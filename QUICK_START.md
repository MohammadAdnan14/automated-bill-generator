# Quick Start (5 Minutes)

## 1. Get Your Gemini API Key (1 min)
- Go to: https://aistudio.google.com/app/apikeys
- Click "Create API Key"
- Copy it (save somewhere safe)

## 2. Install Python (if needed)
```bash
# Check if Python 3.8+ is installed
python --version

# If not, download from python.org
```

## 3. Setup Bill Processor (2 mins)
```bash
# Navigate to the folder with the Python files
cd /path/to/bill_processor_files

# Install dependencies
pip install -r requirements.txt
```

## 4. Run on Sample Bill (1 min)
```bash
python bill_processor.py \
  --pdf ACE_Scanner_2026_05_20.pdf \
  --api-key YOUR_GEMINI_API_KEY \
  --llm gemini \
  --brokerage-rate 5
```

## 5. Review Output (1 min)
Look for these files in the same folder:
- `verification_report_ACE_Scanner_2026_05_20.html` — **Open this in your browser**
- `bill_ACE_Scanner_2026_05_20.xlsx` — Excel file
- `bill_ACE_Scanner_2026_05_20.pdf` — PDF file

---

## That's It!

You now have:
1. ✓ Extracted data from handwritten bill
2. ✓ Flagged suspicious entries for review
3. ✓ Generated professional XLS + PDF

Open the HTML report and spot-check the flagged entries (should be ~10-15 out of 50-150).

---

## Next Steps

- Use `--client` to change client name
- Use `--brokerage-rate 10` for 10rs brokerage
- Use `--period-start` and `--period-end` for different bill periods
- See `README.md` for full documentation

---

## Need Help?

**Error: "API key invalid"**
- Copy the key again from Google AI Studio
- Paste it carefully (no spaces at start/end)

**Error: "No module named 'google.generativeai'"**
- Run: `pip install google-generativeai`

**PDF looks weird**
- Use the Excel file instead (more reliable)

---

**Questions?** See README.md for full documentation.
