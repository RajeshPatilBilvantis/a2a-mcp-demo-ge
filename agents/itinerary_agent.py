from agents.llm import run_agent_json
from agents.search_tool import SEARCH_TOOL, web_search
from prompt_loader import get_prompt


def run(destinations, log=None):
    system = get_prompt("ITINERARY_AGENT", destinations=", ".join(destinations))
    return run_agent_json(system, "Find itineraries and hotels now.", [SEARCH_TOOL], {"web_search": web_search}, log)
