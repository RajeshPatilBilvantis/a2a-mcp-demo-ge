# Plan: Change request v2 — India-only, INR, cheapest-first, Approve button

## Context
The app (Streamlit + DeepSeek agents, prompts in `prompts.docx`, Excel + email output, simulated booking) works end to end. The user wants four changes: domestic (India) trips only, all costs in INR, table sorted cheapest total trip first, and an **Approve** button per table row that replaces the email-reply booking flow.

## Decisions
- Approve **replaces** Gmail reply reading: clicking Approve on a row runs the simulated booking and sends the confirmation email as a reply in the original email thread (same subject + `In-Reply-To`/`References` headers where available). IMAP reading and the "Check Gmail for reply" button are removed.
- "Overall travel expense" = flight price (round trip) + hotel price per night × `NIGHTS` (default 3, constant in `agents/concierge.py`, shown in the table as "Nights"). Sort ascending by this total.

## Changes

### 1. India only (domestic)
- `prompts.docx` via `create_prompts_docx.py`: `CONCIERGE` — choose 5 top-tier **Indian** cities (exclude the user's own city; no international); `FLIGHT_AGENT` — domestic Indian routes only, Indian airlines (IndiGo, Air India, Akasa, SpiceJet, Vistara-Air India), IATA codes; `ITINERARY_AGENT` — Indian destinations only.
- `app.py`: if the entered city is not in India, the concierge reports it. Add a light check: concierge/flight prompt returns `{"error": "not an Indian city"}` and the UI shows it (no hard-coded city list).

### 2. INR only
- Agent prompts require numeric fields: `approx_price_inr` (flight, integer rupees) and `approx_price_per_night_inr` (integer). Drop the `currency` field from the JSON schemas. Prompts instruct: if a source quotes another currency, convert to INR approximately.
- `agents/concierge.py:combine`: parse values to ints (strip `₹`, commas), skip rows with missing prices, compute `Total Trip Cost (INR)` = flight + hotel × NIGHTS. Column names get "(INR)" suffix. UI and email format values as `₹12,345` (Indian digit grouping helper in `agents/concierge.py` or a small `fmt.py`); Excel keeps numeric cells with `₹#,##0` number format so sorting/filtering works.

### 3. Cheapest first
- `combine` sorts rows by `Total Trip Cost (INR)` ascending **before** assigning Option IDs, so OPT-01 is the cheapest. Same ordering flows to the UI, Excel and email (they all use the rows list).

### 4. Approve button column
- `app.py`: replace `st.dataframe` with a per-row layout (header row + one `st.columns` row per option) ending in an **Approve** button column (`st.button("Approve", key=option_id)`). `st.dataframe` cannot hold buttons, so rows are rendered manually; keep the Excel download button.
- On click: `booking_sim.simulate(data, option_id)` (reused as is) → creates `SIM-XXXXXX` reference, adds Booking sheet, sends confirmation. After booking, buttons for all rows are disabled and the booked row shows "✅ Approved".
- `emailer.send`: add optional `thread` arg (`message_id`). The original options email stores its `Message-ID` in `outputs/<token>.json`; the confirmation sets `In-Reply-To`/`References` and subject `Re: <original subject>` so it appears as a reply in the thread.
- The options email text (`EMAIL_TEMPLATE` in docx) changes from "reply with Option ID" to "approve an option in the app; you'll get a confirmation reply here".
- Remove `reply_reader.py`, `REPLY_PARSER` prompt, IMAP mentions; update `README.md` (usage, setup no longer needs IMAP, INR/India notes).

## Files touched
`create_prompts_docx.py` (+ regenerate `prompts.docx`), `agents/concierge.py`, `agents/flight_agent.py`/`itinerary_agent.py` (no logic change, prompts only), `excel_writer.py` (INR formats, total column), `emailer.py` (threading, ₹ formatting), `booking_sim.py` (thread reply), `store.py` (store message id), `app.py` (row buttons), delete `reply_reader.py`, `README.md`.

## Verification
1. Regenerate docx; confirm sections load and `REPLY_PARSER` is gone.
2. Offline test of `combine`: mixed-format price strings (`₹4,500`, `4500`), assert INR ints, ascending totals, OPT-01 cheapest, rows with missing prices skipped.
3. Run `streamlit run app.py` with city "Mumbai": all destinations Indian, all costs ₹, table cheapest first, Excel numeric `₹` format and same order, email received.
4. Click Approve on a row: booking reference shown, Booking sheet added, confirmation lands in the same Gmail thread as a reply; other buttons disabled; clicking again doesn't duplicate.
5. Enter a non-Indian city (e.g. "London"): friendly error, no email sent.
