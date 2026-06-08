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
        
        Returns:
            (resolved_party_name, confidence, flag_message)
        """
        if party_name == "UNCLEAR":
            return "UNCLEAR", 0.0, "Party name marked as UNCLEAR in extraction"
        
        if not self.party_list:
            # No party list provided, can't validate
            return party_name, 1.0, None
        
        # Remove M/S prefix for matching
        party_clean = party_name.replace("M/S ", "").strip()
        
        # Exact match
        if party_clean in self.party_list:
            canonical = self.party_list[party_clean]
            return f"M/S {canonical}", 1.0, None
        
        # Fuzzy match
        best_match = None
        best_score = 0
        
        for key in self.party_list.keys():
            score = self.fuzzy_match(party_clean, key)
            if score > best_score:
                best_score = score
                best_match = key
        
        if best_score >= self.fuzzy_match_threshold:
            canonical = self.party_list[best_match]
            return f"M/S {canonical}", best_score, None
        else:
            # No good match found
            return "UNCLEAR", 0.0, f"Party '{party_name}' not found in master list (closest match: {best_match} with {best_score:.1%} confidence)"
    
    def validate_entry(self, entry: Dict[str, Any]) -> Tuple[List[Dict], bool]:
        """
        Validate single entry and return flags + needs_review boolean.
        
        Returns:
            (flags_list, needs_review_boolean)
        """
        flags = []
        
        # Rule 1: Confidence < HIGH
        for field in ['date', 'katta', 'rate', 'party', 'bill_details']:
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
        
        # Rule 2: Party = UNCLEAR or not in list
        party = entry.get('party', 'UNCLEAR')
        if self.party_list:
            resolved_party, confidence, flag_msg = self.validate_party(party)
            if resolved_party == "UNCLEAR" or confidence < self.fuzzy_match_threshold:
                flags.append({
                    'type': 'UNCLEAR_PARTY',
                    'field': 'party',
                    'value': party,
                    'severity': 'HIGH',
                    'message': flag_msg or 'Party name is unclear or unreadable'
                })
        elif party == "UNCLEAR":
            flags.append({
                'type': 'UNCLEAR_PARTY',
                'field': 'party',
                'value': 'UNCLEAR',
                'severity': 'HIGH',
                'message': 'Party name is unclear or unreadable'
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
        try:
            katta = float(entry['katta'])
            if katta < self.typical_katta_range[0] or katta > self.typical_katta_range[1]:
                flags.append({
                    'type': 'KATTA_OUTLIER',
                    'field': 'katta',
                    'value': katta,
                    'typical_range': f'{self.typical_katta_range[0]}-{self.typical_katta_range[1]}',
                    'severity': 'MEDIUM',
                    'message': f'Katta {katta} is outside typical range {self.typical_katta_range[0]}-{self.typical_katta_range[1]}'
                })
        except Exception as e:
            flags.append({
                'type': 'KATTA_PARSE_ERROR',
                'field': 'katta',
                'value': entry.get('katta'),
                'severity': 'HIGH',
                'message': f'Cannot parse katta as number'
            })
        
        try:
            rate = float(entry['rate'])
            if rate < self.typical_rate_range[0] or rate > self.typical_rate_range[1]:
                flags.append({
                    'type': 'RATE_OUTLIER',
                    'field': 'rate',
                    'value': rate,
                    'typical_range': f'{self.typical_rate_range[0]}-{self.typical_rate_range[1]}',
                    'severity': 'MEDIUM',
                    'message': f'Rate {rate} is outside typical range {self.typical_rate_range[0]}-{self.typical_rate_range[1]}'
                })
        except Exception as e:
            flags.append({
                'type': 'RATE_PARSE_ERROR',
                'field': 'rate',
                'value': entry.get('rate'),
                'severity': 'HIGH',
                'message': f'Cannot parse rate as number'
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
        for field in ['katta', 'rate']:
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
        with open(party_list_file, 'r') as f:
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
    Generate HTML verification report for user review.
    """
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Bill Verification Report</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
            .header { background-color: #2E75B6; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
            .summary { background-color: #e8f4f8; padding: 15px; border-left: 4px solid #2E75B6; margin-bottom: 20px; }
            .summary-stat { display: inline-block; margin-right: 30px; }
            .summary-stat .label { color: #666; font-size: 12px; }
            .summary-stat .value { font-size: 20px; font-weight: bold; color: #2E75B6; }
            .entry { background-color: white; padding: 15px; margin-bottom: 15px; border-radius: 5px; border-left: 4px solid #ccc; }
            .entry.flagged { border-left-color: #d9534f; background-color: #fff5f5; }
            .entry.clean { border-left-color: #5cb85c; background-color: #f5fff5; }
            .entry-header { font-weight: bold; margin-bottom: 10px; }
            .entry-number { color: #666; font-size: 12px; }
            .flag { background-color: #fcf8e3; padding: 10px; margin: 8px 0; border-left: 3px solid #ffc107; font-size: 13px; }
            .flag.high { border-left-color: #d9534f; background-color: #f2dede; }
            .flag.medium { border-left-color: #ffc107; background-color: #fcf8e3; }
            .flag.low { border-left-color: #5bc0de; background-color: #d9edf7; }
            .flag.critical { border-left-color: #c9302c; background-color: #f2dede; font-weight: bold; }
            .field-value { color: #666; font-size: 12px; margin-top: 5px; }
            .confidence-badge { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; margin-left: 5px; }
            .confidence-high { background-color: #5cb85c; color: white; }
            .confidence-medium { background-color: #ffc107; color: white; }
            .confidence-low { background-color: #d9534f; color: white; }
            .action { color: #d9534f; font-weight: bold; margin-top: 10px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Bill Verification Report</h1>
            <p>Review flagged entries. No action needed on clean entries.</p>
        </div>
        
        <div class="summary">
            <div class="summary-stat">
                <div class="label">Total Entries</div>
                <div class="value">""" + str(validation_result['validation_summary']['total_entries']) + """</div>
            </div>
            <div class="summary-stat">
                <div class="label">Flagged (Review)</div>
                <div class="value" style="color: #d9534f;">""" + str(validation_result['validation_summary']['flagged_entries']) + """</div>
            </div>
            <div class="summary-stat">
                <div class="label">Clean (Skip)</div>
                <div class="value" style="color: #5cb85c;">""" + str(validation_result['validation_summary']['clean_entries']) + """</div>
            </div>
            <div class="summary-stat">
                <div class="label">Review %</div>
                <div class="value">""" + str(validation_result['validation_summary']['review_percentage']) + """%</div>
            </div>
        </div>
    """
    
    for entry_result in validation_result['validated_entries']:
        entry = entry_result['original_entry']
        flags = entry_result['flags']
        needs_review = entry_result['needs_review']
        
        entry_class = 'flagged' if needs_review else 'clean'
        status_icon = '⚠️ FLAGGED' if needs_review else '✓ OK'
        
        html += f"""
        <div class="entry {entry_class}">
            <div class="entry-header">
                {status_icon} Entry {entry_result['entry_number']}
                <span class="entry-number">({entry_result['flag_count']} flags)</span>
            </div>
            
            <div style="margin: 10px 0; padding: 10px; background-color: rgba(0,0,0,0.02); border-radius: 3px;">
                <div><strong>Date:</strong> {entry['date']} <span class="confidence-badge confidence-{entry['date_confidence'].lower()}">{entry['date_confidence']}</span></div>
                <div><strong>Katta:</strong> {entry['katta']} <span class="confidence-badge confidence-{entry['katta_confidence'].lower()}">{entry['katta_confidence']}</span></div>
                <div><strong>Rate:</strong> {entry['rate']} <span class="confidence-badge confidence-{entry['rate_confidence'].lower()}">{entry['rate_confidence']}</span></div>
                <div><strong>Party:</strong> {entry['party']} <span class="confidence-badge confidence-{entry['party_confidence'].lower()}">{entry['party_confidence']}</span></div>
                <div><strong>Bill Details:</strong> {entry['bill_details'] or '(empty)'} <span class="confidence-badge confidence-{entry['bill_details_confidence'].lower()}">{entry['bill_details_confidence']}</span></div>
            </div>
        """
        
        if flags:
            html += "<div style='margin-top: 10px;'><strong>Issues:</strong>"
            for flag in flags:
                severity_class = flag.get('severity', 'MEDIUM').lower()
                html += f"""
                <div class="flag {severity_class}">
                    <strong>{flag['type']}</strong>: {flag['message']}
                </div>
                """
            html += "</div>"
        
        if needs_review:
            html += """
            <div class="action">
                ➜ ACTION: Check handwritten bill. Verify this entry. Correct if jumbled or unclear.
            </div>
            """
        
        html += "</div>"
    
    html += """
        <div style="margin-top: 30px; padding: 20px; background-color: #e8f4f8; border-radius: 5px;">
            <h3>Next Steps:</h3>
            <ol>
                <li>Review all <strong>FLAGGED</strong> entries above against the handwritten bill</li>
                <li>Correct any errors (wrong numbers, jumbled fields, unclear party names)</li>
                <li>Once verified, system will generate final XLS</li>
                <li>Do NOT worry about CLEAN entries - they passed validation</li>
            </ol>
        </div>
    </body>
    </html>
    """
    
    return html
