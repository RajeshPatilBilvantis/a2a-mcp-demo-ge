import json
from openai import OpenAI

from travel_concierge import config

MODEL = config.LLM_MODEL
MAX_TURNS = config.LLM_MAX_TURNS


def client():
    return OpenAI(api_key=config.deepseek_key(), base_url=config.LLM_BASE_URL)


def extract_json(text):
    """Parse a JSON object from model text, tolerating code fences / surrounding prose."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object in model reply")
    return json.loads(text[start:end + 1])


def run_agent(system_prompt, user_msg, tools=None, handlers=None, log=None):
    """Tool-calling loop. tools = OpenAI function schemas, handlers = {name: callable(**args)->str}."""
    c = client()
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_msg}]
    for _ in range(MAX_TURNS):
        kwargs = {"model": MODEL, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        msg = c.chat.completions.create(**kwargs).choices[0].message
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            return msg.content or ""
        for call in msg.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
                if log:
                    log("%s(%s)" % (name, ", ".join("%s=%s" % kv for kv in args.items())))
                result = handlers[name](**args)
            except Exception as e:  # report tool errors back to the model
                result = "Error: %s" % e
            messages.append({"role": "tool", "tool_call_id": call.id, "content": str(result)})
    return messages[-1].get("content", "") or ""


def run_agent_json(system_prompt, user_msg, tools=None, handlers=None, log=None):
    """run_agent + JSON validation with one retry."""
    reply = run_agent(system_prompt, user_msg, tools, handlers, log)
    try:
        return extract_json(reply)
    except ValueError:
        reply = run_agent(system_prompt, user_msg + "\n\nReturn ONLY valid JSON, no prose.", tools, handlers, log)
        return extract_json(reply)
