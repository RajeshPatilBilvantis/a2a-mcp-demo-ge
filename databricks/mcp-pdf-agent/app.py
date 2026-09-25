import os, io, json, base64
from urllib.parse import urlparse

import requests
import uvicorn
from pypdf import PdfReader
import pypdfium2 as pdfium
from starlette.responses import JSONResponse
from mcp.server.fastmcp import FastMCP
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem

TABLE        = "workspace.default.pdf_results"
VOLUME_PATH  = "/Volumes/workspace/default/raw_pdfs"
LLM_ENDPOINT = "databricks-claude-sonnet-5"
WAREHOUSE_ID = "37a0db839bacb60b"
MAX_PAGES    = 5
MAX_BYTES    = 10 * 1024 * 1024

w   = WorkspaceClient()
from openai import OpenAI

def get_llm():
    headers = w.config.authenticate()
    token = headers["Authorization"].split(" ", 1)[1]
    host = w.config.host.rstrip("/")
    return OpenAI(api_key=token, base_url=f"{host}/serving-endpoints")

class _FreshLLM:
    @property
    def chat(self):
        return get_llm().chat

llm = _FreshLLM()


def save_pdf_copy(job_id, file_name, pdf_bytes):
    path = f"{VOLUME_PATH}/{job_id}_{file_name}"
    w.files.upload(path, io.BytesIO(pdf_bytes), overwrite=True)
    return path


def ocr_with_vision(pdf_bytes):
    pdf = pdfium.PdfDocument(pdf_bytes)
    content = [{"type": "text",
                "text": "Transcribe all text on these pages exactly. Return only the text."}]
    for i in range(len(pdf)):
        img = pdf[i].render(scale=2).to_pil()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"}})
    resp = llm.chat.completions.create(
        model=LLM_ENDPOINT, messages=[{"role": "user", "content": content}], max_tokens=4000)
    return resp.choices[0].message.content.strip()


def extract_text(pdf_bytes):
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = len(reader.pages)
    if pages > MAX_PAGES:
        raise ValueError(f"PDF has {pages} pages; limit is {MAX_PAGES}")
    text = "\n".join((p.extract_text() or "") for p in reader.pages).strip()
    if len(text) >= 50:
        return text, pages, "text-layer"
    return ocr_with_vision(pdf_bytes), pages, "ocr-vision"


ENRICH_PROMPT = """You are a document analysis agent. Read the document and return ONLY a JSON object with these keys:
"document_type": a short label such as invoice, contract, resume, report or letter,
"key_points": a list of 3 to 6 short strings,
"entities": an object with lists named "people", "organizations", "dates", "amounts",
"summary": a clear summary in 4 to 6 sentences.
Return no markdown and no extra text.

DOCUMENT:
{text}"""


def enrich_and_summarize(text):
    resp = llm.chat.completions.create(
        model=LLM_ENDPOINT,
        messages=[{"role": "user", "content": ENRICH_PROMPT.format(text=text[:30000])}],
        max_tokens=1500)
    raw = resp.choices[0].message.content.strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(raw)


def run_sql(sql, params):
    res = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID, statement=sql,
        parameters=[StatementParameterListItem(name=k, value=str(v)) for k, v in params.items()],
        wait_timeout="30s")
    if res.status.state.value != "SUCCEEDED":
        raise RuntimeError(f"SQL failed: {res.status.error}")
    return res


def save_result(row):
    run_sql(f"""
    INSERT INTO {TABLE}
      (job_id, file_name, page_count, extracted_text, document_type,
       key_points, entities, summary, status, processed_by, created_at)
    VALUES
      (:job_id, :file_name, CAST(:page_count AS INT), :extracted_text, :document_type,
       :key_points, :entities, :summary, :status, :processed_by, current_timestamp())""", row)


def process_pdf(job_id, file_name, pdf_bytes):
    row = {"job_id": job_id, "file_name": file_name, "page_count": 0,
           "extracted_text": "", "document_type": "", "key_points": "[]",
           "entities": "{}", "summary": "", "status": "failed",
           "processed_by": "databricks-pdf-agent"}
    try:
        volume_path = save_pdf_copy(job_id, file_name, pdf_bytes)
        text, pages, method = extract_text(pdf_bytes)
        ai = enrich_and_summarize(text)
        row.update({"page_count": pages, "extracted_text": text,
                    "document_type": ai.get("document_type", ""),
                    "key_points": json.dumps(ai.get("key_points", [])),
                    "entities": json.dumps(ai.get("entities", {})),
                    "summary": ai.get("summary", ""), "status": "done"})
        save_result(row)
        return {"job_id": job_id, "status": "done",
                "document_type": row["document_type"],
                "key_points": ai.get("key_points", []),
                "entities": ai.get("entities", {}),
                "summary": row["summary"], "page_count": pages,
                "extraction_method": method, "volume_path": volume_path,
                "stored_in": TABLE, "processed_by": "databricks-pdf-agent"}
    except Exception as e:
        row["summary"] = f"Error: {e}"
        try:
            save_result(row)
        except Exception:
            pass
        raise


mcp = FastMCP("databricks-pdf-agent", host="0.0.0.0",
              stateless_http=True, json_response=True)


@mcp.tool()
def process_pdf_document(job_id: str, file_name: str, file_url: str) -> dict:
    """Process a PDF on Databricks: download it from a temporary S3 link, extract text
    (with OCR for scanned pages), enrich it (document type, key points, entities),
    summarize it, and store the result in a Unity Catalog table. Returns the result."""
    url = urlparse(file_url)
    if url.scheme != "https" or not (url.hostname or "").endswith(".amazonaws.com"):
        raise ValueError("file_url must be an https link to Amazon S3")
    r = requests.get(file_url, timeout=60)
    r.raise_for_status()
    if len(r.content) > MAX_BYTES:
        raise ValueError("File is larger than 10 MB")
    return process_pdf(job_id, file_name, r.content)


@mcp.tool()
def get_pdf_result(job_id: str) -> dict:
    """Look up the stored processing result for a job ID in the Unity Catalog table."""
    res = run_sql(f"""
      SELECT job_id, file_name, page_count, document_type, key_points, entities,
             summary, status, processed_by, CAST(created_at AS STRING)
      FROM {TABLE} WHERE job_id = :job_id ORDER BY created_at DESC LIMIT 1""",
      {"job_id": job_id})
    rows = (res.result.data_array if res.result else None) or []
    if not rows:
        return {"job_id": job_id, "status": "not_found"}
    cols = ["job_id", "file_name", "page_count", "document_type", "key_points",
            "entities", "summary", "status", "processed_by", "created_at"]
    return dict(zip(cols, rows[0]))


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse({"status": "ok", "server": "databricks-pdf-agent"})

@mcp.custom_route("/selftest", methods=["GET"])
async def selftest(request):
    checks = {}
    try:
        run_sql(f"SELECT COUNT(*) FROM {TABLE}", {})
        checks["table_access"] = "ok"
    except Exception as e:
        checks["table_access"] = f"FAILED: {e}"
    try:
        list(w.files.list_directory_contents(VOLUME_PATH))
        checks["volume_access"] = "ok"
    except Exception as e:
        checks["volume_access"] = f"FAILED: {e}"
    try:
        llm.chat.completions.create(
            model=LLM_ENDPOINT,
            messages=[{"role": "user", "content": "Reply with OK"}],
            max_tokens=5)
        checks["model_access"] = "ok"
    except Exception as e:
        checks["model_access"] = f"FAILED: {e}"
    return JSONResponse(checks)

if __name__ == "__main__":
    port = int(os.getenv("DATABRICKS_APP_PORT", "8000"))
    uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=port)