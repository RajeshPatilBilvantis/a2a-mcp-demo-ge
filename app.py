import re

import pandas as pd
import streamlit as st

from travel_concierge import storage as store
from travel_concierge.agents import concierge
from travel_concierge.config import NIGHTS
from travel_concierge.formatting import inr
from travel_concierge.prompts import get_prompt
from travel_concierge.services import booking, emailer, excel, reply_reader

st.set_page_config(page_title="Travel Concierge", page_icon="✈️", layout="wide")
st.title("✈️ Travel Concierge")
st.caption("Domestic India trips. Enter your city and email; agents find flights + 3★+ hotels (all costs in ₹, cheapest first).")

with st.form("trip"):
    city = st.text_input("Your current city (India)", placeholder="e.g. Mumbai")
    email_addr = st.text_input("Your email", placeholder="you@gmail.com")
    go = st.form_submit_button("Find travel options")

if go:
    if not city.strip() or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_addr.strip()):
        st.error("Please enter a city and a valid email.")
    else:
        try:
            with st.status("Concierge is working...", expanded=True) as status:
                rows = concierge.run(city.strip(), log=lambda m: st.write("🔎 " + m))
                data = store.new_request(city.strip(), email_addr.strip(), rows)
                excel.write_options(data)
                data["subject"] = "Your travel options from %s [%s]" % (data["city"], data["token"])
                data["message_id"] = emailer.send(
                    data["email"], data["subject"],
                    get_prompt("EMAIL_TEMPLATE", city=data["city"], nights=NIGHTS),
                    rows, store.xlsx_path(data), approve=True)
                store.save(data)
                status.update(label="Done - emailed to %s" % data["email"], state="complete")
            st.session_state["token"] = data["token"]
        except ValueError as e:
            st.error(str(e))
        except Exception as e:
            st.error("Failed: %s" % e)

if "token" in st.session_state:
    data = store.load(st.session_state["token"])
    booked = data.get("booking")
    st.subheader("Options from %s (cheapest first) - request %s" % (data["city"], data["token"]))

    table = pd.DataFrame(data["rows"])
    for col in [c for c in table.columns if "(INR)" in c]:
        table[col] = table[col].map(inr)
    table["Status"] = ["✅ Approved" if booked and booked["option"]["Option ID"] == r["Option ID"] else ""
                       for r in data["rows"]]
    st.dataframe(table, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Approval")
    st.write("Click the green **Approve** button next to an option in the email, send the pre-filled reply, "
             "then click below.")
    if st.button("Check Gmail for approval", disabled=bool(booked)):
        try:
            oid = reply_reader.find_approval(data["token"], data["email"], {r["Option ID"] for r in data["rows"]})
            if not oid:
                st.info("No approval reply found yet.")
            else:
                with st.status("Approval received for %s - booking (simulated)..." % oid, expanded=True) as status:
                    booking.simulate(data, oid, step=lambda m: st.write("⏳ " + m))
                    status.update(label="Booked - confirmation emailed", state="complete")
                st.rerun()
        except Exception as e:
            st.error("Approval check failed: %s" % e)

    if booked:
        st.success("SIMULATED booking confirmed - reference %s. A reply was sent to %s." % (booked["reference"], data["email"]))
    with open(store.xlsx_path(data), "rb") as f:
        st.download_button("Download Excel", f, file_name=store.xlsx_path(data).split("/")[-1])
