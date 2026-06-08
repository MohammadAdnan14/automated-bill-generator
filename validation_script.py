"""
Validation Script: Flag Risky Entries
For Haroon & Sons Coconut Brokerage Bill Automation

Takes Claude/Gemini extracted JSON and flags entries that need manual review.
Now with party list support and alias resolution.
"""

import json
from datetime import datetime
from typing import List, Dict, Any, Tuple
from difflib import SequenceMatcher

class BillValidator:
    def __init__(self, bill_period_start: str = "01-04-2025", bill_period_end: str = "31-03-2026", party_list: Dict[str, str] = None):
        """
        Initialize validator with bill period and optional party list.
        
        Args:
            bill_period_start: DD-MM-YYYY format
            bill_period_end: DD-MM-YYYY format
            party_list: Dict mapping canonical names and aliases to canonical names
                       e.g., {"BALAJI INDUSTRIES": "BALAJI INDUSTRIES", "BHABHI": "BALAJI INDUSTRIES"}
        """
        self.bill_period_start = self._parse_date(bill_period_start)
        self.bill_period_end = self._parse_date(bill_period_end)
        self.typical_katta_range = (1, 500)
        self.typical_rate_range = (100, 500)
        self.party_list = party_list or {}  # Will be populated if provided
        self.fuzzy_match_threshold = 0.95  # 95% match for fuzzy matching
    
    @staticmethod
    def _parse_date(date_str: str) -> datetime:
        """Parse DD-MM-YYYY to datetime object."""
        return datetime.strptime(date_str, "%d-%m-%Y")
    
    @staticmethod
    def fuzzy_match(str1: str, str2: str) -> float:
        """Calculate fuzzy match ratio between two strings."""
        return SequenceMatcher(None, str1.upper(), str2.upper()).ratio()
    
    def validate_party(self, party_name: str) -> Tuple[str, float, str]:
        """
        Validate party name against party list.
        Quietly converts to the closest match in the master list.
        
        Returns:
            (resolved_party_name, confidence, flag_message)
        """
        if party_name == "UNCLEAR":
            return "UNCLEAR", 0.0, "Party name marked as UNCLEAR in extraction"
        
        if not self.party_list:
            # No party list provided, can't validate
            return party_name, 1.0, None
        
        # Remove M/S prefix for matching
        import re
        party_clean = re.sub(r'^(M/S\.?|M/S\s+)', '', party_name, flags=re.IGNORECASE).strip().upper()
        
        # Exact match
        if party_clean in self.party_list:
            canonical = self.party_list[party_clean]
            return f"M/S {canonical}", 1.0, None
        
        # Fuzzy match to find the closest match quietly
        best_match = None
        best_score = 0.0
        
        for key, canonical in self.party_list.items():
            key_clean = re.sub(r'^(M/S\.?|M/S\s+)', '', key, flags=re.IGNORECASE).strip().upper()
            
            # Match against the full candidate name
            score = self.fuzzy_match(party_clean, key_clean)
            
            # Match against the first word or words of key_clean for partial names
            key_words = key_clean.split()
            if key_words:
                word_score = self.fuzzy_match(party_clean, key_words[0])
                score = max(score, word_score * 0.9)  # slight penalty for word-only match
                
            if score > best_score:
                best_score = score
                best_match = canonical
        
        # Quietly convert to the closest match if any reasonable candidate exists
        if best_score >= 0.4:
            return f"M/S {best_match}", best_score, None
        else:
            # No candidate found
            return "UNCLEAR", 0.0, f"Party '{party_name}' could not be matched to any party in master list"
    
    def validate_entry(self, entry: Dict[str, Any]) -> Tuple[List[Dict], bool]:
        """
        Validate single entry and return flags + needs_review boolean.
        
        Returns:
            (flags_list, needs_review_boolean)
        """
        flags = []
        
        # Step 1: Normalize party name BEFORE verification
        party_name = entry.get('party', 'UNCLEAR')
        entry['original_party'] = party_name  # Save original party name before normalization
        if self.party_list:
            resolved_party, score, flag_msg = self.validate_party(party_name)
            entry['party'] = resolved_party
            if resolved_party != "UNCLEAR":
                entry['party_confidence'] = 'HIGH'
            else:
                entry['party_confidence'] = 'LOW'
        
        # Rule 1: Confidence < HIGH (Excluding Rate, and checking Bill Details only if LOW)
        for field in ['date', 'katta', 'party']:
            confidence = entry.get(f'{field}_confidence')
            if confidence in ['MEDIUM', 'LOW']:
                flags.append({
                    'type': 'LOW_CONFIDENCE',
                    'field': field,
                    'value': entry.get(field),
                    'confidence': confidence,
                    'severity': 'HIGH' if confidence == 'LOW' else 'MEDIUM',
                    'message': f'{field.replace("_", " ").title()} has {confidence} confidence (legibility issue)'
                })
        
        bill_details_conf = entry.get('bill_details_confidence')
        if bill_details_conf == 'LOW':
            flags.append({
                'type': 'LOW_CONFIDENCE',
                'field': 'bill_details',
                'value': entry.get('bill_details'),
                'confidence': 'LOW',
                'severity': 'HIGH',
                'message': 'Bill Details has LOW confidence (legibility issue)'
            })
        
        # Rule 2: Party = UNCLEAR
        party = entry.get('party', 'UNCLEAR')
        if party == "UNCLEAR" or party == "M/S UNCLEAR":
            flags.append({
                'type': 'UNCLEAR_PARTY',
                'field': 'party',
                'value': party,
                'severity': 'HIGH',
                'message': 'Party name is unclear or could not be matched to master list'
            })
        
        # Rule 3: Date outside bill period
        try:
            entry_date = self._parse_date(entry['date'])
            if not (self.bill_period_start <= entry_date <= self.bill_period_end):
                flags.append({
                    'type': 'DATE_OUT_OF_PERIOD',
                    'field': 'date',
                    'value': entry['date'],
                    'expected_range': f"{self.bill_period_start.strftime('%d-%m-%Y')} to {self.bill_period_end.strftime('%d-%m-%Y')}",
                    'severity': 'HIGH',
                    'message': f"Date {entry['date']} is outside bill period"
                })
        except Exception as e:
            flags.append({
                'type': 'DATE_PARSE_ERROR',
                'field': 'date',
                'value': entry['date'],
                'severity': 'CRITICAL',
                'message': f'Cannot parse date: {str(e)}'
            })
        
        # Rule 4: Confidence anomaly (field isolation)
        if (entry.get('date_confidence') == 'HIGH' and 
            entry.get('katta_confidence') in ['MEDIUM', 'LOW']):
            flags.append({
                'type': 'FIELD_ISOLATION_ANOMALY',
                'fields': ['date', 'katta'],
                'severity': 'MEDIUM',
                'message': 'Date is clear but Katta is unclear → possible field misalignment (check if fields belong to same entry)'
            })
        
        if (entry.get('rate_confidence') == 'HIGH' and 
            entry.get('party_confidence') in ['MEDIUM', 'LOW']):
            flags.append({
                'type': 'FIELD_ISOLATION_ANOMALY',
                'fields': ['rate', 'party'],
                'severity': 'MEDIUM',
                'message': 'Rate is clear but Party is unclear → possible field misalignment'
            })
        
        # Rule 5: Outlier values (sanity check)
        # Parse Katta (supporting commercial units like "30 BAGS" without crash)
        try:
            katta_val = entry['katta']
            import re
            if isinstance(katta_val, str):
                num_match = re.search(r'([\d\.]+)', katta_val)
                if num_match:
                    katta = float(num_match.group(1))
                else:
                    raise ValueError("No numeric part found in katta")
            else:
                katta = float(katta_val)
                
            if katta < self.typical_katta_range[0] or katta > self.typical_katta_range[1]:
                flags.append({
                    'type': 'KATTA_OUTLIER',
                    'field': 'katta',
                    'value': katta_val,
                    'typical_range': f'{self.typical_katta_range[0]}-{self.typical_katta_range[1]}',
                    'severity': 'MEDIUM',
                    'message': f'Katta {katta_val} is outside typical range {self.typical_katta_range[0]}-{self.typical_katta_range[1]}'
                })
        except Exception as e:
            flags.append({
                'type': 'KATTA_PARSE_ERROR',
                'field': 'katta',
                'value': entry.get('katta'),
                'severity': 'HIGH',
                'message': f'Cannot parse katta as number'
            })
        
        # Parse and check Rate (outliers are blanked out in entry)
        try:
            rate_val = entry.get('rate')
            if rate_val is None or str(rate_val).strip() in ['', 'None', 'null']:
                entry['rate'] = ''
                flags.append({
                    'type': 'RATE_MISSING',
                    'field': 'rate',
                    'value': '',
                    'severity': 'MEDIUM',
                    'message': 'Rate is missing'
                })
            else:
                rate = float(rate_val)
                if rate < self.typical_rate_range[0] or rate > self.typical_rate_range[1]:
                    entry['rate'] = ''  # Blank out implausible rate
                    flags.append({
                        'type': 'RATE_OUTLIER',
                        'field': 'rate',
                        'value': rate_val,
                        'typical_range': f'{self.typical_rate_range[0]}-{self.typical_rate_range[1]}',
                        'severity': 'HIGH',
                        'message': f'Rate {rate_val} is implausible and has been left blank'
                    })
        except Exception as e:
            entry['rate'] = ''  # Blank out
            flags.append({
                'type': 'RATE_PARSE_ERROR',
                'field': 'rate',
                'value': entry.get('rate'),
                'severity': 'HIGH',
                'message': f'Cannot parse rate as number, left blank'
            })
        
        # Rule 6: Missing bill details (when confidence is LOW)
        if (not entry.get('bill_details') or entry.get('bill_details', '').strip() == '') and \
           entry.get('bill_details_confidence') == 'LOW':
            flags.append({
                'type': 'MISSING_DETAILS',
                'field': 'bill_details',
                'severity': 'LOW',
                'message': 'Bill details field is empty/unclear. Verify in handwritten bill if details should exist.'
            })
        
        # Rule 7: Digit 6 problem (special handling)
        for field in ['katta']:
            if entry.get(f'{field}_confidence') in ['MEDIUM', 'LOW']:
                field_value = str(entry.get(field, ''))
                if any(char in field_value for char in ['5', '6', '8', '9']):
                    flags.append({
                        'type': 'DIGIT_6_RISK',
                        'field': field,
                        'value': entry.get(field),
                        'severity': 'HIGH',
                        'message': f'{field.title()} contains digits that could be misread (especially 6 vs 5/8/9)'
                    })
                    
        # Check date for digit 6 risk
        if entry.get('date_confidence') in ['MEDIUM', 'LOW']:
            date_value = str(entry.get('date', ''))
            parts = date_value.split('-')
            if len(parts) >= 2:
                day_month = parts[0] + parts[1]
                if any(char in day_month for char in ['0', '6', '8']):
                    flags.append({
                        'type': 'DIGIT_6_RISK',
                        'field': 'date',
                        'value': date_value,
                        'severity': 'HIGH',
                        'message': 'Date contains day/month digits that could be misread (especially 6 vs 0/8)'
                    })
        
        needs_review = len(flags) > 0
        
        return flags, needs_review
    
    def validate_bill(self, extracted_json: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate entire extracted bill and return structured report.
        """
        transactions = extracted_json.get('transactions', [])
        
        validated_entries = []
        flagged_count = 0
        clean_count = 0
        critical_issues = 0
        
        for entry in transactions:
            flags, needs_review = self.validate_entry(entry)
            
            validated_entry = {
                'entry_number': entry.get('entry_number'),
                'original_entry': entry,
                'flags': flags,
                'needs_review': needs_review,
                'flag_count': len(flags)
            }
            
            if needs_review:
                flagged_count += 1
                critical_issues += sum(1 for f in flags if f.get('severity') == 'CRITICAL')
            else:
                clean_count += 1
            
            validated_entries.append(validated_entry)
        
        return {
            'bill_metadata': extracted_json.get('bill_metadata', {}),
            'validation_summary': {
                'total_entries': len(transactions),
                'flagged_entries': flagged_count,
                'clean_entries': clean_count,
                'critical_issues': critical_issues,
                'review_percentage': round((flagged_count / len(transactions) * 100) if transactions else 0, 1)
            },
            'validated_entries': validated_entries
        }


def load_party_list(party_list_file: str) -> Dict[str, str]:
    """
    Load party list from file and create lookup dict with alias support.
    
    Format: "CANONICAL_NAME <> ALIAS" or just "CANONICAL_NAME"
    Returns: {"CANONICAL_NAME": "CANONICAL_NAME", "ALIAS": "CANONICAL_NAME"}
    """
    party_dict = {}
    
    try:
        with open(party_list_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check for alias format
            if '<>' in line:
                parts = line.split('<>')
                canonical = parts[0].strip()
                alias = parts[1].strip() if len(parts) > 1 else canonical
                
                # Add both canonical and alias to lookup
                party_dict[canonical] = canonical
                party_dict[alias] = canonical
            else:
                # Just a single name
                party_dict[line] = line
        
        return party_dict
    except FileNotFoundError:
        print(f"Warning: Party list file not found: {party_list_file}")
        return {}


def generate_verification_report(validation_result: Dict[str, Any]) -> str:
    """
    Generate a redesigned compact HTML verification report for user review.
    """
    validated_entries = validation_result.get('validated_entries', [])
    
    total_entries = len(validated_entries)
    passed_entries = validation_result['validation_summary']['clean_entries']
    flagged_entries = validation_result['validation_summary']['flagged_entries']
    
    date_flags_count = 0
    bill_detail_flags_count = 0
    party_corrections_count = 0
    low_confidence_entries_count = 0
    
    for entry_result in validated_entries:
        original = entry_result['original_entry']
        flags = entry_result['flags']
        
        # Count date flags
        if any(flag.get('field') == 'date' for flag in flags):
            date_flags_count += 1
            
        # Count bill detail flags
        if any(flag.get('field') == 'bill_details' for flag in flags):
            bill_detail_flags_count += 1
            
        # Count party corrections
        original_party = original.get('original_party', original.get('party'))
        resolved_party = original.get('party')
        if original_party != resolved_party and resolved_party != 'UNCLEAR' and original_party != 'UNCLEAR':
            party_corrections_count += 1
            
        # Count low confidence entries
        if any(flag.get('type') == 'LOW_CONFIDENCE' for flag in flags):
            low_confidence_entries_count += 1

    review_percentage = validation_result['validation_summary']['review_percentage']
    client_name = validation_result.get('bill_metadata', {}).get('client_name', 'M/S LALCHAND RAMCHAND, VASHI')
    bill_period = validation_result.get('bill_metadata', {}).get('bill_period', 'April 2025 - March 2026')

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bill Verification Report</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --primary: #1e3a8a;
            --primary-light: #3b82f6;
            --bg-main: #f8fafc;
            --card-bg: #ffffff;
            --text-dark: #0f172a;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --success: #22c55e;
            --success-bg: #f0fdf4;
            --warning: #eab308;
            --warning-bg: #fefce8;
            --danger: #ef4444;
            --danger-bg: #fef2f2;
            --info: #06b6d4;
            --info-bg: #ecfeff;
        }}
        
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-main);
            color: var(--text-dark);
            line-height: 1.5;
            padding: 30px 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .header {{
            background: linear-gradient(135deg, var(--primary), #1e40af);
            color: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 25px;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        }}
        
        .header h1 {{
            font-size: 24px;
            font-weight: 700;
            margin-bottom: 8px;
        }}
        
        .header p {{
            font-size: 14px;
            opacity: 0.9;
        }}
        
        .meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
            padding-top: 20px;
        }}
        
        .meta-item .label {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            opacity: 0.7;
        }}
        
        .meta-item .value {{
            font-size: 14px;
            font-weight: 600;
            margin-top: 4px;
        }}
        
        /* Stats Cards */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
            transition: transform 0.2s;
        }}
        
        .stat-card:hover {{
            transform: translateY(-2px);
        }}
        
        .stat-card .label {{
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        
        .stat-card .value {{
            font-size: 22px;
            font-weight: 700;
            margin-top: 5px;
            color: var(--primary);
        }}
        
        .stat-card.flagged .value {{ color: var(--danger); }}
        .stat-card.passed .value {{ color: var(--success); }}
        
        /* Table styles */
        .table-container {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
            margin-bottom: 30px;
        }}
        
        .actions-bar {{
            padding: 15px 20px;
            border-bottom: 1px solid var(--border);
            background: #f8fafc;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .actions-bar h2 {{
            font-size: 16px;
            font-weight: 600;
        }}
        
        .btn {{
            background-color: var(--primary-light);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: background 0.2s;
        }}
        
        .btn:hover {{
            background-color: var(--primary);
        }}
        
        .btn-secondary {{
            background-color: #cbd5e1;
            color: var(--text-dark);
            margin-left: 10px;
        }}
        
        .btn-secondary:hover {{
            background-color: #94a3b8;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
        }}
        
        th {{
            background-color: #f1f5f9;
            color: var(--text-muted);
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            padding: 12px 20px;
            border-bottom: 1px solid var(--border);
        }}
        
        td {{
            padding: 14px 20px;
            border-bottom: 1px solid var(--border);
            font-size: 13px;
        }}
        
        .entry-row {{
            cursor: pointer;
            transition: background 0.15s;
        }}
        
        .entry-row:hover {{
            background-color: #f8fafc;
        }}
        
        .entry-row.flagged-row {{
            background-color: rgba(239, 68, 68, 0.01);
        }}
        
        .entry-row.flagged-row:hover {{
            background-color: rgba(239, 68, 68, 0.03);
        }}
        
        /* Status Badges */
        .badge {{
            display: inline-block;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: 600;
            border-radius: 4px;
            text-transform: uppercase;
        }}
        
        .badge-pass {{
            background-color: var(--success-bg);
            color: var(--success);
            border: 1px solid rgba(34, 197, 94, 0.2);
        }}
        
        .badge-review {{
            background-color: var(--danger-bg);
            color: var(--danger);
            border: 1px solid rgba(239, 68, 68, 0.2);
        }}
        
        /* Confidence Badges */
        .conf-badge {{
            display: inline-block;
            font-size: 10px;
            font-weight: 500;
            padding: 2px 6px;
            border-radius: 3px;
        }}
        
        .conf-high {{
            background-color: var(--success-bg);
            color: var(--success);
        }}
        
        .conf-medium {{
            background-color: var(--warning-bg);
            color: var(--warning);
        }}
        
        .conf-low {{
            background-color: var(--danger-bg);
            color: var(--danger);
        }}
        
        /* Details row expansion */
        .details-row {{
            background-color: #f8fafc;
        }}
        
        .details-container {{
            padding: 20px;
            border-left: 4px solid var(--primary-light);
            background: #ffffff;
            margin: 10px 20px;
            border-radius: 6px;
            box-shadow: inset 0 2px 4px 0 rgba(0, 0, 0, 0.03), 0 1px 3px 0 rgba(0,0,0,0.05);
        }}
        
        .details-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 15px;
        }}
        
        .detail-field {{
            border: 1px solid var(--border);
            padding: 10px;
            border-radius: 6px;
            background: #fafafa;
        }}
        
        .detail-field .label {{
            font-size: 10px;
            color: var(--text-muted);
            text-transform: uppercase;
            font-weight: 600;
        }}
        
        .detail-field .value {{
            font-size: 13px;
            font-weight: 600;
            margin-top: 4px;
        }}
        
        .detail-field .original-val {{
            font-size: 11px;
            color: var(--text-muted);
            font-style: italic;
            margin-top: 2px;
            border-top: 1px dashed var(--border);
            padding-top: 2px;
        }}
        
        .issues-section {{
            margin-top: 15px;
            border-top: 1px solid var(--border);
            padding-top: 15px;
        }}
        
        .issues-title {{
            font-size: 12px;
            font-weight: 600;
            color: var(--danger);
            margin-bottom: 8px;
        }}
        
        .flag-item {{
            background-color: var(--danger-bg);
            border-left: 3px solid var(--danger);
            padding: 10px;
            margin-bottom: 8px;
            border-radius: 4px;
            font-size: 12px;
        }}
        
        .flag-item.medium {{
            background-color: var(--warning-bg);
            border-left-color: var(--warning);
            color: #854d0e;
        }}
        
        .flag-item.low {{
            background-color: var(--info-bg);
            border-left-color: var(--info);
            color: #0e7490;
        }}
        
        .action-required {{
            margin-top: 12px;
            color: var(--danger);
            font-weight: 600;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <div class="header">
            <h1>Bill Verification Report</h1>
            <p>Verification dashboard for Haroon & Sons bill extraction. Click any row to expand details and review flags.</p>
            <div class="meta-grid">
                <div class="meta-item">
                    <div class="label">Client Name</div>
                    <div class="value">{client_name}</div>
                </div>
                <div class="meta-item">
                    <div class="label">Bill Period</div>
                    <div class="value">{bill_period}</div>
                </div>
                <div class="meta-item">
                    <div class="label">Status</div>
                    <div class="value">{"⚠️ Review Required" if flagged_entries > 0 else "✓ Processed"}</div>
                </div>
            </div>
        </div>
        
        <!-- Summary Stats Grid -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="label">Total Entries</div>
                <div class="value">{total_entries}</div>
            </div>
            <div class="stat-card passed">
                <div class="label">Passed</div>
                <div class="value">{passed_entries}</div>
            </div>
            <div class="stat-card flagged">
                <div class="label">Flagged</div>
                <div class="value">{flagged_entries}</div>
            </div>
            <div class="stat-card">
                <div class="label">Review %</div>
                <div class="value">{review_percentage}%</div>
            </div>
            <div class="stat-card">
                <div class="label">Date Flags</div>
                <div class="value">{date_flags_count}</div>
            </div>
            <div class="stat-card">
                <div class="label">Bill Flags</div>
                <div class="value">{bill_detail_flags_count}</div>
            </div>
            <div class="stat-card">
                <div class="label">Party Normalized</div>
                <div class="value">{party_corrections_count}</div>
            </div>
            <div class="stat-card">
                <div class="label">Low Conf.</div>
                <div class="value">{low_confidence_entries_count}</div>
            </div>
        </div>
        
        <!-- Table container -->
        <div class="table-container">
            <div class="actions-bar">
                <h2>Transactions Checklist</h2>
                <div>
                    <button class="btn" onclick="expandAllFlagged()">Expand Flagged</button>
                    <button class="btn btn-secondary" onclick="collapseAll()">Collapse All</button>
                </div>
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th style="width: 80px;">Entry</th>
                        <th>Date</th>
                        <th>Qty</th>
                        <th>Rate</th>
                        <th>Party</th>
                        <th>Bill Details</th>
                        <th>Status</th>
                        <th>Flags</th>
                    </tr>
                </thead>
                <tbody>
"""

    for entry_result in validated_entries:
        entry = entry_result['original_entry']
        flags = entry_result['flags']
        needs_review = entry_result['needs_review']
        entry_num = entry_result['entry_number']
        
        status_badge = f'<span class="badge badge-review">Review</span>' if needs_review else f'<span class="badge badge-pass">Pass</span>'
        row_class = 'flagged-row' if needs_review else 'clean-row'
        
        # Gather flag summary
        flag_summary_list = []
        for flag in flags:
            f_type = flag.get('type', '')
            # shorten type for summary column
            short_type = f_type.replace('_OUTLIER', '').replace('_RISK', '').replace('LOW_', '').replace('UNCLEAR_', '').title()
            if short_type not in flag_summary_list:
                flag_summary_list.append(short_type)
        
        flags_column = ", ".join(flag_summary_list) if flags else "-"
        
        html += f"""
                    <tr class="entry-row {row_class}" onclick="toggleDetails('{entry_num}')">
                        <td><strong>{entry_num}</strong></td>
                        <td><span class="conf-badge conf-{entry.get('date_confidence', 'high').lower()}">{entry.get('date_confidence')}</span></td>
                        <td><span class="conf-badge conf-{entry.get('katta_confidence', 'high').lower()}">{entry.get('katta_confidence')}</span></td>
                        <td><span class="conf-badge conf-{entry.get('rate_confidence', 'high').lower()}">{entry.get('rate_confidence')}</span></td>
                        <td><span class="conf-badge conf-{entry.get('party_confidence', 'high').lower()}">{entry.get('party_confidence')}</span></td>
                        <td><span class="conf-badge conf-{entry.get('bill_details_confidence', 'high').lower()}">{entry.get('bill_details_confidence')}</span></td>
                        <td>{status_badge}</td>
                        <td style="color: var(--text-muted); font-size: 11px;">{flags_column}</td>
                    </tr>
                    <tr id="details-{entry_num}" class="details-row" style="display: none;">
                        <td colspan="8">
                            <div class="details-container">
                                <h3 style="font-size: 14px; margin-bottom: 12px; color: var(--primary);">Entry {entry_num} Extracted Values</h3>
                                <div class="details-grid">
                                    <div class="detail-field">
                                        <div class="label">Date</div>
                                        <div class="value">{entry.get('date')}</div>
                                    </div>
                                    <div class="detail-field">
                                        <div class="label">Katta / Quantity</div>
                                        <div class="value">{entry.get('katta')}</div>
                                    </div>
                                    <div class="detail-field">
                                        <div class="label">Rate</div>
                                        <div class="value">{entry.get('rate') if entry.get('rate') != "" else "(Blank / Missing)"}</div>
                                        {f'<div class="original-val">Original: {entry_result.get("original_entry", {}).get("rate")}</div>' if entry.get('rate') == "" and entry_result.get("original_entry", {}).get("rate") else ""}
                                    </div>
                                    <div class="detail-field">
                                        <div class="label">Party Name</div>
                                        <div class="value">{entry.get('party')}</div>
                                        {f'<div class="original-val">Original: {entry.get("original_party")}</div>' if entry.get('party') != entry.get('original_party') else ""}
                                    </div>
                                    <div class="detail-field">
                                        <div class="label">Bill Details</div>
                                        <div class="value">{entry.get('bill_details') or "(Empty)"}</div>
                                    </div>
                                </div>
        """
        
        if flags:
            html += """
                                <div class="issues-section">
                                    <div class="issues-title">Detected Issues Requiring Review:</div>
            """
            for flag in flags:
                sev = flag.get('severity', 'MEDIUM').lower()
                html += f"""
                                    <div class="flag-item {sev}">
                                        <strong>{flag.get('type')}:</strong> {flag.get('message')}
                                    </div>
                """
            html += """
                                    <div class="action-required">
                                        ➜ Action Required: Check handwritten bill. Verify the flagged fields above. Correct the final Excel output if needed.
                                    </div>
                                </div>
            """
        else:
            html += """
                                <div style="color: var(--success); font-size: 12px; font-weight: 500; margin-top: 10px;">
                                    ✓ This entry passed all validation checks cleanly. No action required.
                                </div>
            """
            
        html += """
                            </div>
                        </td>
                    </tr>
        """

    html += """
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        function toggleDetails(id) {
            var row = document.getElementById("details-" + id);
            if (row.style.display === "none") {
                row.style.display = "table-row";
            } else {
                row.style.display = "none";
            }
        }
        
        function expandAllFlagged() {
            var flaggedRows = document.querySelectorAll(".flagged-row");
            flaggedRows.forEach(function(row) {
                var entryNum = row.cells[0].innerText.trim();
                var details = document.getElementById("details-" + entryNum);
                if (details) {
                    details.style.display = "table-row";
                }
            });
        }
        
        function collapseAll() {
            var detailsRows = document.querySelectorAll(".details-row");
            detailsRows.forEach(function(row) {
                row.style.display = "none";
            });
        }
    </script>
</body>
</html>
"""

    return html
