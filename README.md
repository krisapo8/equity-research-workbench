# Equity Research Workbench

A runnable Python/Streamlit financial research prototype.

## Features

- Upload text-based PDF, Markdown or TXT financial filings.
- Extract 14 financial statement metrics using optional OpenAI structured outputs, with filename/page references.
- Run a deterministic rule-based parser on a fictional three-year demonstration filing without an API key.
- Calculate revenue growth, margins, EBITDA, FCF, leverage and interest coverage.
- Inspect filing evidence, trace individual reported values back to their source page, and export CSV files.
- Generate source-referenced research observations. The LLM mode rejects summary bullets containing unrecognised citations.
- Compare extraction with analyst-labelled ground truth using field precision, recall, F1, matched-field value accuracy and source check rate.
- Estimate analyst time savings using measured processing time plus user-supplied manual and QA review timings.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

Open the localhost URL shown by Streamlit. Click **Run research** with the fictional demo selected to see an immediate dashboard and accuracy benchmark.

## AI extraction

Enter an OpenAI API key in the sidebar, switch to **LLM structured extraction**, upload a text-based annual filing and click **Run research**. Optionally set `OPENAI_API_KEY` in your shell. Model defaults to `gpt-4.1-mini`, change in sidebar if needed. API usage is chargeable. The LLM reads page text chunks and returns a Pydantic-validated schema. The code follows the OpenAI Responses structured parsing method.

Use human-reviewed labels to benchmark real filings. Required columns in the CSV: `source,year,metric,value`; `source` must match the uploaded filename exactly. Supported metric IDs are in `research/core.py`.

## Benchmark protocol

1. Select a representative set of company filings, industries, filing formats and fiscal periods.
2. Have analysts independently label a fixed set of metrics. Preserve source name, fiscal year and values in millions.
3. Run the model on the same files. Report precision, recall, matched-field accuracy, and failures per document, not just overall averages.
4. Time manual extraction per filing using a stopwatch, separately time automated extraction and the required human validation/correction.
5. Calculate `(manual minutes - automated minutes - review minutes) / manual minutes` as time reduction.
6. Record model, date, sample size, token/API cost, and an error taxonomy (wrong period, wrong unit, missed figure, wrong sign, wrong line item, unsupported citation).

The supplied gold CSV is generated from the fictional demo and intentionally yields 100% rule-parser performance. It does **not** measure LLM performance on real annual reports. Sidebar timing inputs are hypothetical until replaced with observed values.

## Limitations and quality gates

- Source check confirms that an equivalent number appears on the cited page. It cannot establish that the number belongs to the correct accounting line item, period or column.
- The current LLM pipeline is text-first. Scanned PDFs need OCR before upload. Complex tables, multi-column layouts, reported units, currency and fiscal calendars can create extraction errors.
- All input monetary values must use the same currency and be in millions. Upload one company at a time. Avoid repeated metrics from several annual filings unless you reconcile duplicates.
- Historical balance sheet measures are year-end snapshots. EBITDA uses operating income plus reported depreciation/amortisation, not management-adjusted EBITDA.
- Time saved is a user-entered scenario plus measured processing time, not a validated productivity claim until field timing studies are completed.
- Never rely on LLM prose alone for securities recommendations. Reconcile extracted figures to primary filings.

## Tests

```bash
pytest -q
```

## Project layout

```
app.py                     Streamlit interface
research/core.py           Calculations, parsing, provenance and evaluation
research/extraction.py     Rule-based + LLM extraction, cited summaries
demo/Orion_Systems_FY2024.txt  Entirely fictional filing
demo/gold_labels.csv       Demo reference labels
tests/test_core.py         Unit tests
```

## New: type a ticker and generate a company financial report

Select **Ticker lookup (US SEC)** in the sidebar and enter e.g. `AAPL`, `MSFT` or `NVDA`, or an unambiguous legal company name. Enter a **declared contact identity** in the form `Your Name you@example.com`. The SEC requires a contact address in the User-Agent. Click **Generate company report**.

- Automatically resolves a US-listed ticker from the SEC ticker directory, downloads SEC Company Facts XBRL records, selects annual FY filings, converts USD values to millions, and calculates financial ratios.
- Displays financial highlights, multi-year historical financial statements/ratios, a source evidence ledger with XBRL tag, accession and SEC archive links, and downloads CSV/Markdown files.
- Optionally generates a fuller AI narrative with your OpenAI API key. Without an API key, the deterministic source-linked overview still works.
- Only **US SEC registrants** are supported for automated ticker lookup. It is not a universal worldwide ticker/financial-data provider, not live stock quotes, not a full qualitative filing review, and not an automated DCF.
- SEC facts can have missing, issuer-specific, reclassified or restated fields. The selected filing accession establishes provenance but does **not** verify the number or provide a page citation. Some leverage/EBITDA values will be blank when compatible data is not found. Review before making investment decisions.
- The existing **Upload company filings** workflow remains available for page-verified text/PDF LLM extraction and analyst benchmarking.

If you already installed dependencies, run `python -m pip install -r requirements.txt` again to install `requests`, then `streamlit run app.py`.

Official source: https://www.sec.gov/search-filings/edgar-application-programming-interfaces

## V3: valuation, market peers, filing intelligence and cloud deployment

The **Ticker lookup (US SEC)** workflow has six tabs:

1. **Company report:** SEC-based financial summary and optional OpenAI commentary.
2. **Historical financials:** annual financial fundamentals and ratios.
3. **DCF valuation:** editable five-year FCFF valuation, base/bull/bear scenarios, sensitivity table, downloads. `Revenue -> EBIT -> NOPAT + D&A - capex - ΔNWC = FCFF`; discount FCFF at WACC; Gordon-growth terminal value; equity = EV minus net debt; per-share valuation requires a **verified diluted share count** supplied by the analyst. Bull/bear spreads are illustrative, not probabilistic estimates. Results are not forecasts from consensus data.
4. **Comparable companies:** quote and market-cap data from Yahoo Finance via `yfinance`, annual denominators from SEC facts, timestamped input, EV/Revenue, EV/EBITDA and P/E. USD only. Quotes may be delayed or unavailable. Financial and market inputs may differ in date. Missing debt or cash prevents EV calculation. Validate before publishing.
5. **AI filing analysis:** fetch the latest 10-K from SEC submissions; retrieve HTML; find candidate text excerpts about business, risk, management discussion and competition; optionally ask the LLM for excerpt-linked findings. Review the excerpt ID, quote and filing URL. Extracted passages are heuristic and **not a comprehensive full-filing review**. HTML lacks stable page numbering, so no PDF page is claimed. Download human-review CSV and upload reviewed labels for factual accuracy and citation support.
6. **SEC evidence:** documented reported tags, values and SEC links.

### To run locally

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

### Deploy as a website (recommended: Streamlit Community Cloud)

1. Create a GitHub repository; upload **the contents of `equity_research_platform`** so `app.py` and `requirements.txt` are in the repository root.
2. Do **not** commit `.env`, `.streamlit/secrets.toml`, API keys, or your `.venv` folder. `.gitignore` is included.
3. Open https://share.streamlit.io and connect the repository. Select branch `main` and main file `app.py`.
4. Deploy. The app gets a hosted `*.streamlit.app` URL and runs without VS Code or your laptop being on. Free services can sleep or have usage/resource limits.
5. In the Streamlit app settings, use **Secrets** for key/value entries such as:

```toml
OPENAI_API_KEY = "YOUR_KEY"
SEC_USER_AGENT = "EquityResearch contact@example.com"
```

6. If the app is public and a server-side paid API key is configured, **protect access** before making expensive LLM generation available to everyone. Otherwise visitors can trigger charges on your key. For a private portfolio prototype, prefer a private GitHub repository and restricted app access if available, or leave the API key unset and enter your own when using the app. App access control and abuse prevention have not been implemented in this prototype.

**Technical limits:** SEC requests can be rate limited/blocked by hosting network IP; market data from Yahoo is an informal research input rather than licensed professional market data; a US-company comparison must respect fiscal years, sector, business mix and accounting comparability. There is no claim of empirically measured extraction accuracy on multiple real-world issuers until reviewers supply independent gold labels. Existing uploaded-file numerical benchmarking and analyst time-study controls remain in the Upload filings workflow.

### Validation

```bash
pytest -q
```

### Further production work

Persist reports and audit trails, add authentication/rate limits, establish a paid reliable quote-feed, expand 10-K retrieval to complete section-aware extraction and PDFs when available, build cross-company independently labelled benchmarks, handle currency/fiscal alignment, refine fully diluted share estimates and company-specific WACC/tax/NWC forecasts.
