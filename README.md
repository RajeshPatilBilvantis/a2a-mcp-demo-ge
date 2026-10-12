# Travel Concierge

A Streamlit app for **domestic India** trips. Enter your current city and email. A Travel Concierge agent delegates to two specialist agents, builds a table of flight × hotel options across top-tier Indian cities (all costs in INR, cheapest total trip first), saves it to Excel, and emails it to you. Click **Approve** next to an option in the email to get a **simulated** booking and a confirmation reply in the same thread.

## Agents

| Agent | Role |
|---|---|
| Travel Concierge | Receives the request, picks ~5 destination cities, delegates, merges results |
| Flight Route Expert | Only finds optimized flight routes/fares from your city |
| Itinerary & Hotel Expert | Only finds itineraries and hotels rated 3 stars or higher |

All prompts are stored in `prompts.docx` and read at runtime. Edit them in Word; no code change needed.

## Setup

1. Create the environment and install dependencies:
   ```
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in:
   - `DEEPSEEK_API_KEY`: your DeepSeek API key
   - `GMAIL_ADDRESS`: the Gmail account that sends the emails
   - `GMAIL_APP_PASSWORD`: a Gmail app password (requires 2-step verification)
3. In Gmail settings, enable **IMAP** (needed to read the approval reply).
4. (Optional) Regenerate the prompts file: `.venv/bin/python create_prompts_docx.py`. This overwrites any edits to `prompts.docx`.

## Run

```
.venv/bin/streamlit run app.py
```

## Usage

1. Enter an Indian city and your email, then click **Find travel options**.
2. The table appears cheapest first (flight + hotel × 3 nights, in ₹), an Excel file is saved in `outputs/`, and the same table is emailed with the Excel attached.
3. In the email, click the green **Approve** button on the option you want. It opens a pre-filled reply (`APPROVE OPT-03`); press Send.
4. In the app, click **Check Gmail for approval**. The app reads the reply, simulates the booking (reference `SIM-XXXXXX`), adds a *Booking* sheet to the Excel, and replies in the original thread with the booking details and updated Excel. No real booking or payment is made.

## Project layout

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI |
| `agents/concierge.py` | Concierge agent, delegation and flight × hotel combining |
| `agents/flight_agent.py`, `agents/itinerary_agent.py` | Specialist agents |
| `agents/llm.py` | DeepSeek client and tool-calling loop |
| `agents/search_tool.py` | Web search tool (DuckDuckGo) used by the agents |
| `prompt_loader.py`, `create_prompts_docx.py`, `prompts.docx` | Prompts in Word |
| `excel_writer.py` | Builds and styles the Excel output |
| `emailer.py` | Sends email via Gmail SMTP |
| `reply_reader.py` | Reads the Approve reply via Gmail IMAP |
| `booking_sim.py` | Simulated booking + threaded confirmation reply |
| `fmt.py` | INR formatting and price parsing |
| `store.py` | Saves each request to `outputs/<token>.json` |

## Notes

- Prices come from web search snippets and are approximate. Verify before booking anything real.
- Never commit `.env`; it is already in `.gitignore`.
- DeepSeek has no built-in web search, so the agents use a search tool; results can vary between runs.
