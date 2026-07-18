# SafeX Solutions — Invoice Automation Prototype

A single-pipeline prototype that takes a plain-text customer order, parses
it into structured data with an LLM, validates it, generates a PDF
invoice, and emails it to the customer — all triggered through one
FastAPI endpoint.

## What this project does

1. A customer's order arrives as free-form text (e.g. copy-pasted from an
   email or chat).
2. Azure OpenAI (`gpt-5-mini`) parses that text into structured JSON:
   customer name, line items, quantities, and prices where mentioned.
3. The parsed order is validated with Pandas: missing customer names,
   empty item lists, and non-positive quantities are caught; missing
   unit prices are filled in from a small product price lookup table.
4. A PDF invoice is generated with ReportLab, including an itemized
   table, subtotal, tax, and total.
5. The invoice is emailed to the customer as a PDF attachment via Gmail
   SMTP.

Ambiguous orders (unclear customer, unclear items, contradictory
details) are **flagged** by the parser instead of guessed at, and are
returned to the caller for manual review rather than silently invoiced.

## Architecture flow

```
                 POST /generate-invoice
                 { order_text, customer_email }
                          |
                          v
                  +---------------+
                  |   parser.py   |   Azure OpenAI (gpt-5-mini)
                  | parse_order() |   raw text -> structured JSON
                  +---------------+
                          |
              flagged? ---+--- yes --> return {status: "flagged", flag_reason}
                          |
                          no
                          v
                 +-----------------+
                 |  validator.py   |   Pandas
                 | validate_order()|   clean data, fill missing prices,
                 +-----------------+   collect warnings
                          |
                          v
              +----------------------+
              | invoice_generator.py |   ReportLab
              |  generate_invoice()  |   build itemized PDF invoice
              +----------------------+
                          |
                          v
                 +---------------+
                 |  notifier.py  |   smtplib + email.mime
                 | send_invoice_ |   send PDF via Gmail SMTP,
                 |    email()    |   1 retry on failure
                 +---------------+
                          |
                          v
        JSON response: { status, invoice_path, warnings, email_result }
```

All of this is orchestrated from a single endpoint in `app.py`.

## Project structure

```
app.py                    FastAPI entrypoint (POST /generate-invoice)
parser.py                 LLM order parsing (Azure OpenAI)
validator.py               Pandas-based validation + price lookup
invoice_generator.py      PDF invoice generation (ReportLab)
notifier.py                Email sending (smtplib)
data/sample_orders.csv    15 sample plain-text orders for testing
notebooks/demo.ipynb      Step-by-step walkthrough of the full pipeline
invoices/                 Generated PDF invoices land here (gitignored)
requirements.txt
.env.example               Template for required environment variables
.env                       Your real credentials (gitignored, not committed)
```

## Setup

1. **Install dependencies** (Python 3.11+ required):

   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables.** Copy `.env.example` to `.env` if
   you don't already have one, and fill in your real values:

   ```bash
   cp .env.example .env
   ```

   Required variables:

   | Variable                    | Description                                      |
   |------------------------------|---------------------------------------------------|
   | `AZURE_OPENAI_ENDPOINT`      | Your Azure OpenAI resource endpoint URL           |
   | `AZURE_OPENAI_API_KEY`       | Your Azure OpenAI API key                         |
   | `AZURE_OPENAI_DEPLOYMENT`    | Deployment name (e.g. `gpt-5-mini`)               |
   | `AZURE_OPENAI_API_VERSION`   | API version (e.g. `2024-08-01-preview`)           |
   | `EMAIL_ADDRESS`              | Gmail address to send invoices from               |
   | `EMAIL_APP_PASSWORD`         | Gmail **app password** (not your regular password)|
   | `EMAIL_SMTP_SERVER`          | Defaults to `smtp.gmail.com`                      |
   | `EMAIL_SMTP_PORT`            | Defaults to `587`                                 |

   The app checks for all required variables on startup and will raise a
   clear error naming any that are missing — it will not silently run
   with partial configuration.

## Running the server

```bash
uvicorn app:app --reload
```

The server starts at `http://127.0.0.1:8000`. No emails are sent on
startup — only when you actually call the endpoint.

## Testing the endpoint

### curl

```bash
curl -X POST http://127.0.0.1:8000/generate-invoice \
  -H "Content-Type: application/json" \
  -d '{
        "order_text": "Hi, this is John Carter from Carter Manufacturing. I would like to order 10 widgets and 5 brackets.",
        "customer_email": "john.carter@example.com"
      }'
```

### Postman

- Method: `POST`
- URL: `http://127.0.0.1:8000/generate-invoice`
- Body → raw → JSON:

  ```json
  {
    "order_text": "Order from Maria Lopez: 3 sensors at $42.00 each and 2 cables.",
    "customer_email": "maria.lopez@example.com"
  }
  ```

### Expected response shape

```json
{
  "status": "completed",
  "invoice_path": "invoices/invoice_John_Carter_2026-07-17.pdf",
  "warnings": ["Item 'bracket' had no unit price; filled in $3.25 from product lookup."],
  "email_result": {
    "status": "sent",
    "timestamp": "2026-07-17T12:34:56.789+00:00",
    "attempts": 1,
    "error": null
  }
}
```

If the order is too ambiguous to parse, you'll instead get:

```json
{
  "status": "flagged",
  "flag_reason": "No identifiable items were mentioned in the order text.",
  "parsed_order": { "...": "..." },
  "invoice_path": null,
  "warnings": [],
  "email_result": null
}
```

## Demo notebook

`notebooks/demo.ipynb` walks through the entire pipeline step by step
using a few sample orders from `data/sample_orders.csv`, printing the
output at each stage (parsed JSON, validated order, invoice path). The
final email-send step is **mocked** in the notebook — it prints what
would be sent instead of actually sending — so the notebook can be
re-run freely without spamming a real inbox. Run it with:

```bash
jupyter notebook notebooks/demo.ipynb
```

## Notes on prototype placeholders

- **Tax rate**: a flat 5% is hardcoded in `invoice_generator.py`
  (`TAX_RATE = 0.05`). A production system would look this up per
  jurisdiction/product.
- **Product price lookup**: `validator.py` contains a small hardcoded
  dictionary of ~10 products and prices, used only to fill in missing
  unit prices the LLM didn't find in the order text. A production
  system would query a real product catalog or pricing database instead.

## What this prototype intentionally does not do

- It does not use the standard OpenAI client — only `AzureOpenAI`.
- It does not hardcode credentials anywhere in code — everything sensitive
  comes from `.env`.
- It does not send any email automatically on server startup — only when
  `/generate-invoice` is actually called.
