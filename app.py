"""FastAPI entrypoint for the Invoice Automation Prototype.

Exposes a single POST /generate-invoice endpoint that runs the full
pipeline: parse -> validate -> generate PDF -> email.
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

load_dotenv()

REQUIRED_ENV_VARS = [
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_DEPLOYMENT",
    "AZURE_OPENAI_API_VERSION",
    "EMAIL_ADDRESS",
    "EMAIL_APP_PASSWORD",
]


def check_required_env_vars() -> None:
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): "
            f"{', '.join(missing)}. Please set them in your .env file "
            "(see .env.example for the full list)."
        )


check_required_env_vars()

# Imported after the env check so a missing var fails fast with a clear
# message instead of a deep import-time traceback from the SDK client.
from parser import parse_order  # noqa: E402
from validator import validate_order  # noqa: E402
from invoice_generator import generate_invoice  # noqa: E402
from notifier import send_invoice_email  # noqa: E402

app = FastAPI(title="SafeX Solutions Invoice Automation")


class OrderRequest(BaseModel):
    order_text: str
    customer_email: str


@app.post("/generate-invoice")
def generate_invoice_endpoint(request: OrderRequest):
    """Run the full order-to-invoice-to-email pipeline for one order."""
    try:
        parsed_order = parse_order(request.order_text)

        if parsed_order.get("flagged"):
            return {
                "status": "flagged",
                "flag_reason": parsed_order.get("flag_reason"),
                "parsed_order": parsed_order,
                "invoice_path": None,
                "warnings": [],
                "email_result": None,
            }

        validated_order = validate_order(parsed_order)
        warnings = validated_order.pop("warnings", [])

        invoice_path = generate_invoice(validated_order)

        email_result = send_invoice_email(
            to_email=request.customer_email,
            customer_name=validated_order.get("customer_name", "Customer"),
            pdf_path=invoice_path,
        )

        return {
            "status": "completed" if email_result.get("status") == "sent" else "email_failed",
            "invoice_path": invoice_path,
            "warnings": warnings,
            "email_result": email_result,
        }

    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "invoice_path": None,
            "warnings": [],
            "email_result": None,
        }


@app.get("/")
def root():
    return {"service": "SafeX Solutions Invoice Automation", "status": "running"}
