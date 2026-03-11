
import sqlite3
import tempfile
import os
from pathlib import Path
from typing import List, Dict, Any, Union

__tool_exports__ = ['execute_sql']

from core.common_data_area import CommonDataArea
from execution_logger import log_execution_step, log_exception

def execute_sql(queries: List[str] | str) -> Union[List[Union[List[Dict[str, Any]], str]], Dict[str, Any]]:
    """
    Execute one or more SQL queries against the internal SQLite database.

    Args:
        queries (List[str]): A list of SQL statements to execute.

    Returns:
        Union[List[Any], Dict]: 
            - On success: A list of results. SELECTs return lists of dicts (rows).
              Other queries return success messages.
            - On failure: A dictionary containing error details.
    """
    if isinstance(queries, str):
        queries = [queries]
    elif isinstance(queries, tuple):
        queries = list(queries)
    elif not isinstance(queries, list):
        return {
            "success": False,
            "error": f"Database Error: queries must be a list of SQL strings or a single SQL string, got {type(queries).__name__}",
            "query_index": -1,
            "failed_query": "",
            "partial_results": [],
            "foreign_keys_on": True,
        }

    cda = CommonDataArea()
    db_path_str = cda.get_setting('sqlite_db_path', 'backend.db')
    db_path = Path(db_path_str).resolve()
    fallback_db_path = Path(tempfile.gettempdir()) / f"desktop_agentic_fallback_{os.getpid()}.db"
    current_db_path = db_path

    current_db_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _err_payload(
        message: str,
        failed_query: str = "",
        query_index: int = -1,
        partial_results: List[Union[List[Dict[str, Any]], str]] | None = None,
        foreign_keys_on: bool = True,
    ) -> Dict[str, Any]:
        return {
            "success": False,
            "error": f"Database Error: {message}",
            "query_index": query_index,
            "failed_query": failed_query,
            "partial_results": partial_results or [],
            "foreign_keys_on": foreign_keys_on,
        }

    def _run_batch(foreign_keys_on: bool) -> Dict[str, Any]:
        batch_results: List[Union[List[Dict[str, Any]], str]] = []
        try:
            with sqlite3.connect(current_db_path) as conn:
                conn.execute(f"PRAGMA foreign_keys = {'ON' if foreign_keys_on else 'OFF'};")
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                for idx, raw_query in enumerate(queries):
                    query = (raw_query or "").strip()
                    if not query:
                        continue

                    log_execution_step("SQL_TOOL_QUERY", f"#{idx + 1}: {query[:220]}")
                    try:
                        cursor.execute(query)
                    except sqlite3.Error as q_err:
                        conn.rollback()
                        log_execution_step("SQL_TOOL_ERROR", f"Query #{idx + 1} failed: {q_err}")
                        log_exception(
                            "SQL_TOOL_ERROR",
                            q_err,
                            {"query_index": idx, "query": query, "foreign_keys_on": foreign_keys_on},
                        )
                        return _err_payload(
                            str(q_err),
                            failed_query=query,
                            query_index=idx,
                            partial_results=batch_results,
                            foreign_keys_on=foreign_keys_on,
                        )

                    if query.upper().startswith("SELECT") or "RETURNING" in query.upper():
                        rows = cursor.fetchall()
                        batch_results.append([dict(row) for row in rows])
                    else:
                        batch_results.append(f"Success. Rows affected: {cursor.rowcount}")

                conn.commit()
            return {"success": True, "results": batch_results, "foreign_keys_on": foreign_keys_on}
        except sqlite3.Error as conn_err:
            log_execution_step("SQL_TOOL_ERROR", f"Connection/transaction failed: {conn_err}")
            log_exception(
                "SQL_TOOL_ERROR",
                conn_err,
                {"phase": "connection_or_transaction", "foreign_keys_on": foreign_keys_on},
            )
            return _err_payload(
                str(conn_err),
                partial_results=batch_results,
                foreign_keys_on=foreign_keys_on,
            )

    log_execution_step("SQL_TOOL_START", f"Executing {len(queries)} queries on {current_db_path}")
    first_attempt = _run_batch(foreign_keys_on=True)
    if first_attempt.get("success"):
        log_execution_step("SQL_TOOL_DONE", "Batch executed successfully with foreign_keys=ON")
        return first_attempt.get("results", [])

    err = str(first_attempt.get("error", ""))
    if "disk i/o error" in err.lower():
        try:
            fallback_db_path.parent.mkdir(parents=True, exist_ok=True)
            current_db_path = fallback_db_path.resolve()
            cda.set_setting('sqlite_db_path', str(current_db_path))
            log_execution_step("SQL_TOOL_RETRY", f"Retrying batch on fallback DB: {current_db_path}")
            retry_io_attempt = _run_batch(foreign_keys_on=True)
            if retry_io_attempt.get("success"):
                log_execution_step("SQL_TOOL_DONE", "Batch executed successfully on fallback DB")
                return retry_io_attempt.get("results", [])
            return retry_io_attempt
        except Exception as fallback_exc:
            return _err_payload(str(fallback_exc))

    holiday_query = any("holidaylist" in (q or "").lower() for q in queries)

    # Workaround for legacy/migrated DBs where HolidayList FK points to Users_Old.
    if holiday_query and "users_old" in err.lower():
        log_execution_step("SQL_TOOL_RETRY", "Retrying HolidayList batch with foreign_keys=OFF due to Users_Old FK")
        retry_attempt = _run_batch(foreign_keys_on=False)
        if retry_attempt.get("success"):
            log_execution_step("SQL_TOOL_DONE", "Batch executed successfully with foreign_keys=OFF")
            return retry_attempt.get("results", [])
        return retry_attempt

    return first_attempt

