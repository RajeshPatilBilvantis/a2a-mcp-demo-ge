import asyncio, os, sys
from datetime import timedelta
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from aws_sigv4 import AwsSigV4Auth, agentcore_mcp_url

async def main(runtime_arn, bucket, key, job_id):
    region = os.environ.get("AWS_REGION", "us-east-1")
    url = agentcore_mcp_url(runtime_arn, region)

    async with streamablehttp_client(url, auth=AwsSigV4Auth(region),
                                     timeout=timedelta(seconds=60)) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Tools offered by AWS DOCX MCP server:")
            for t in tools.tools:
                print(f"  - {t.name}")

            print(f"\nCalling process_docx_document for job {job_id} ...")
            result = await session.call_tool(
                "process_docx_document",
                {"job_id": job_id, "file_name": key.split("/")[-1],
                 "s3_bucket": bucket, "s3_key": key},
                read_timeout_seconds=timedelta(seconds=180))

            if result.isError:
                print("Tool returned an error:")
            print(result.content[0].text if result.content else result)

if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:5]))
