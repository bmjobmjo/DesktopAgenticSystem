__tool_exports__ = ['ingest_file', 'search_files']


import os
import shutil
import json
import hashlib
import sqlite3
import threading
import base64
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from core.common_data_area import CommonDataArea
from core.ssl_compat import create_ssl_context
from core.db_schema import DB_PATH
from execution_logger import log_execution_step, log_exception

# -----------------------------------------------------------------------------
# Lazy Imports for File Processing & Embeddings
# -----------------------------------------------------------------------------
try:
    import PyPDF2
except Exception:
    PyPDF2 = None

try:
    import docx
except Exception:
    docx = None

try:
    import openpyxl
except Exception:
    openpyxl = None

try:
    import pptx
except Exception:
    pptx = None

try:
    import torch
    import torch.nn.functional as F
    from transformers import AutoModel, AutoTokenizer
except Exception:
    torch = None
    F = None
    AutoModel = None
    AutoTokenizer = None

_EMBEDDING_MODEL = None
_EMBEDDING_TOKENIZER = None
_EMBEDDING_MODEL_ID = None
_EMBEDDING_LOCK = threading.Lock()
_FIXED_EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_EMBEDDING_ROOT = _PROJECT_ROOT / "EmbedingModel"
_LOCAL_EMBEDDING_DIR = _LOCAL_EMBEDDING_ROOT / "Qwen3-Embedding-8B"
_FIXED_MAX_TOKENS = 2048
_FIXED_OVERLAP_TOKENS = 256
_QUERY_INSTRUCTION = (
    "Given a user question, retrieve relevant passages from ingested files "
    "that directly answer the question."
)

_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}


def _can_skip_embeddings(category: Any) -> bool:
    raw = str(category or "").strip().lower()
    return raw in {"incoming_file", "expense", "expenses"}



def _mean_pooling(last_hidden_state, attention_mask):
    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    masked_embeddings = last_hidden_state * mask
    sum_embeddings = masked_embeddings.sum(dim=1)
    sum_mask = mask.sum(dim=1).clamp(min=1e-9)
    return sum_embeddings / sum_mask


def _last_token_pool(last_hidden_states, attention_mask):
    left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
    if left_padding:
        return last_hidden_states[:, -1]
    sequence_lengths = attention_mask.sum(dim=1) - 1
    batch_size = last_hidden_states.shape[0]
    return last_hidden_states[torch.arange(batch_size, device=last_hidden_states.device), sequence_lengths]


def _is_qwen_embedding_model(model) -> bool:
    model_type = str(getattr(getattr(model, "config", None), "model_type", "") or "").lower()
    return model_type.startswith("qwen")


def _format_retrieval_query(query: str) -> str:
    return f"Instruct: {_QUERY_INSTRUCTION}\nQuery:{query}"


def _is_local_embedding_model_ready(model_dir: Path) -> bool:
    # Minimal files expected after save_pretrained for model/tokenizer.
    required_any = [
        model_dir / "config.json",
        model_dir / "tokenizer.json",
        model_dir / "tokenizer_config.json",
    ]
    return all(p.exists() for p in required_any)


def _load_embedding_model():
    global _EMBEDDING_MODEL, _EMBEDDING_TOKENIZER, _EMBEDDING_MODEL_ID
    if torch is None or AutoModel is None or AutoTokenizer is None or F is None:
        log_execution_step('EMBEDDING_INIT', "transformers/torch are not installed.")
        return None, None

    model_id_or_path = str(_LOCAL_EMBEDDING_DIR)

    with _EMBEDDING_LOCK:
        if _EMBEDDING_MODEL is not None and _EMBEDDING_TOKENIZER is not None and _EMBEDDING_MODEL_ID == model_id_or_path:
            return _EMBEDDING_MODEL, _EMBEDDING_TOKENIZER
        try:
            _LOCAL_EMBEDDING_DIR.mkdir(parents=True, exist_ok=True)

            if _is_local_embedding_model_ready(_LOCAL_EMBEDDING_DIR):
                log_execution_step(
                    'EMBEDDING_INIT',
                    f"Loading Qwen embedding model from local folder '{_LOCAL_EMBEDDING_DIR}'...",
                )
                tokenizer = AutoTokenizer.from_pretrained(
                    str(_LOCAL_EMBEDDING_DIR),
                    trust_remote_code=True,
                    local_files_only=True,
                    padding_side="left",
                )
                model = AutoModel.from_pretrained(
                    str(_LOCAL_EMBEDDING_DIR),
                    trust_remote_code=True,
                    local_files_only=True,
                )
            else:
                log_execution_step(
                    'EMBEDDING_INIT',
                    f"Downloading Qwen embedding model '{_FIXED_EMBEDDING_MODEL}' to '{_LOCAL_EMBEDDING_DIR}'...",
                )
                tokenizer = AutoTokenizer.from_pretrained(
                    _FIXED_EMBEDDING_MODEL,
                    trust_remote_code=True,
                    cache_dir=str(_LOCAL_EMBEDDING_ROOT),
                    padding_side="left",
                )
                model = AutoModel.from_pretrained(
                    _FIXED_EMBEDDING_MODEL,
                    trust_remote_code=True,
                    cache_dir=str(_LOCAL_EMBEDDING_ROOT),
                )
                tokenizer.save_pretrained(str(_LOCAL_EMBEDDING_DIR))
                model.save_pretrained(str(_LOCAL_EMBEDDING_DIR))

            model.eval()
            _EMBEDDING_MODEL = model
            _EMBEDDING_TOKENIZER = tokenizer
            _EMBEDDING_MODEL_ID = model_id_or_path
            log_execution_step('EMBEDDING_INIT', f"Qwen embedding model loaded from '{model_id_or_path}'.")
            return _EMBEDDING_MODEL, _EMBEDDING_TOKENIZER
        except Exception as e:
            log_exception('EMBEDDING_LOAD_ATTEMPT_FAILED', e, {'model': model_id_or_path})
            return None, None


def _encode_texts(texts: List[str]) -> List[List[float]]:
    model, tokenizer = _load_embedding_model()
    if model is None or tokenizer is None:
        raise RuntimeError("Qwen embedding model is not available.")

    try:
        encoded = tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=_FIXED_MAX_TOKENS,
            return_tensors="pt",
        )
        with torch.no_grad():
            outputs = model(**encoded)
        if _is_qwen_embedding_model(model):
            pooled = _last_token_pool(outputs.last_hidden_state, encoded["attention_mask"])
        else:
            pooled = _mean_pooling(outputs.last_hidden_state, encoded["attention_mask"])
        normalized = F.normalize(pooled, p=2, dim=1)
        return normalized.cpu().tolist()
    except Exception as e:
        log_exception('EMBEDDING_ENCODE_FAILED', e, {'count': len(texts)})
        raise

# -----------------------------------------------------------------------------
# Optimization: Text Extraction Logic
# -----------------------------------------------------------------------------
def _extract_text(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    
    if ext == '.pdf':
        if not PyPDF2: return "[PyPDF2 not installed]"
        text = ""
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += (page.extract_text() or "") + "\n"
        except Exception as e:
            text = f"[Error reading PDF: {e}]"
        return text
        
    elif ext in ['.docx', '.doc']:
        if not docx: return "[python-docx not installed]"
        try:
            doc = docx.Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        except Exception as e:
            return f"[Error reading DOCX: {e}]"
            
    elif ext in ['.xlsx', '.xls']:
        if not openpyxl: return "[openpyxl not installed]"
        text = ""
        try:
            wb = openpyxl.load_workbook(file_path, data_only=True)
            for sheet in wb.sheetnames:
                ws = wb[sheet]
                text += f"Sheet: {sheet}\n"
                for row in ws.iter_rows(values_only=True):
                    row_text = " ".join([str(cell) for cell in row if cell is not None])
                    text += row_text + "\n"
        except Exception as e:
            text = f"[Error reading Excel: {e}]"
        return text

    elif ext in ['.pptx', '.ppt']:
        if not pptx: return "[python-pptx not installed]"
        text = ""
        try:
            prs = pptx.Presentation(file_path)
            for slide in prs.slides:
                for shape in slide.shapes:
                    if hasattr(shape, "text"):
                        text += shape.text + "\n"
        except Exception as e:
            text = f"[Error reading PPT: {e}]"
        return text

    elif ext in _IMAGE_EXTENSIONS:
        return "[Image content extraction is handled by the multimodal LLM pipeline during ingestion.]"

    else:
        # Default to plain text
        try:
            return file_path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            return f"[Error reading text: {e}]"

def _compute_hash(file_path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for b in iter(lambda: f.read(4096), b""):
            sha256.update(b)
    return sha256.hexdigest()

def _chunk_text_by_tokens(text: str, max_tokens: int, overlap_tokens: int) -> List[str]:
    if not text:
        return []
    _, tokenizer = _load_embedding_model()
    if tokenizer is None:
        return [text]

    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if not token_ids:
        return [text]
    if max_tokens <= 0:
        max_tokens = _FIXED_MAX_TOKENS
    if overlap_tokens < 0:
        overlap_tokens = 0
    if overlap_tokens >= max_tokens:
        overlap_tokens = max_tokens // 8

    step = max_tokens - overlap_tokens
    chunks: List[str] = []
    start = 0
    while start < len(token_ids):
        end = min(start + max_tokens, len(token_ids))
        chunk_tokens = token_ids[start:end]
        chunk_text = tokenizer.decode(chunk_tokens, skip_special_tokens=True)
        if chunk_text.strip():
            chunks.append(chunk_text)
        if end >= len(token_ids):
            break
        start += step
    return chunks


def _text_token_count(text: str) -> int:
    if not text:
        return 0
    _, tokenizer = _load_embedding_model()
    if tokenizer is None:
        return 0
    try:
        return len(tokenizer.encode(text, add_special_tokens=False))
    except Exception:
        return 0

def _get_embeddings_db_path() -> Path:
    cda = CommonDataArea()
    configured = str(cda.get_setting('sqlite_db_path', '') or '').strip()
    if configured:
        return Path(configured).resolve()
    return Path(DB_PATH).resolve()

def _post_json(url: str, body: Dict[str, Any], headers: Dict[str, str], timeout: int = 120) -> Dict[str, Any]:
    data = json.dumps(body).encode('utf-8')
    request = urllib.request.Request(url, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(request, timeout=timeout, context=create_ssl_context()) as response:
        payload = json.loads(response.read().decode('utf-8'))
        return payload if isinstance(payload, dict) else {}


def _project_context(cda: CommonDataArea) -> str:
    db_path = _get_embeddings_db_path()
    if not db_path.exists():
        return "No projects available."
    try:
        with sqlite3.connect(str(db_path), timeout=20) as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='Projects'")
            if not cur.fetchone():
                return "No projects available."
            cur.execute("PRAGMA table_info(Projects)")
            cols = {str(r[1]) for r in cur.fetchall()}
            select_cols = ["id", "name"]
            select_cols.append("description" if "description" in cols else "'' AS description")
            select_cols.append("status" if "status" in cols else "'' AS status")
            cur.execute(f"SELECT {', '.join(select_cols)} FROM Projects ORDER BY id")
            rows = cur.fetchall()
    except Exception:
        return "No projects available."
    if not rows:
        return "No projects available."
    lines = []
    for row in rows:
        lines.append(
            f"- ID {row[0]} | Name: {str(row[1] or '').strip()} | Status: {str(row[3] or '').strip()} | Description: {str(row[2] or '').strip()}"
        )
    return "\n".join(lines)


def _normalize_project_id(value: Any, cda: CommonDataArea) -> Any:
    if value in (None, '', 'null', 'None'):
        return None
    try:
        project_id = int(value)
    except Exception:
        return None
    db_path = _get_embeddings_db_path()
    if not db_path.exists():
        return None
    try:
        with sqlite3.connect(str(db_path), timeout=20) as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM Projects WHERE id=? LIMIT 1", (project_id,))
            return project_id if cur.fetchone() else None
    except Exception:
        return None


def _image_analysis_prompt(project_context: str, user_description: str | None = None) -> str:
    user_context = ''
    if user_description:
        user_context = (
            f"\nUser provided context: '{str(user_description).strip()}'\n"
            "Use this context if it is consistent with the image."
        )
    return (
        "Analyze this image and return JSON only.\n"
        "Return fields:\n"
        "- description: a detailed, information-dense summary of the image in about 120-300 words. Include visible text, objects, layout, labels, UI elements, symbols, logos, and likely purpose/context. Write it for semantic search quality.\n"
        "- extracted_details: a thorough plain-text description of all visible content, including text, labels, layout, objects, symbols, logos, UI elements, tables, and context\n"
        "- keywords: array of important keywords or tags\n"
        "- document_type: short label such as screenshot, logo, photo, scanned page, chart, UI mockup, etc.\n"
        "- matched_project_id: integer project ID if the image strongly matches one project from the provided project list, otherwise null\n"
        f"{user_context}\n"
        "Available Projects:\n"
        f"{project_context}\n\n"
        "Project matching rules:\n"
        "- Compare the image content against the provided project names and descriptions.\n"
        "- Return a project ID only if there is a clear semantic match.\n"
        "- If multiple projects are plausible but none is clearly best, return null.\n"
        "- If no project matches, return null.\n"
        "- Never invent a project ID."
    )


def _analyze_image_with_llm(file_path: Path, cda: CommonDataArea, user_description: str | None = None) -> Dict[str, Any]:
    provider = str(cda.get_setting('llm_provider', 'gemini') or 'gemini').strip().lower()
    project_context = _project_context(cda)
    prompt = _image_analysis_prompt(project_context, user_description)
    mime = 'image/jpeg'
    if file_path.suffix.lower() == '.png':
        mime = 'image/png'
    elif file_path.suffix.lower() == '.webp':
        mime = 'image/webp'
    elif file_path.suffix.lower() == '.bmp':
        mime = 'image/bmp'
    elif file_path.suffix.lower() in ('.tif', '.tiff'):
        mime = 'image/tiff'

    encoded = base64.b64encode(file_path.read_bytes()).decode('ascii')

    if provider == 'gemini':
        api_key = str(cda.get_setting('gemini_api_key', '') or '').strip()
        if not api_key:
            raise RuntimeError('Gemini API key is missing for image analysis.')
        model_id = str(cda.get_setting('gemini_model', 'gemini-1.5-flash') or 'gemini-1.5-flash').strip()
        url = f'https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={api_key}'
        temperature = float(cda.get_setting('gemini_temperature', 0.0) or 0.0)
        body = {
            'contents': [{
                'role': 'user',
                'parts': [
                    {'text': prompt},
                    {'inline_data': {'mime_type': mime, 'data': encoded}},
                ],
            }],
            'generationConfig': {'temperature': temperature},
            'safetySettings': [
                {'category': 'HARM_CATEGORY_HARASSMENT', 'threshold': 'BLOCK_NONE'},
                {'category': 'HARM_CATEGORY_HATE_SPEECH', 'threshold': 'BLOCK_NONE'},
                {'category': 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'threshold': 'BLOCK_NONE'},
                {'category': 'HARM_CATEGORY_DANGEROUS_CONTENT', 'threshold': 'BLOCK_NONE'},
            ],
        }
        payload = _post_json(url, body, {'Content-Type': 'application/json'}, timeout=180)
        response_text = payload['candidates'][0]['content']['parts'][0]['text']
    elif provider in ('local', 'openrouter'):
        if provider == 'local':
            base_url = str(cda.get_setting('local_llm_url', 'http://127.0.0.1:1234/v1') or 'http://127.0.0.1:1234/v1').rstrip('/')
            if not base_url.endswith('/chat/completions'):
                base_url += '/chat/completions'
            model_id = str(cda.get_setting('local_llm_model', 'qwen2.5-14b-instruct-1m') or 'qwen2.5-14b-instruct-1m').strip()
            headers = {'Content-Type': 'application/json'}
        else:
            base_url = 'https://openrouter.ai/api/v1/chat/completions'
            model_id = str(cda.get_setting('openrouter_model', 'stepfun/step-3.5-flash') or 'stepfun/step-3.5-flash').strip()
            api_key = str(cda.get_setting('openrouter_api_key', '') or '').strip()
            if not api_key:
                raise RuntimeError('OpenRouter API key is missing for image analysis.')
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {api_key}',
                'HTTP-Referer': 'http://localhost:8000',
                'X-Title': 'DesktopAgenticSystem',
            }

        body = {
            'model': model_id,
            'messages': [{
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': prompt},
                    {'type': 'image_url', 'image_url': {'url': f'data:{mime};base64,{encoded}'}},
                ],
            }],
            'temperature': 0.0,
            'stream': False,
        }
        payload = _post_json(base_url, body, headers, timeout=180)
        response_text = str(payload['choices'][0]['message']['content'])
    else:
        llm = cda.get_runtime('llm_client')
        if llm is None:
            raise RuntimeError(f'Unsupported LLM provider for image analysis: {provider}')
        response_text = llm.generate(prompt, agent_name='ImageIngestor', user_prompt='Analyze image file')

    import re
    match = re.search(r'\{.*\}', response_text, re.DOTALL)
    if not match:
        raise RuntimeError('Image analysis response did not contain JSON.')
    data = json.loads(match.group(0))
    description = str(data.get('description', '') or '').strip() or 'No description generated.'
    details = str(data.get('extracted_details', '') or '').strip()
    if not details:
        details = description
    result = {
        'description': description,
        'extracted_details': details,
        'keywords': data.get('keywords', []),
        'document_type': data.get('document_type'),
        'matched_project_id': _normalize_project_id(data.get('matched_project_id'), cda),
    }
    return result

# -----------------------------------------------------------------------------
# Main Tool Functions
# -----------------------------------------------------------------------------

def ingest_file(file_path: str, category: str = None, user_description: str = None, status_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """
    Ingest a file into the knowledge base (copy, index, and embed).

    Process:
    1. Copies the file to the configured 'file_storage_path'.
    2. Extracts text content (PDF, DOCX, XLSX, PPTX) and uses multimodal LLM analysis for images.
    3. Generates a detailed search-oriented description using LLM.
    4. Matches the file to a project when there is a clear semantic fit.
    5. Creates vector embeddings for the description and content chunks.
    6. Stores metadata in the Database.

    Args:
        file_path (str): Absolute path to the source file.
        category (str, optional): Metadata category tag.
        user_description (str, optional): A user-provided description to guide the LLM summary.
        status_callback (callable, optional): UI status update handler.

    Returns:
        Dict: Success status and metadata including 'file_id' and 'description'.
    """
    if status_callback:
        status_callback(f"Processing {os.path.basename(file_path)}...")
        
    cda = CommonDataArea()
    source_path = Path(file_path).resolve()
    
    if not source_path.exists():
        return {"success": False, "error": f"Source file not found: {file_path}"}

    # 1. Read Settings
    storage_setting = cda.get_setting('file_storage_path', 'storage/files')
    # Resolve storage path relative to project root (CWD in most cases here)
    storage_dir = Path(storage_setting).resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)

    # 2. Copy File
    dest_path = storage_dir / source_path.name
    # Handle naming collision if needed, but for now overwrite or simple copy
    if dest_path.exists():
        # Checking hash to see if identical?
        if _compute_hash(source_path) == _compute_hash(dest_path):
            pass # Same file
        else:
            # Append timestamp or incremental
            stem = source_path.stem
            ext = source_path.suffix
            import time
            dest_path = storage_dir / f"{stem}_{int(time.time())}{ext}"
    
    shutil.copy2(source_path, dest_path)
    final_path = dest_path

    # 3. Create File Entry in DB
    file_hash = _compute_hash(final_path)
    file_size = final_path.stat().st_size
    
    # Store relative path in DB for portability
    try:
        db_path_str = os.path.relpath(final_path, os.getcwd())
    except Exception:
        db_path_str = str(final_path)
    
    log_execution_step('INGEST', f"Final storage path (relative): {db_path_str}")

    db_path = _get_embeddings_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path), timeout=20) as conn:
        cursor = conn.cursor()
        
        # Check if this exact file (by path) exists?
        cursor.execute("SELECT id FROM Files WHERE file_path = ?", (db_path_str,))
        existing = cursor.fetchone()
        
        if existing:
            file_id = existing[0]
            # Update metadata
            cursor.execute("UPDATE Files SET file_hash=?, file_size=?, upload_date=CURRENT_TIMESTAMP WHERE id=?", 
                           (file_hash, file_size, file_id))
            # Clear old embeddings/expenses
            cursor.execute("DELETE FROM Embeddings WHERE source_type='file' AND source_id=?", (file_id,))
            cursor.execute("DELETE FROM Expenses WHERE file_id=?", (file_id,))
        else:
            cursor.execute("INSERT INTO Files (file_path, filename, file_type, file_size, file_hash) VALUES (?, ?, ?, ?, ?)",
                           (db_path_str, final_path.name, final_path.suffix, file_size, file_hash))
            file_id = cursor.lastrowid
            
        conn.commit()

        # Phase 1: Text Extraction
        log_execution_step('INGEST', f"Starting extraction for {final_path.name}")
        if status_callback:
            status_callback(f"Extracting text from {final_path.name}...")
        
        image_analysis: Dict[str, Any] = {}
        description = "No description generated."
        matched_project_id = None

        try:
            if final_path.suffix.lower() in _IMAGE_EXTENSIONS:
                log_execution_step('INGEST', f"Starting multimodal image analysis for {final_path.name}")
                if status_callback:
                    status_callback(f"Analyzing image {final_path.name} with LLM...")
                image_analysis = _analyze_image_with_llm(final_path, cda, user_description=user_description)
                description = str(image_analysis.get('description', description) or description)
                text_content = str(image_analysis.get('extracted_details', '') or '').strip()
                matched_project_id = image_analysis.get('matched_project_id')
                if not text_content:
                    text_content = description
                log_execution_step('INGEST', f"Image analysis produced {len(text_content)} characters.")
            else:
                text_content = _extract_text(final_path)
                log_execution_step('INGEST', f"Extracted {len(text_content)} characters.")
        except Exception as e:
            log_exception('INGEST_ERROR', e, f"Content extraction failed for {final_path.name}")
            raise
            
        # Phase 2: Embed Document Content first
        model, tokenizer = _load_embedding_model()
        skip_embeddings = not bool(model and tokenizer)
        if skip_embeddings:
            log_execution_step('INGEST_EMBEDDINGS_SKIPPED', "Embedding model unavailable; continuing without embeddings.")
            if not _can_skip_embeddings(category):
                log_execution_step('INGEST_WARNING', f"Continuing without embeddings for category '{category}'.")

        if not skip_embeddings:
            chunks = _chunk_text_by_tokens(
                text_content,
                max_tokens=_FIXED_MAX_TOKENS,
                overlap_tokens=_FIXED_OVERLAP_TOKENS,
            )
            log_execution_step('INGEST', f"Document split into {len(chunks)} chunks. Starting vectorization.")
            
            try:
                for i, chk in enumerate(chunks):
                    if status_callback:
                        status_callback(f"Embedding chunk {i+1}/{len(chunks)}...")
                    
                    vec = _encode_texts([chk])[0]
                    chunk_char_count = len(chk)
                    chunk_token_count = _text_token_count(chk)
                    cursor.execute(
                        "INSERT INTO Embeddings (source_type, source_id, chunk_index, type, content, char_count, token_count, embedding_vector, enc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        ('file', file_id, i, 'file_text', chk, chunk_char_count, chunk_token_count, json.dumps(vec), 0)
                    )
                    if i == 0 or i == len(chunks) - 1 or (i+1) % 5 == 0:
                        log_execution_step('INGEST_DB', f"Saved chunk {i+1}/{len(chunks)} to Embeddings.")

                conn.commit()
                log_execution_step('INGEST', "Primary content embeddings committed to database.")
            except Exception as e:
                log_exception('INGEST_DB_ERROR', e, "Failed to save content embeddings.")
                raise

        # Phase 3: LLM Enrichment (Description & Project Matching)
        if final_path.suffix.lower() not in _IMAGE_EXTENSIONS:
            llm = cda.get_runtime('llm_client')
            if llm:
                snippet = text_content[:2000]
                log_execution_step('INGEST', "Requesting LLM analysis for detailed description & project matching...")
                user_context = ""
                if user_description:
                    user_context = f"\n        User provided description/context: '{user_description}'\n        Please incorporate this user context into the final description."
                project_context = _project_context(cda)

                prompt = f"""
            Analyze the following file content and return JSON only.

            Return fields:
            - description: a detailed, information-dense summary of the file in about 120-300 words. Include file type, purpose, main topics, important entities, dates, technical terms, and key takeaways. Write it for semantic search quality.{user_context}
            - keywords: array of important keywords or tags
            - document_type: short label such as report, presentation, spreadsheet, technical note, contract, screenshot, image, etc.
            - matched_project_id: integer project ID if the file strongly matches one project from the provided project list, otherwise null

            Available Projects:
            {project_context}

            Project matching rules:
            - Compare the file content against the provided project names and descriptions.
            - Return a project ID only if there is a clear semantic match.
            - If multiple projects are plausible but none is clearly best, return null.
            - If no project matches, return null.
            - Never invent a project ID.
            
            Content:
            {snippet}
            
            Return JSON only.
            """
                try:
                    if status_callback:
                        status_callback("Analyzing metadata with LLM...")
                    response = llm.generate(prompt, agent_name="Ingestor", user_prompt="Ingest File")
                    import re
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        data = json.loads(json_match.group(0))
                        description = data.get('description', description)
                        matched_project_id = _normalize_project_id(data.get('matched_project_id'), cda)
                    log_execution_step('INGEST', f"LLM metadata analysis successful: {description[:50]}...")
                except Exception as e:
                    log_exception('INGEST_LLM_ERROR', e, "LLM Enrichment failed - continuing without description.")
        else:
            log_execution_step('INGEST', f"Using multimodal image analysis description: {description[:50]}...")

        if (not description or description == "No description generated.") and str(text_content or "").strip():
            description = str(text_content).strip()[:500]

        # Phase 4: Final Updates (Description & Description Embedding)
        try:
            # Update File record
            cursor.execute("UPDATE Files SET description = ?, project_id = ? WHERE id = ?", (description, matched_project_id, file_id))
            log_execution_step('INGEST_DB', f"Updated file {file_id} description and project link.")

            if not skip_embeddings:
                desc_vec = _encode_texts([description])[0]
                desc_char_count = len(description or "")
                desc_token_count = _text_token_count(description or "")
                cursor.execute(
                    "INSERT INTO Embeddings (source_type, source_id, chunk_index, type, content, char_count, token_count, embedding_vector, enc) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ('file', file_id, -1, 'file_description', description, desc_char_count, desc_token_count, json.dumps(desc_vec), 0)
                )
                log_execution_step('INGEST_DB', "Saved search priority description embedding.")
            conn.commit()
            log_execution_step('INGEST_COMPLETE', f"Successfully ingested {final_path.name}")
        except Exception as e:
            log_exception('INGEST_FINAL_DB_ERROR', e, "Faild to complete final metadata updates.")
    
    return {
        "success": True,
        "file_id": file_id,
        "stored_path": str(final_path),
        "description": description,
        "project_id": matched_project_id,
        "embeddings_indexed": not skip_embeddings,
        "warning": "" if not skip_embeddings else "Embeddings unavailable; file stored without vector indexing."
    }

def search_files(query: str, top_k: int = 5, threshold: float = 0.35) -> List[Dict[str, Any]]:
    """
    Search for files using semantic search (vector embeddings).
    
    The search uses a hybrid approach, boosting matches on the file description
    while also searching within the document content chunks.

    Args:
        query (str): The search query text.
        top_k (int, optional): Number of results to return. Defaults to 5.
        threshold (float, optional): Minimum cosine similarity score to keep a match.
            Valid range is [-1.0, 1.0]. Defaults to 0.35.

    Returns:
        List[Dict]: A list of matching files with 'score', 'snippet', and metadata.
    """
    cda = CommonDataArea()
    try:
        threshold = float(threshold)
    except Exception:
        return [{"error": f"Invalid threshold value: {threshold}"}]
    if threshold < -1.0 or threshold > 1.0:
        return [{"error": f"Threshold out of range [-1.0, 1.0]: {threshold}"}]
    model, tokenizer = _load_embedding_model()

    if not model or not tokenizer:
        return [{"error": "Embedding model not loaded."}]

    try:
        query_vec = _encode_texts([_format_retrieval_query(query)])[0]
    except Exception as e:
        return [{"error": f"Encoding failed: {e}"}]

    db_path = _get_embeddings_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT f.id, f.filename, f.file_path, f.description, 
               e.type, e.content, e.embedding_vector 
        FROM Embeddings e
        JOIN Files f ON e.source_type = 'file' AND e.source_id = f.id
    """)
    rows = cursor.fetchall()
    
    try:
        import numpy as np
    except ImportError:
        conn.close()
        return [{"error": "Numpy required for search."}]
    
    results = []
    q_norm = np.linalg.norm(query_vec)
    if q_norm == 0: q_norm = 1e-9

    for row in rows:
        vec_blob = row['embedding_vector']
        if not vec_blob: continue
        
        try:
            vec = np.array(json.loads(vec_blob))
            v_norm = np.linalg.norm(vec)
            if v_norm == 0: v_norm = 1e-9
            
            score = np.dot(query_vec, vec) / (q_norm * v_norm)
            
            # Boost description
            if row['type'] == 'file_description':
                score *= 1.2
            
            if score >= threshold:
                results.append({
                    "file_id": row['id'],
                    "filename": row['filename'],
                    "path": row['file_path'],
                    "description": row['description'],
                    "match_type": row['type'],
                    "snippet": row['content'] or '',
                    "score": float(score)
                })
        except Exception:
            continue
            
    conn.close()
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_k]
