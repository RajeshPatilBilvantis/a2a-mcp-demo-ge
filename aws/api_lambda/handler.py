import base64, json, os, re, time, uuid, urllib.parse
from decimal import Decimal
import boto3
from botocore.config import Config

REGION     = os.environ.get("AWS_REGION", "us-east-1")
BUCKET     = os.environ["BUCKET"]
JOBS_TABLE = os.environ["JOBS_TABLE"]
ORCH_ARN   = os.environ["ORCH_ARN"]

ALLOWED = {
    ".pdf":  "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

s3        = boto3.client("s3", region_name=REGION, config=Config(signature_version="s3v4"))
agentcore = boto3.client("bedrock-agentcore", region_name=REGION,
                         config=Config(read_timeout=300, retries={"max_attempts": 0}))
jobs      = boto3.resource("dynamodb", region_name=REGION).Table(JOBS_TABLE)


def plain(obj):
    if isinstance(obj, Decimal):
        return int(obj)
    if isinstance(obj, list):
        return [plain(x) for x in obj]
    if isinstance(obj, dict):
        return {k: plain(v) for k, v in obj.items()}
    return obj


def respond(status, body):
    return {"statusCode": status, "headers": {"content-type": "application/json"},
            "body": json.dumps(plain(body))}


def add_event(job_id, message, **fields):
    now = int(time.time())
    fields["updated_at"] = now
    sets = ", ".join(f"#{k} = :{k}" for k in fields)
    jobs.update_item(
        Key={"job_id": job_id},
        UpdateExpression=f"SET events = list_append(if_not_exists(events, :empty), :e), {sets}",
        ExpressionAttributeNames={f"#{k}": k for k in fields},
        ExpressionAttributeValues={":e": [{"t": now, "msg": message}], ":empty": [],
                                   **{f":{k}": v for k, v in fields.items()}})


def run_orchestrator(job):
    resp = agentcore.invoke_agent_runtime(
        agentRuntimeArn=ORCH_ARN, qualifier="DEFAULT",
        runtimeSessionId=f"job-{job['job_id']}-{uuid.uuid4().hex}",
        contentType="application/json", accept="application/json",
        payload=json.dumps({"job_id": job["job_id"], "bucket": BUCKET,
                            "key": job["s3_key"], "file_name": job["file_name"]}).encode())
    return json.loads(resp["response"].read())


def safe_name(name):
    name = os.path.basename(name or "")
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)[:100]


# ---------- HTTP (Function URL) ----------

def create_upload(body):
    file_name = safe_name(body.get("file_name"))
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in ALLOWED:
        return respond(400, {"error": "Only .pdf and .docx files are supported"})
    mode = "sync" if body.get("mode") == "sync" else "async"
    job_id = uuid.uuid4().hex[:12]
    key = f"uploads/{job_id}/{file_name}"
    jobs.put_item(Item={"job_id": job_id, "file_name": file_name, "s3_key": key,
                        "mode": mode, "status": "awaiting_upload",
                        "created_at": int(time.time()), "updated_at": int(time.time()),
                        "events": [{"t": int(time.time()), "msg": f"Job created ({mode} mode)"}]})
    url = s3.generate_presigned_url(
        "put_object", Params={"Bucket": BUCKET, "Key": key, "ContentType": ALLOWED[ext]},
        ExpiresIn=300)
    return respond(200, {"job_id": job_id, "upload_url": url,
                         "content_type": ALLOWED[ext], "mode": mode})


def process_sync(body):
    job = jobs.get_item(Key={"job_id": body.get("job_id", "")}).get("Item")
    if not job:
        return respond(404, {"error": "Job not found"})
    try:
        s3.head_object(Bucket=BUCKET, Key=job["s3_key"])
    except Exception:
        return respond(409, {"error": "File has not been uploaded yet"})
    add_event(job["job_id"], "Sync request: API calling orchestrator and waiting")
    try:
        return respond(200, run_orchestrator(job))
    except Exception as e:
        add_event(job["job_id"], f"Failed: {str(e)[:200]}", status="failed")
        return respond(500, {"error": str(e)})


def get_status(params):
    job = jobs.get_item(Key={"job_id": (params or {}).get("job_id", "")}).get("Item")
    if not job:
        return respond(404, {"error": "Job not found"})
    if "result" in job:
        job["result"] = json.loads(job["result"])
    return respond(200, job)


def handle_http(event):
    method = event["requestContext"]["http"]["method"]
    path = event.get("rawPath", "/")
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode()
    try:
        body = json.loads(body)
    except ValueError:
        body = {}
    if method == "POST" and path == "/upload-url":
        return create_upload(body)
    if method == "POST" and path == "/process":
        return process_sync(body)
    if method == "GET" and path == "/status":
        return get_status(event.get("queryStringParameters"))
    return respond(404, {"error": f"No route for {method} {path}"})


# ---------- S3 upload trigger ----------

def handle_s3(event):
    for record in event["Records"]:
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        parts = key.split("/")
        if len(parts) < 3:
            continue
        job_id, file_name = parts[1], parts[-1]
        job = jobs.get_item(Key={"job_id": job_id}).get("Item")
        if not job:
            job = {"job_id": job_id, "file_name": file_name, "s3_key": key, "mode": "async",
                   "created_at": int(time.time())}
            jobs.put_item(Item={**job, "status": "uploaded", "events": []})
        add_event(job_id, "Upload detected by S3 event trigger", status="uploaded")
        if job.get("mode") == "sync":
            continue
        add_event(job_id, "Async mode: trigger started the orchestrator", status="queued")
        try:
            run_orchestrator(job)
        except Exception as e:
            add_event(job_id, f"Failed: {str(e)[:200]}", status="failed")
    return {"ok": True}


def handler(event, context):
    if "Records" in event and event["Records"][0].get("eventSource") == "aws:s3":
        return handle_s3(event)
    return handle_http(event)
