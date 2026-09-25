import urllib.parse
import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


class AwsSigV4Auth(httpx.Auth):
    """Signs every outgoing HTTP request with the caller's AWS credentials."""
    requires_request_body = True

    def __init__(self, region, service="bedrock-agentcore"):
        self.region = region
        self.service = service
        self.session = boto3.Session()

    def auth_flow(self, request):
        creds = self.session.get_credentials().get_frozen_credentials()
        headers = {"host": request.url.host}
        if "content-type" in request.headers:
            headers["content-type"] = request.headers["content-type"]
        aws_req = AWSRequest(method=request.method, url=str(request.url),
                             data=request.content or b"", headers=headers)
        SigV4Auth(creds, self.service, self.region).add_auth(aws_req)
        for name in ("Authorization", "X-Amz-Date", "X-Amz-Security-Token"):
            if name in aws_req.headers:
                request.headers[name] = aws_req.headers[name]
        yield request


def agentcore_mcp_url(runtime_arn, region):
    encoded = urllib.parse.quote(runtime_arn, safe="")
    return (f"https://bedrock-agentcore.{region}.amazonaws.com"
            f"/runtimes/{encoded}/invocations?qualifier=DEFAULT")
