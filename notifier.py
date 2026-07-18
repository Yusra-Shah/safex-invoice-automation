"""Email notification via Gmail SMTP with a PDF invoice attachment."""

import os
import smtplib
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD")
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))


def _build_message(to_email: str, customer_name: str, pdf_path: str) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = f"Your SafeX Solutions Invoice - {customer_name}"

    body = (
        f"Hi {customer_name},\n\n"
        "Thank you for your order. Please find your invoice attached.\n\n"
        "Best regards,\n"
        "SafeX Solutions"
    )
    msg.attach(MIMEText(body, "plain"))

    with open(pdf_path, "rb") as f:
        attachment = MIMEApplication(f.read(), _subtype="pdf")
        attachment.add_header(
            "Content-Disposition", "attachment", filename=os.path.basename(pdf_path)
        )
        msg.attach(attachment)

    return msg


def _attempt_send(msg: MIMEMultipart, to_email: str) -> None:
    with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_APP_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())


def send_invoice_email(to_email: str, customer_name: str, pdf_path: str) -> dict:
    """Send the generated invoice PDF to the customer via email.

    Makes one retry attempt if the first send fails. Never raises;
    always returns a dict with "status" ("sent" or "failed"), a
    "timestamp", and an "error" field (None on success).
    """
    last_error = None

    for attempt in range(2):
        try:
            msg = _build_message(to_email, customer_name, pdf_path)
            _attempt_send(msg, to_email)
            return {
                "status": "sent",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "attempts": attempt + 1,
                "error": None,
            }
        except Exception as exc:
            last_error = str(exc)

    return {
        "status": "failed",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attempts": 2,
        "error": last_error,
    }
