import asyncio, concurrent.futures, json, os, time
from datetime import timedelta
import boto3
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent, tool
from strands.models import BedrockModel
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from dbx_auth import get_dbx_config, get_dbx_token
from aws_sigv4 import AwsSigV4Auth, agentcore_mcp_url

REGION         = os.environ.get("AWS_REGION", "us-east-1")
MODEL_ID       = os.environ.get("MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
JOBS_TABLE     = os.environ.get("JOBS_TABLE", "a2a-jobs")
REGISTRY_TABLE = os.environ.get("REGISTRY_TABLE", "a2a-agent-registry")

ddb      = boto3.resource("dynamodb", region_name=REGION)
jobs     = ddb.Table(JOBS_TABLE)
registry = ddb.Table(REGISTRY_TABLE)
s3       = boto3.client("s3", region_name=REGION)
app      = BedrockAgentCoreApp()

SYSTEM_PROMPT = """You are the orchestrator agent in a multi-cloud network of AI agents.
For each document job:
1. Call list_registered_agents to discover which agents are available.
2. Pick the agent whose 'accepts' list contains the file's extension.
3. Call delegate_to_agent with that agent_id exactly once.
4. Reply with one short sentence naming the agent you chose and why.
Never summarize the document yourself."""


def update_job(job_id, **fields):
    fields["updated_at"] = int(time.time())
    jobs.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
        ExpressionAttributeNames={f"#{k}": k for k in fields},
        ExpressionAttributeValues={f":{k}": v for k, v in fields.items()})


def add_event(job_id, message):
    now = int(time.time())
    jobs.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET events = list_append(if_not_exists(events, :empty), :e), updated_at = :t",
        ExpressionAttributeValues={":e": [{"t": now, "msg": message}], ":empty": [], ":t": now})


async def _call_mcp(card, tool_name, args):
    if card["auth"]["type"] == "databricks-oauth":
        token = get_dbx_token(get_dbx_config())
        client = streamablehttp_client(card["endpoint"],
                                       headers={"Authorization": f"Bearer {token}"},
                                       timeout=timedelta(seconds=60))
    else:
        client = streamablehttp_client(agentcore_mcp_url(card["endpoint"], REGION),
                                       auth=AwsSigV4Auth(REGION),
                                       timeout=timedelta(seconds=60))
    async with client as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = [t.name for t in (await session.list_tools()).tools]
            if tool_name not in tools:
                raise RuntimeError(f"Tool {tool_name} not offered; available: {tools}")
            result = await session.call_tool(tool_name, args,
                                             read_timeout_seconds=timedelta(seconds=240))
            text = result.content[0].text if result.content else "{}"
            if result.isError:
                raise RuntimeError(text)
            return tools, json.loads(text)


def call_mcp(card, tool_name, args):
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, _call_mcp(card, tool_name, args)).result()


def run_job(job):
    job_id = job["job_id"]
    outcome = {}

    @tool
    def list_registered_agents() -> str:
        """List all AI agents registered in the agent registry: their IDs, the cloud
        they run on, what they do, and which file types they accept."""
        cards = registry.scan()["Items"]
        add_event(job_id, f"Orchestrator discovered {len(cards)} agents in the registry")
        return json.dumps([{k: c[k] for k in ("agent_id", "name", "cloud", "description", "accepts")}
                           for c in cards], default=str)

    @tool
    def delegate_to_agent(agent_id: str) -> str:
        """Send the current document job to the chosen agent over MCP and wait for its result."""
        card = registry.get_item(Key={"agent_id": agent_id}).get("Item")
        if not card:
            return f"Unknown agent {agent_id}. Choose one from the registry."
        ext = os.path.splitext(job["file_name"])[1].lower()
        if ext not in card["accepts"]:
            return f"Agent {agent_id} does not accept {ext} files. Choose another agent."

        update_job(job_id, status="processing", assigned_agent=agent_id,
                   assigned_cloud=card["cloud"])
        add_event(job_id, f"Delegated to {agent_id} on {card['cloud']} via MCP")

        if card["input_style"] == "presigned_url":
            url = s3.generate_presigned_url(
                "get_object", Params={"Bucket": job["bucket"], "Key": job["key"]}, ExpiresIn=900)
            args = {"job_id": job_id, "file_name": job["file_name"], "file_url": url}
        else:
            args = {"job_id": job_id, "file_name": job["file_name"],
                    "s3_bucket": job["bucket"], "s3_key": job["key"]}

        tools, result = call_mcp(card, card["tool"], args)
        add_event(job_id, f"{agent_id} offered tools {tools}; called {card['tool']}")
        outcome["agent_id"] = agent_id
        outcome["result"] = result
        return f"Agent {agent_id} finished. Document type: {result.get('document_type')}."

    agent = Agent(model=BedrockModel(model_id=MODEL_ID, region_name=REGION),
                  tools=[list_registered_agents, delegate_to_agent],
                  system_prompt=SYSTEM_PROMPT, callback_handler=None)
    reply = str(agent(f"New document job. job_id={job_id}, file_name={job['file_name']}. "
                      f"Route it to the right agent."))

    if "result" not in outcome:
        update_job(job_id, status="failed", error=reply[:1000])
        add_event(job_id, "Orchestrator could not complete the job")
        return {"job_id": job_id, "status": "failed", "error": reply}

    result = outcome["result"]
    update_job(job_id, status="done", summary=result.get("summary", ""),
               result=json.dumps(result), orchestrator_note=reply[:500])
    add_event(job_id, "Result returned to the orchestrator")
    return {"job_id": job_id, "status": "done", "agent": outcome["agent_id"],
            "orchestrator_note": reply, "result": result}


@app.entrypoint
def invoke(payload):
    job = {"job_id": payload["job_id"], "bucket": payload["bucket"], "key": payload["key"]}
    job["file_name"] = payload.get("file_name") or job["key"].split("/")[-1]
    update_job(job["job_id"], status="routing", file_name=job["file_name"],
               s3_bucket=job["bucket"], s3_key=job["key"])
    add_event(job["job_id"], "Orchestrator agent received the job")
    try:
        return run_job(job)
    except Exception as e:
        update_job(job["job_id"], status="failed", error=str(e)[:1000])
        add_event(job["job_id"], f"Failed: {str(e)[:200]}")
        return {"job_id": job["job_id"], "status": "failed", "error": str(e)}


if __name__ == "__main__":
    app.run()
