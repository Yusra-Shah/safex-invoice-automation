"""LLM-based order parsing using Azure OpenAI.

Takes raw, plain-text customer orders and turns them into structured
JSON via the model. The model is instructed to flag ambiguous orders
rather than guess at missing details.
"""

import json
import os

from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

client = AzureOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
)

DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")

SYSTEM_PROMPT = """You are an order-parsing assistant for SafeX Solutions.

You will receive a plain-text customer order. Extract the order details
and return ONLY valid JSON, with no markdown fences and no commentary,
in exactly this shape:

{
  "customer_name": string,
  "items": [{"item": string, "quantity": integer, "unit_price": number or null}],
  "flagged": boolean,
  "flag_reason": string or null
}

Rules:
- If a quantity is not mentioned for an item, default it to 1.
- If a unit price is not mentioned in the text, set unit_price to null
  (it will be looked up later). Never invent a price.
- If the order is too ambiguous or incomplete to parse confidently
  (e.g. no identifiable customer name, no identifiable items, or
  contradictory information), set "flagged" to true and explain why
  in "flag_reason". Do not guess at missing critical information.
- If the order is clear, set "flagged" to false and "flag_reason" to null.
- Return ONLY the JSON object, nothing else.
"""


def _empty_flagged_result(reason: str) -> dict:
    return {
        "customer_name": "",
        "items": [],
        "flagged": True,
        "flag_reason": reason,
    }


def _extract_json_block(text: str) -> str:
    """Best-effort extraction of a JSON object from a model response
    that may be wrapped in markdown code fences or extra prose."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]


def parse_order(text: str) -> dict:
    """Parse raw order text into structured data via Azure OpenAI.

    Always returns a dict matching the expected schema. If the model
    call fails or returns malformed JSON, the result is flagged rather
    than raising, so the pipeline can surface the issue to the caller.
    """
    if not text or not text.strip():
        return _empty_flagged_result("Order text was empty.")

    try:
        response = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
        raw_content = response.choices[0].message.content or ""
    except Exception as exc:
        return _empty_flagged_result(f"LLM call failed: {exc}")

    json_block = _extract_json_block(raw_content)

    try:
        parsed = json.loads(json_block)
    except json.JSONDecodeError as exc:
        return _empty_flagged_result(
            f"Model returned malformed JSON and could not be parsed: {exc}"
        )

    # Defensive normalization in case the model omits fields.
    parsed.setdefault("customer_name", "")
    parsed.setdefault("items", [])
    parsed.setdefault("flagged", False)
    parsed.setdefault("flag_reason", None)

    normalized_items = []
    for item in parsed.get("items") or []:
        if not isinstance(item, dict):
            continue
        normalized_items.append(
            {
                "item": item.get("item", ""),
                "quantity": item.get("quantity") if item.get("quantity") is not None else 1,
                "unit_price": item.get("unit_price", None),
            }
        )
    parsed["items"] = normalized_items

    return parsed
