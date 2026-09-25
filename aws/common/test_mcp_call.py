import asyncio, json, sys
from datetime import timedelta
import boto3
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from dbx_auth import get_dbx_config, get_dbx_token

async def main(bucket, key, job_id):
    cfg = get_dbx_config()
    token = get_dbx_token(cfg)
    file_url = boto3.client("s3").generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=600)

    async with streamablehttp_client(
            cfg["mcp_url"],
            headers={"Authorization": f"Bearer {token}"},
            timeout=timedelta(seconds=60)) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools offered by Databricks MCP server:")
            for t in tools.tools:
                print(f"  - {t.name}")

            print(f"\nCalling process_pdf_document for job {job_id} ...")
            result = await session.call_tool(
                "process_pdf_document",
                {"job_id": job_id, "file_name": key.split("/")[-1], "file_url": file_url},
                read_timeout_seconds=timedelta(seconds=180))

            if result.isError:
                print("Tool returned an error:")
            print(result.content[0].text if result.content else result)

if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3]))
