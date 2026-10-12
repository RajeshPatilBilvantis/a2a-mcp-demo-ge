from ddgs import DDGS

SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current travel information (flights, fares, hotels, attractions).",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
}


def web_search(query):
    results, err = [], None
    for _ in range(3):  # backends are occasionally flaky
        try:
            results = DDGS().text(query, max_results=6)
            break
        except Exception as e:
            err = e
    else:
        return "Search failed: %s" % err
    return "\n\n".join("%s\n%s\n%s" % (r.get("title"), r.get("body"), r.get("href")) for r in results) or "No results"
