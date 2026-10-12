import itertools

from travel_concierge.agents import flight, itinerary
from travel_concierge.agents.llm import extract_json, run_agent
from travel_concierge.config import NIGHTS
from travel_concierge.formatting import to_int
from travel_concierge.prompts import get_prompt

TOOLS = [
    {"type": "function", "function": {
        "name": "delegate_to_flight_agent",
        "description": "Ask the flight route expert for optimized domestic flights from the origin to the destinations.",
        "parameters": {"type": "object", "properties": {
            "origin": {"type": "string"},
            "destinations": {"type": "array", "items": {"type": "string"}}},
            "required": ["origin", "destinations"]}}},
    {"type": "function", "function": {
        "name": "delegate_to_itinerary_agent",
        "description": "Ask the itinerary/hotel expert for itineraries and 3+ star hotels in the destinations.",
        "parameters": {"type": "object", "properties": {
            "destinations": {"type": "array", "items": {"type": "string"}}},
            "required": ["destinations"]}}},
]


def run(city, log=None):
    """Concierge delegates; returns option rows sorted cheapest total trip first (all INR)."""
    results = {}

    def do_flights(origin, destinations):
        results["flights"] = flight.run(origin, destinations, log).get("flights", [])
        return str(results["flights"])

    def do_stays(destinations):
        results["stays"] = itinerary.run(destinations, log).get("stays", [])
        return str(results["stays"])

    reply = run_agent(get_prompt("CONCIERGE", city=city), "Plan trip options from %s." % city, TOOLS,
                      {"delegate_to_flight_agent": do_flights, "delegate_to_itinerary_agent": do_stays}, log)
    if not results:  # concierge answered without delegating, e.g. a non-Indian city
        try:
            msg = extract_json(reply).get("error")
        except ValueError:
            msg = None
        raise ValueError(msg or "Please enter a city in India.")
    if not results.get("flights") or not results.get("stays"):
        raise RuntimeError("Concierge did not obtain both flight and hotel results")
    rows = combine(results["flights"], results["stays"])
    if not rows:
        raise RuntimeError("No complete flight + hotel combinations with prices were found. Try again.")
    return rows


def combine(flights, stays, nights=NIGHTS):
    combos = []
    stays = [s for s in stays if _stars(s) >= 3 and to_int(s.get("approx_price_per_night_inr"))]
    flights = [f for f in flights if to_int(f.get("approx_price_inr"))]
    for dest in sorted({f["city"] for f in flights} & {s["city"] for s in stays}):
        for f, s in itertools.product([f for f in flights if f["city"] == dest],
                                      [s for s in stays if s["city"] == dest]):
            fare, night = to_int(f["approx_price_inr"]), to_int(s["approx_price_per_night_inr"])
            combos.append({
                "City": dest,
                "Flight Route": f.get("route", ""), "Airline": f.get("airline", ""),
                "Stops": f.get("stops", ""), "Duration": f.get("duration", ""),
                "Flight Cost (INR)": fare,
                "Hotel": s.get("hotel", ""), "Stars": _stars(s),
                "Hotel/Night (INR)": night, "Nights": nights, "Hotel Cost (INR)": night * nights,
                "Total Trip Cost (INR)": fare + night * nights,
                "Itinerary Highlights": s.get("itinerary", ""),
            })
    combos.sort(key=lambda r: r["Total Trip Cost (INR)"])  # cheapest first, then IDs
    return [{"Option ID": "OPT-%02d" % i, **r} for i, r in enumerate(combos, 1)]


def _stars(s):
    try:
        return int(float(s.get("stars", 0)))
    except (TypeError, ValueError):
        return 0
