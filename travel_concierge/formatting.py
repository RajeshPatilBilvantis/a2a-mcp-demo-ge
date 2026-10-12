import re


def inr(n):
    """12345678 -> ₹1,23,45,678 (Indian digit grouping)."""
    s = str(int(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = head + "," + tail
    return "₹" + s


def to_int(v):
    """'₹4,500' / '4500' / 4500.0 -> 4500; None if unparseable."""
    try:
        return int(float(re.sub(r"[^\d.]", "", str(v))))
    except ValueError:
        return None


def display_rows(rows):
    """Copy of rows with every '(INR)' column rendered as ₹ strings (for UI/email)."""
    return [{k: (inr(v) if "(INR)" in k and isinstance(v, int) else v) for k, v in r.items()} for r in rows]
