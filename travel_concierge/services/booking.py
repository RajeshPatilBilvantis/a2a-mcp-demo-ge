import datetime
import uuid

from travel_concierge import storage as store
from travel_concierge.formatting import inr
from travel_concierge.prompts import get_prompt
from travel_concierge.services import emailer, excel


def simulate(data, option_id, step=lambda m: None):
    """Simulated booking only (no payment, no airline/hotel calls). Replies in the original email thread."""
    if data.get("booking"):
        return data["booking"], False
    o = next(r for r in data["rows"] if r["Option ID"] == option_id)
    step("Holding flight %s (%s)..." % (o["Flight Route"], o["Airline"]))
    step("Reserving %s for %d nights..." % (o["Hotel"], o["Nights"]))
    data["booking"] = {"option": o, "reference": "SIM-" + uuid.uuid4().hex[:6].upper(),
                       "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}
    store.save(data)
    path = excel.add_booking(data)
    step("Replying to %s with confirmation..." % data["email"])
    text = get_prompt("BOOKING_CONFIRMATION", option_id=option_id, city=o["City"],
                      reference=data["booking"]["reference"], route=o["Flight Route"], airline=o["Airline"],
                      hotel=o["Hotel"], stars=o["Stars"], nights=o["Nights"], total=inr(o["Total Trip Cost (INR)"]))
    emailer.send(data["email"], "Re: " + (data.get("subject") or "[%s]" % data["token"]), text,
                 rows=[o], attachment=path, reply_to_id=data.get("message_id"))
    return data["booking"], True
