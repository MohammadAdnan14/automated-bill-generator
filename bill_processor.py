#!/usr/bin/env python3
"""
Bill Processor CLI
For Haroon & Sons Coconut Brokerage Bill Automation

Usage:

This script:
1. Sends PDF to Gemini (or Claude) for extraction with confidence scores
2. Validates extracted data and flags risky entries
3. Generates HTML verification report for manual review
4. Generates XLS and PDF from verified entries
"""

import argparse
import json
import base64
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Dict
from dotenv import load_dotenv
from google import genai
from google.genai import types
from validation_script import BillValidator, generate_verification_report, load_party_list
from formatting_script import BillFormatter

# Load environment variables from .env file
load_dotenv()


def load_image_as_base64(image_path: str) -> str:
    """Load image file and convert to base64."""
    with open(image_path, 'rb') as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def get_extraction_prompt() -> str:
    """Get the extraction prompt from extraction_prompt.md"""
    with open('extraction_prompt.md', 'r', encoding='utf-8') as f:
        return f.read()


def extract_with_gemini(pdf_path: str, api_key: str, model_name: str = "gemini-2.5-flash") -> Dict:
    """
    Send PDF to Gemini for extraction using new google-genai SDK.
    
    Args:
        pdf_path: Path to PDF file
        api_key: Gemini API key
        model_name: Gemini model name
    
    Returns:
        Extracted JSON with confidence scores
    """
    client = genai.Client(api_key=api_key)
    
    # Load prompt
    prompt = get_extraction_prompt()
    
    # Load file bytes
    with open(pdf_path, 'rb') as f:
        file_bytes = f.read()
    
    # Determine media type
    if pdf_path.lower().endswith('.pdf'):
        media_type = "application/pdf"
    elif pdf_path.lower().endswith(('.jpg', '.jpeg')):
        media_type = "image/jpeg"
    elif pdf_path.lower().endswith('.png'):
        media_type = "image/png"
    else:
        media_type = "image/jpeg"
    
    # Generate content using modern SDK format
    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Part.from_bytes(
                data=file_bytes,
                mime_type=media_type
            ),
            prompt
        ]
    )
    
    # Parse response
    response_text = response.text
    
    # Extract JSON from response
    try:
        # Try to find JSON in response
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        if start != -1 and end > start:
            json_str = response_text[start:end]
            extracted = json.loads(json_str)
            return extracted
        else:
            print("Error: Could not find JSON in Gemini response")
            print("Response:", response_text[:500])
            sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing Gemini response as JSON: {e}")
        print("Response:", response_text[:500])
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Bill Processor: Extract, validate, and format coconut brokerage bills',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python bill_processor.py --pdf bill.jpg --client "M/S LALCHAND RAMCHAND, VASHI"
        """
    )
    
    parser.add_argument('--pdf', required=True, help='Path to handwritten bill PDF/JPG')
    parser.add_argument('--api-key', default=os.getenv('GEMINI_API_KEY'), help='Gemini or Claude API key (defaults to GEMINI_API_KEY in .env)')
    parser.add_argument('--llm', default='gemini-2.5-flash', help='LLM provider (default: gemini-2.5-flash)')
    parser.add_argument('--brokerage-rate', type=int, default=5, choices=[5, 10], help='Brokerage rate in rupees (default: 5)')
    parser.add_argument('--client', required=True, help='Client name for bill header')
    parser.add_argument('--period-start', default='01-04-2025', help='Bill period start (DD-MM-YYYY)')
    parser.add_argument('--period-end', default='31-03-2026', help='Bill period end (DD-MM-YYYY)')
    parser.add_argument('--output-dir', default='.', help='Output directory for XLS and PDF')
    parser.add_argument('--party-list', default='bill/party.txt', help='Path to master party list file (default: bill/party.txt)')
    
    args = parser.parse_args()
    
    # Validate API key exists
    if not args.api_key:
        print("Error: API key not found. Please provide it via --api-key or set GEMINI_API_KEY in a .env file.")
        sys.exit(1)
        
    # Validate inputs
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"Error: File not found: {args.pdf}")
        sys.exit(1)
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*80)
    print("BILL PROCESSOR - Haroon & Sons Coconut Brokerage")
    print("="*80)
    
    # Step 1: Extract
    print(f"\n[1/4] Extracting data from {pdf_path.name}...")
    extracted = extract_with_gemini(str(pdf_path), args.api_key, args.llm)
    print(f"✓ Extracted {len(extracted.get('transactions', []))} entries")
    
    # Save extracted JSON
    extracted_json_path = output_dir / f"extracted_{pdf_path.stem}.json"
    with open(extracted_json_path, 'w', encoding='utf-8') as f:
        json.dump(extracted, f, indent=2)
    print(f"✓ Saved extracted data: {extracted_json_path}")
    
    # Step 2: Validate
    print(f"\n[2/4] Validating entries...")
    party_dict = load_party_list(args.party_list) if args.party_list else None
    if party_dict:
        print(f"✓ Loaded party list from {args.party_list} with {len(party_dict)} entries/aliases")
    else:
        print(f"⚠️  No party list loaded (validation checks will skip party verification)")
        
    validator = BillValidator(
        bill_period_start=args.period_start,
        bill_period_end=args.period_end,
        party_list=party_dict
    )
    validation_result = validator.validate_bill(extracted)
    
    flagged = validation_result['validation_summary']['flagged_entries']
    clean = validation_result['validation_summary']['clean_entries']
    print(f"✓ Validation complete: {clean} clean, {flagged} flagged for review")
    
    # Save validation result
    validation_json_path = output_dir / f"validation_{pdf_path.stem}.json"
    with open(validation_json_path, 'w', encoding='utf-8') as f:
        json.dump(validation_result, f, indent=2)
    print(f"✓ Saved validation result: {validation_json_path}")
    
    # Step 3: Generate verification report
    print(f"\n[3/4] Generating verification report...")
    html_report = generate_verification_report(validation_result)
    
    report_path = output_dir / f"verification_report_{pdf_path.stem}.html"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_report)
    print(f"✓ Generated verification report: {report_path}")
    print(f"\n⚠️  NEXT STEP: Open the HTML report and review flagged entries")
    print(f"   File: {report_path}")
    print(f"   Correct any errors, then save corrections to corrections.json")
    
    # Step 4: Format output (using original entries, not validated yet)
    # Note: In real workflow, user would correct flagged entries first
    print(f"\n[4/4] Formatting output...")
    
    formatter = BillFormatter(
        client_name=args.client,
        brokerage_rate=args.brokerage_rate,
        bill_period_start=args.period_start,
        bill_period_end=args.period_end
    )
    
    # Prepare entries (convert to proper format)
    prepared_entries = formatter.prepare_entries(validation_result['validated_entries'])
    
    # Generate XLS
    xls_path = output_dir / f"bill_{pdf_path.stem}.xlsx"
    formatter.generate_xls(prepared_entries, str(xls_path))
    print(f"✓ Generated XLS: {xls_path}")
    
    # Generate PDF
    
    print("\n" + "="*80)
    print("PROCESSING COMPLETE")
    print("="*80)
    print(f"\nOutput files:")
    print(f"  1. Verification Report: {report_path}")
    print(f"  2. Excel File: {xls_path}")
    print(f"\nNext steps:")
    print(f"  1. Review the HTML verification report")
    print(f"  2. Correct any flagged entries (if needed)")
    print(f"  3. Use the generated XLS/PDF for final review or client delivery")
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    main()
