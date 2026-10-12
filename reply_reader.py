import email
import imaplib
import re
from email.header import decode_header, make_header

from emailer import _creds


def _body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
        return ""
    return msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "replace")


def _strip_quotes(text):
    lines = []
    for line in text.splitlines():
        if re.match(r"^On .* wrote:", line) or line.startswith(">"):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def find_approval(token, sender, valid_ids):
    """Newest reply from `sender` with `token` in the subject saying 'APPROVE OPT-xx' (as sent by the
    email's Approve button). Returns the Option ID, or None."""
    user, pw = _creds()
    m = imaplib.IMAP4_SSL("imap.gmail.com")
    m.login(user, pw)
    try:
        m.select('"[Gmail]/All Mail"', readonly=True)
        _, ids = m.search(None, "FROM", '"%s"' % sender, "SUBJECT", '"%s"' % token)
        for mid in reversed(ids[0].split()):
            _, d = m.fetch(mid, "(RFC822)")
            msg = email.message_from_bytes(d[0][1])
            subject = str(make_header(decode_header(msg.get("Subject", ""))))
            reply = _strip_quotes(_body(msg))
            if not subject.lower().startswith("re:") or "SIMULATED BOOKING" in reply:
                continue  # original send, or our own confirmation (when sender == user)
            for oid in re.findall(r"OPT-\d+", reply.upper()):
                if oid in valid_ids:
                    return oid
        return None
    finally:
        m.logout()
