# Bill Processor CLI
## Haroon & Sons Coconut Brokerage Bill Automation

A Python CLI tool that extracts, validates, and formats handwritten coconut brokerage bills into structured Excel and PDF documents.

---

## Features

✅ **AI-Powered Extraction** — Uses Gemini (or Claude) to read handwritten bills with confidence scoring
✅ **Intelligent Validation** — Flags low-confidence, out-of-range, and suspicious entries
✅ **Manual Review** — HTML verification report for spot-checking flagged entries only (~5-10 entries)
✅ **Auto-Formatting** — Generates professional XLS and PDF with headers, formulas, and totals
✅ **LLM Flexible** — Works with Gemini or Claude API (easy to swap)

---

## Installation

### 1. Install Python (if not already installed)
Requires Python 3.8+

### 2. Clone/Download the Files
Save all Python files to a single directory:
- `bill_processor.py` (main script)
- `extraction_prompt.md` (prompt template)
- `validation_script.py` (validation logic)
- `formatting_script.py` (XLS/PDF generation)
- `requirements.txt` (dependencies)

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Get API Key
- **Gemini:** Go to [Google AI Studio](https://aistudio.google.com/app/apikeys) → Create API key
- **Claude:** Go to [Anthropic Console](https://console.anthropic.com/account/keys) → Create API key

---

## Usage

### Basic Command
```bash
python bill_processor.py --pdf input.pdf --api-key YOUR_API_KEY --llm gemini --brokerage-rate 5
```

### Arguments
- `--pdf` (required) — Path to handwritten bill (PDF or JPG)
- `--api-key` (required) — Your Gemini or Claude API key
- `--llm` (optional) — LLM provider: `gemini` (default) or `claude`
- `--brokerage-rate` (optional) — Brokerage rate in rupees: `5` (default) or `10`
- `--client` (optional) — Client name for bill header (default: "M/S LALCHAND RAMCHAND, VASHI")
- `--period-start` (optional) — Bill period start in DD-MM-YYYY (default: "01-04-2025")
- `--period-end` (optional) — Bill period end in DD-MM-YYYY (default: "31-03-2026")
- `--output-dir` (optional) — Output directory for files (default: current directory)

### Examples

#### Extract ACE_Scanner bill with Gemini (5rs brokerage)
```bash
python bill_processor.py --pdf ACE_Scanner_2026_05_20.pdf --api-key YOUR_GEMINI_KEY --llm gemini --brokerage-rate 5
```

#### Extract with custom client name and bill period
```bash
python bill_processor.py \
  --pdf bill.jpg \
  --api-key YOUR_KEY \
  --llm gemini \
  --brokerage-rate 10 \
  --client "M/S SOME OTHER CLIENT" \
  --period-start "01-06-2025" \
  --period-end "30-11-2025"
```

#### Use Claude instead of Gemini
```bash
python bill_processor.py --pdf bill.pdf --api-key YOUR_CLAUDE_KEY --llm claude
```

---

## Workflow

### Step 1: Extract & Validate
```bash
python bill_processor.py --pdf handwritten_bill.pdf --api-key YOUR_KEY --llm gemini --brokerage-rate 5
```

**Output:**
- `extracted_*.json` — Raw extracted data with confidence scores
- `validation_*.json` — Validation results
- `verification_report_*.html` — HTML report of flagged entries

### Step 2: Review Flagged Entries
Open `verification_report_*.html` in your browser.

You'll see:
- **Clean entries** (✓ OK) — Passed all validation, no action needed
- **Flagged entries** (⚠️ FLAGGED) — Requires manual review

For each flagged entry:
1. Look at the handwritten bill
2. Verify the extracted data matches
3. Correct if jumbled, unclear, or wrong
4. Note corrections in a text file if needed

### Step 3: Use Generated Files
- `bill_*.xlsx` — Excel file for internal records (editable)
- `bill_*.pdf` — PDF file for client delivery (print-ready)

---

## Output Files

### Extracted Data (`extracted_*.json`)
Raw JSON from Gemini with confidence scores:
```json
{
  "bill_metadata": { ... },
  "transactions": [
    {
      "entry_number": 1,
      "date": "07-04-2025",
      "date_confidence": "HIGH",
      "katta": 400,
      "katta_confidence": "HIGH",
      "rate": 218,
      "rate_confidence": "HIGH",
      "party": "M/S MUSKHAN ENTERPRISES",
      "party_confidence": "HIGH",
      "bill_details": "Bill 6",
      "bill_details_confidence": "HIGH"
    },
    ...
  ]
}
```

### Verification Report (`verification_report_*.html`)
Interactive HTML showing:
- Summary of total/flagged/clean entries
- Each flagged entry with:
  - Extracted values + confidence levels
  - List of issues/flags
  - Action items for user

### Excel Output (`bill_*.xlsx`)
Professional formatted spreadsheet with:
- Company header (Haroon & Sons)
- Client name
- Bill period
- Column headers (Date, Katta, Rate, Party, Details, Brokerage)
- All transactions sorted by date
- Total brokerage at bottom
- Proper formatting and formulas

### PDF Output (`bill_*.pdf`)
Print-ready PDF with:
- Repeating page headers
- Page numbers
- Same content as Excel
- Professional formatting

---

## Flagging Rules

The system flags entries that need review if any of these are true:

1. **Low Confidence** — Any field has MEDIUM or LOW confidence (hard to read)
2. **Unclear Party** — Party name not recognized or unreadable
3. **Date Out of Period** — Date outside the specified bill period
4. **Field Isolation** — One field is clear but neighbors are unclear (possible misalignment)
5. **Outlier Values** — Katta < 1 or > 500, Rate < 100 or > 500
6. **Missing Details** — Bill details field is empty/unclear
7. **Digit 6 Problem** — Any number containing ambiguous digits (6 vs 5/8/9)

---

## Troubleshooting

### "Error: File not found: input.pdf"
- Check that the PDF path is correct
- Use absolute path if file is in a different directory:
  ```bash
  python bill_processor.py --pdf /path/to/bill.pdf --api-key KEY
  ```

### "Error parsing Gemini response as JSON"
- The API call succeeded but Gemini didn't return valid JSON
- This can happen if:
  - PDF is too blurry/hard to read → Use a clearer scan
  - Gemini misunderstood the prompt → Check API limit/quota
- Try again with a clearer image

### "ImportError: No module named 'google.generativeai'"
- Dependencies not installed
- Run: `pip install -r requirements.txt`

### "Invalid API key"
- Check that your API key is correct
- Make sure the key matches the LLM provider (Gemini key for `--llm gemini`)

### "PDF looks wrong" (PDF missing headers/formatting)
- This is a known issue with reportlab
- The Excel file is always correct; use that for records
- You can print the Excel as PDF as a workaround

---

## Performance Notes

- Extraction time: ~5-15 seconds (depends on PDF size, LLM speed)
- Validation + formatting: <5 seconds
- Total time per bill: ~10-20 seconds
- Spot-check time (manual review): ~5-10 minutes

**Cost:** ~$0.01-0.05 per bill (Gemini/Claude API pricing)

---

## FAQ

### Can I use both Gemini and Claude?
Yes, pass `--llm gemini` or `--llm claude`. The rest of the system is LLM-agnostic.

### What if a party name is not in our master list?
The system marks it as "UNCLEAR" and flags it for review. When you get the master party list, we can add fuzzy matching to auto-validate.

### Can I batch process multiple bills?
Not yet. Currently, one bill at a time. We can add batch processing later.

### What if I want to modify the flagging rules?
Edit `validation_script.py` → `BillValidator.validate_entry()` method. Each flag is clearly labeled.

### Can I use a different LLM (like OpenAI)?
Yes, but you'd need to modify `bill_processor.py` to call a different API. The structure supports it.

---

## Architecture

```
Input: Handwritten PDF
  ↓
[Tier 1: Extraction]
  ├─ Claude/Gemini API extracts data
  ├─ Returns JSON with confidence scores
  └─ Saves extracted_*.json
  ↓
[Tier 2: Validation]
  ├─ Checks confidence levels
  ├─ Flags suspicious entries
  ├─ Validates against business rules
  └─ Generates validation_*.json + HTML report
  ↓
[You: Manual Review]
  └─ Open HTML report, spot-check flagged entries
  ↓
[Tier 3: Formatting]
  ├─ Prepares data for output
  ├─ Generates bill_*.xlsx
  └─ Generates bill_*.pdf
  ↓
Output: bill_*.xlsx + bill_*.pdf
```

---

## Support

For issues or questions:
1. Check troubleshooting section above
2. Review the generated HTML report (very detailed)
3. Check the validation_*.json file for full validation details

---

## Version
- **v1.0** — Initial release (May 2026)
- Tier 1: Extraction ✓
- Tier 2: Validation ✓
- Tier 3: Formatting ✓
- Next: Web app UI (coming soon)

---

## License
Internal use for Haroon & Sons only.
