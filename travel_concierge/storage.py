import json
import os
import uuid

from travel_concierge.config import OUTPUT_DIR as OUT


def new_request(city, email, rows):
    os.makedirs(OUT, exist_ok=True)
    token = "TRIP-" + uuid.uuid4().hex[:6]
    data = {"token": token, "city": city, "email": email, "rows": rows, "booking": None,
            "message_id": None, "subject": None}
    save(data)
    return data


def _path(token):
    return os.path.join(OUT, token + ".json")


def save(data):
    with open(_path(data["token"]), "w") as f:
        json.dump(data, f, indent=2)


def load(token):
    with open(_path(token)) as f:
        return json.load(f)


def xlsx_path(data):
    return os.path.join(OUT, "travel_options_%s_%s.xlsx" % (data["city"].replace(" ", "_"), data["token"]))
