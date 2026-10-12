from travel_concierge.agents.llm import run_agent_json
from travel_concierge.agents.search import SEARCH_TOOL, web_search
from travel_concierge.prompts import get_prompt


def run(origin, destinations, log=None):
    system = get_prompt("FLIGHT_AGENT", origin=origin, destinations=", ".join(destinations))
    return run_agent_json(system, "Find the flight options now.", [SEARCH_TOOL], {"web_search": web_search}, log)
