"""Synchronize built-in agent templates into one or more SQLite databases.

This preserves a previous prompt version whenever the prompt body changes, so a
database deployed outside the source tree can be updated safely.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENTS_DIR = ROOT / "apps" / "das_core" / "agents"

AGENT_METADATA = {
    "router": "Routes requests to the appropriate specialized agent.",
    "attendance_manager": (
        "Manage attendance check-in, check-out, open-session status, and attendance history. "
        "Managers and admins may view organization-wide attendance, generate CSV/PDF reports, and deliver those "
        "reports through configured WhatsApp or Telegram channels. Not leave or break management."
    ),
    "dailytask_manager": (
        "Manage daily operational tasks when the request explicitly concerns daily tasks, today's tasks, "
        "yesterday's tasks, last-week daily tasks, or daily-task roll-forward. Managers and admins may view "
        "team daily-task reports, generate CSV/PDF exports, and deliver them through configured WhatsApp or "
        "Telegram channels. Do not select this agent for a generic request such as \"list my tasks\"."
    ),
    "work_diary_manager": (
        "Manage work diary entries, recent diary views, limited updates, and optional project linkage. "
        "Managers and admins may view team work-diary reports, generate CSV/PDF exports, and deliver them "
        "through configured WhatsApp or Telegram channels. Not task assignment or backlog management."
    ),
    "expense_manager": (
        "Create expense entries directly from user-provided details or receipts, using safe defaults for omitted "
        "category, date, currency, project, purchaser, status, and file linkage. Treat mark, log, or record this "
        "expense as creation unless the user clearly identifies an existing expense to update. Also manage expense "
        "updates and reports. No approval workflow."
    ),
    "employee_manager": (
        "Manage employee records and organizational job-title/designation lookups. "
        "Use Employees.designation for titles, not access-control roles."
    ),
    "organization_management_agent": (
        "Manage users, access roles, departments, project master records, and project membership. "
        "Organizational title lookups belong to employee_manager."
    ),
    "project_manager": (
        "Own project-specific documents, project schedules, timelines, milestones, plans, and project task schedules, "
        "plus notes, meeting minutes, project memory, project knowledge facts, reports, and task retrieval. Route "
        "requests to create, update, maintain, review, or view a named project's schedule, timeline, milestones, "
        "plan, or task schedule here. Timed or recurring automation belongs to schedule_manager. Route generic task-list requests such as \"list my tasks\" here unless "
        "the user explicitly asks for daily tasks or today's tasks; also handle tasks for a named project."
    ),
    "schedule_manager": (
        "Validate and manage timed or recurring automation schedules. A project schedule document without an "
        "explicit automation request belongs to project_manager."
    ),
    "task_manager": (
        "Manage formal general and project-linked tasks and issues, including backlog, assignment, notes, reopen, "
        "inactivation, and status updates. Not daily-task planning."
    ),
}

# Older deployments may still reference this former built-in name.
NAME_ALIASES = {"organization_management_agent": ("OrganizationManagementAgent",)}


def prompt_path(agent_name: str) -> Path:
    if agent_name == "router":
        return AGENTS_DIR / "router" / "router.prompt"
    return AGENTS_DIR / agent_name / f"{agent_name}.prompt"


def sync_agent(cursor: sqlite3.Cursor, agent_name: str, content: str) -> int:
    names = (agent_name, *NAME_ALIASES.get(agent_name, ()))
    placeholders = ", ".join("?" for _ in names)
    rows = cursor.execute(
        f"SELECT id, name, description, prompt_content, COALESCE(version, 1) FROM Agents WHERE name IN ({placeholders})",
        names,
    ).fetchall()
    # Older/minimal databases may not have every built-in agent.  Keep those
    # databases usable while synchronizing whichever matching records exist.
    if not rows:
        return 0

    updated = 0
    for agent_id, stored_name, old_description, old_content, version in rows:
        if old_content == content and old_description == AGENT_METADATA[agent_name]:
            continue
        if old_content != content:
            cursor.execute(
                """
                INSERT INTO AgentPromptVersion (agent_id, agent_name, prompt_content, version)
                VALUES (?, ?, ?, ?)
                """,
                (agent_id, stored_name, old_content, version),
            )
            cursor.execute(
                """
                UPDATE Agents
                SET description=?, prompt_content=?, version=?, is_active=1
                WHERE id=?
                """,
                (AGENT_METADATA[agent_name], content, int(version) + 1, agent_id),
            )
        else:
            cursor.execute(
                "UPDATE Agents SET description=?, is_active=1 WHERE id=?",
                (AGENT_METADATA[agent_name], agent_id),
            )
        updated += 1
    return updated


def sync_database(db_path: Path, agent_names: list[str]) -> int:
    if not db_path.is_file():
        raise FileNotFoundError(db_path)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        tables = {row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "Agents" not in tables or "AgentPromptVersion" not in tables:
            raise RuntimeError(f"{db_path} does not have the required Agents prompt tables")

        changed = 0
        for agent_name in agent_names:
            changed += sync_agent(cursor, agent_name, prompt_path(agent_name).read_text(encoding="utf-8"))
        conn.commit()
    return changed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("databases", nargs="+", type=Path, help="SQLite database paths to update")
    parser.add_argument(
        "--agent",
        action="append",
        choices=sorted(AGENT_METADATA),
        dest="agents",
        help="Built-in agent to synchronize; specify more than once. Defaults to all supported agents.",
    )
    args = parser.parse_args()
    agent_names = args.agents or list(AGENT_METADATA)

    for database in args.databases:
        changed = sync_database(database.resolve(), agent_names)
        print(f"{database}: synchronized {changed} agent prompt(s)")


if __name__ == "__main__":
    main()
