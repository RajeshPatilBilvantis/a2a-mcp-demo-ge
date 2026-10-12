import os
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
from html import escape
from urllib.parse import quote

import pandas as pd

from fmt import display_rows
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))


def _creds():
    user, pw = os.getenv("GMAIL_ADDRESS"), os.getenv("GMAIL_APP_PASSWORD")
    if not user or not pw:
        raise RuntimeError("GMAIL_ADDRESS / GMAIL_APP_PASSWORD not set in .env")
    return user, pw


def _table(rows, reply_address, subject):
    """HTML table; with `subject`, adds an Approve button (mailto reply link) to every row."""
    th = "".join("<th style='border:1px solid #999;padding:4px 8px;background:#1F4E78;color:#fff'>%s</th>"
                 % escape(str(k)) for k in list(rows[0]) + (["Approve"] if subject else []))
    body = ""
    for r in rows:
        cells = "".join("<td style='border:1px solid #999;padding:4px 8px'>%s</td>" % escape(str(v))
                        for v in r.values())
        if subject:
            link = "mailto:%s?subject=%s&body=%s" % (reply_address, quote("Re: " + subject),
                                                      quote("APPROVE %s" % r["Option ID"]))
            cells += ("<td style='border:1px solid #999;padding:4px 8px'><a href='%s' style='background:#2E7D32;"
                      "color:#fff;padding:6px 12px;border-radius:4px;text-decoration:none;font-weight:bold'>"
                      "Approve</a></td>" % escape(link))
        body += "<tr>%s</tr>" % cells
    return "<table style='border-collapse:collapse;font-family:Arial;font-size:13px'><tr>%s</tr>%s</table>" % (th, body)


def send(to, subject, intro, rows=None, attachment=None, reply_to_id=None, approve=False):
    """Send mail; returns the new Message-ID. reply_to_id threads it under an earlier message."""
    user, pw = _creds()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = user, to, subject
    msg["Message-ID"] = make_msgid()
    if reply_to_id:
        msg["In-Reply-To"] = msg["References"] = reply_to_id
    msg.set_content(intro)
    html = "<p>%s</p>" % escape(intro).replace("\n", "<br>")
    if rows:
        html += _table(display_rows(rows), user, subject if approve else None)
    msg.add_alternative(html, subtype="html")
    if attachment:
        with open(attachment, "rb") as f:
            msg.add_attachment(f.read(), maintype="application",
                               subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               filename=os.path.basename(attachment))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(user, pw)
        s.send_message(msg)
    return msg["Message-ID"]
