import base64, json, os, urllib.parse, urllib.request
import boto3

def get_dbx_config():
    sm = boto3.client("secretsmanager")
    secret_id = os.environ.get("DBX_SECRET", "a2a/databricks")
    return json.loads(sm.get_secret_value(SecretId=secret_id)["SecretString"])

def get_dbx_token(cfg):
    data = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "scope": "all-apis"}).encode()
    req = urllib.request.Request(f"{cfg['host']}/oidc/v1/token", data=data, method="POST")
    basic = base64.b64encode(f"{cfg['client_id']}:{cfg['client_secret']}".encode()).decode()
    req.add_header("Authorization", f"Basic {basic}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())["access_token"]
