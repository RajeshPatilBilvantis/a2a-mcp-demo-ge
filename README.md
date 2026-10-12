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

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env     # then fill in your keys
```
Fill in `.env`:
- `DEEPSEEK_API_KEY`: your DeepSeek API key
- `GMAIL_ADDRESS`: the Gmail account that sends the emails
- `GMAIL_APP_PASSWORD`: a Gmail app password (requires 2-step verification)

Also enable **IMAP** in Gmail settings (needed to read the approval reply).

## Run

```
.venv/bin/streamlit run app.py
```

Regenerate `data/prompts.docx` from defaults (overwrites your edits): `.venv/bin/python -m scripts.create_prompts_docx`

## Usage

1. Enter an Indian city and your email, then click **Find travel options**.
2. The table appears cheapest first (flight + hotel × 3 nights, in ₹), an Excel file is saved in `outputs/`, and the same table is emailed with the Excel attached.
3. In the email, click the green **Approve** button on the option you want. It opens a pre-filled reply (`APPROVE OPT-03`); press Send.
4. In the app, click **Check Gmail for approval**. The app reads the reply, simulates the booking (reference `SIM-XXXXXX`), adds a *Booking* sheet to the Excel, and replies in the original thread with the booking details and updated Excel. No real booking or payment is made.

## Project structure

```
.
├── app.py                    # Streamlit UI (entry point)
├── requirements.txt
├── .env.example              # required secrets (copy to .env)
├── data/
│   └── prompts.docx          # all agent/email prompts, editable in Word
├── outputs/                  # generated Excel + request state (git-ignored)
├── scripts/
│   └── create_prompts_docx.py  # generates data/prompts.docx
└── travel_concierge/
    ├── config.py             # paths, env/secrets, settings (NIGHTS, model)
    ├── prompts.py            # reads prompts from the Word document
    ├── formatting.py         # INR formatting and price parsing
    ├── storage.py            # per-request state in outputs/<token>.json
    ├── agents/
    │   ├── llm.py            # DeepSeek client + tool-calling loop
    │   ├── search.py         # web search tool
    │   ├── concierge.py      # orchestrator: delegates, combines, sorts
    │   ├── flight.py         # flight route expert
    │   └── itinerary.py      # itinerary + 3★+ hotel expert
    └── services/
        ├── excel.py          # Excel output + Booking sheet
        ├── emailer.py        # Gmail SMTP, HTML table with Approve buttons
        ├── reply_reader.py   # Gmail IMAP: finds the APPROVE reply
        └── booking.py        # simulated booking + threaded confirmation
```

## Notes

- Prices come from web search snippets and are approximate. Verify before booking anything real.
- Never commit `.env`; it is already in `.gitignore`.
- DeepSeek has no built-in web search, so the agents use a search tool; results can vary between runs.
