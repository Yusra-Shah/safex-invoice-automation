"""Pandas-based validation and price-fill-in for parsed orders."""

import pandas as pd

# Placeholder product price lookup for the prototype. In a production
# system this would come from a product catalog / database.
PRODUCT_PRICE_LOOKUP = {
    "widget": 12.50,
    "gadget": 24.99,
    "bolt": 0.75,
    "bracket": 3.25,
    "sensor": 45.00,
    "cable": 8.99,
    "battery pack": 19.99,
    "enclosure": 32.50,
    "circuit board": 58.00,
    "power supply": 41.75,
    "laptop": 650,
    "keyboard": 25,
    "mouse": 15,
    "monitor": 180,
    "notebook": 3,
    "pen": 1,
    "desk": 120,
    "chair": 90,
    "printer": 200,
    "webcam": 40,
}


def _lookup_price(item_name: str) -> float | None:
    """Case-insensitive, substring-tolerant lookup against the price table."""
    if not item_name:
        return None
    name = item_name.strip().lower()
    if name in PRODUCT_PRICE_LOOKUP:
        return PRODUCT_PRICE_LOOKUP[name]
    for key, price in PRODUCT_PRICE_LOOKUP.items():
        if key in name or name in key:
            return price
    return None


def validate_order(order: dict) -> dict:
    """Validate and clean a parsed order dict.

    Checks for a missing customer name, an empty items list, and
    non-positive quantities. Fills in unit_price from a hardcoded
    product price lookup when the parser left it null. Returns the
    cleaned order dict plus a "warnings" list describing anything
    that needed attention.
    """
    warnings: list[str] = []
    cleaned = dict(order)

    if not cleaned.get("customer_name") or not str(cleaned["customer_name"]).strip():
        warnings.append("Missing customer name.")
        cleaned["customer_name"] = cleaned.get("customer_name") or "Unknown Customer"

    items = cleaned.get("items") or []
    if len(items) == 0:
        warnings.append("Order has no items.")
        cleaned["items"] = []
        cleaned["warnings"] = warnings
        return cleaned

    df = pd.DataFrame(items)

    if "quantity" not in df.columns:
        df["quantity"] = 1
    if "unit_price" not in df.columns:
        df["unit_price"] = None
    if "item" not in df.columns:
        df["item"] = ""

    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")

    for idx, row in df.iterrows():
        item_name = row.get("item", "") or "(unnamed item)"

        if pd.isna(row["quantity"]) or row["quantity"] <= 0:
            warnings.append(
                f"Item '{item_name}' had an invalid or non-positive quantity; defaulted to 1."
            )
            df.at[idx, "quantity"] = 1

        if pd.isna(row["unit_price"]) or row["unit_price"] is None:
            looked_up = _lookup_price(item_name)
            if looked_up is not None:
                df.at[idx, "unit_price"] = looked_up
                warnings.append(
                    f"Item '{item_name}' had no unit price; filled in ${looked_up:.2f} from product lookup."
                )
            else:
                df.at[idx, "unit_price"] = None
                warnings.append(
                    f"Item '{item_name}' has no matching price in the lookup table, manual pricing required"
                )

    df["quantity"] = df["quantity"].astype(int)
    df["unit_price"] = df["unit_price"].astype(float)

    cleaned["items"] = df[["item", "quantity", "unit_price"]].to_dict(orient="records")
    cleaned["warnings"] = warnings
    return cleaned
