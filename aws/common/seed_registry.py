import json, os
import boto3

ddb = boto3.resource("dynamodb")
table = ddb.Table(os.environ["REGISTRY_TABLE"])
sm = boto3.client("secretsmanager")
dbx = json.loads(sm.get_secret_value(SecretId=os.environ["DBX_SECRET"])["SecretString"])

cards = [
    {
        "agent_id": "databricks-pdf-agent",
        "name": "Databricks PDF Agent",
        "cloud": "Databricks",
        "description": "Extracts text from PDF documents (with OCR for scanned pages), enriches "
                       "them and summarizes them. Stores results in a Unity Catalog table.",
        "accepts": [".pdf"],
        "protocol": "MCP (streamable HTTP)",
        "endpoint": dbx["mcp_url"],
        "auth": {"type": "databricks-oauth", "secret": os.environ["DBX_SECRET"]},
        "tool": "process_pdf_document",
        "input_style": "presigned_url",
    },
    {
        "agent_id": "aws-docx-agent",
        "name": "AWS DOCX Agent",
        "cloud": "AWS",
        "description": "Extracts paragraphs and tables from Word documents, enriches them and "
                       "summarizes them with Claude on Amazon Bedrock. Stores results in S3.",
        "accepts": [".docx"],
        "protocol": "MCP (streamable HTTP)",
        "endpoint": os.environ["DOCX_MCP_ARN"],
        "auth": {"type": "aws-sigv4"},
        "tool": "process_docx_document",
        "input_style": "s3_location",
    },
]

for card in cards:
    table.put_item(Item=card)
    print(f"Registered: {card['agent_id']} ({card['cloud']}) accepts {card['accepts']}")
