import pdfplumber
import pandas as pd
import re
from datetime import datetime
from typing import List, Dict


class BankStatementParser:
    """Parse bank statements from PDF or CSV files"""

    def __init__(self):
        self.transactions = []

    def parse_pdf(self, file_path: str) -> List[Dict]:
        """Extract transactions from PDF bank statement"""
        transactions = []

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    # Try to extract table first
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            parsed = self._parse_table(table)
                            transactions.extend(parsed)
                    else:
                        # Fallback to text extraction
                        parsed = self._parse_text(text)
                        transactions.extend(parsed)

        return transactions

    def parse_csv(self, file_path: str) -> List[Dict]:
        """Extract transactions from CSV bank statement"""
        transactions = []

        try:
            df = pd.read_csv(file_path)

            # Common column name patterns
            date_cols = [
                col
                for col in df.columns
                if any(
                    keyword in col.lower()
                    for keyword in ["date", "posted", "transaction"]
                )
            ]
            desc_cols = [
                col
                for col in df.columns
                if any(
                    keyword in col.lower()
                    for keyword in [
                        "description",
                        "memo",
                        "merchant",
                        "details",
                        "payee",
                    ]
                )
            ]
            amount_cols = [
                col
                for col in df.columns
                if any(
                    keyword in col.lower() for keyword in ["amount", "debit", "credit"]
                )
            ]

            for _, row in df.iterrows():
                try:
                    date_str = row[date_cols[0]] if date_cols else None
                    description = str(row[desc_cols[0]]) if desc_cols else ""
                    amount_str = str(row[amount_cols[0]]) if amount_cols else "0"

                    # Parse date
                    date = self._parse_date(date_str) if date_str else datetime.now()

                    # Parse amount (handle negatives, remove currency symbols)
                    amount = self._parse_amount(amount_str)

                    if amount != 0:
                        transactions.append(
                            {
                                "date": date,
                                "description": description.strip(),
                                "amount": abs(amount),
                                "merchant": self._extract_merchant(description),
                            }
                        )
                except Exception:
                    continue

        except Exception as e:
            print(f"Error parsing CSV: {e}")

        return transactions

    def _parse_table(self, table: List[List]) -> List[Dict]:
        """Parse transactions from table format"""
        transactions = []

        if not table or len(table) < 2:
            return transactions

        # Assume first row is headers
        headers = [str(h).lower() if h else "" for h in table[0]]

        for row in table[1:]:
            if len(row) < 2:
                continue

            try:
                transaction = {}
                for i, header in enumerate(headers):
                    if i < len(row) and row[i]:
                        value = str(row[i]).strip()

                        if "date" in header:
                            transaction["date"] = self._parse_date(value)
                        elif any(
                            k in header
                            for k in ["description", "memo", "merchant", "details"]
                        ):
                            transaction["description"] = value
                        elif any(k in header for k in ["amount", "debit", "credit"]):
                            transaction["amount"] = self._parse_amount(value)

                if "description" in transaction and transaction.get("amount", 0) != 0:
                    transaction["merchant"] = self._extract_merchant(
                        transaction["description"]
                    )
                    transactions.append(transaction)
            except Exception:
                continue

        return transactions

    def _parse_text(self, text: str) -> List[Dict]:
        """Parse transactions from unstructured text"""
        transactions = []
        lines = text.split("\n")

        # Common patterns for transaction lines (including French dates)
        date_pattern = (
            r"\d{1,2}[.\s]+(janv|févr|mars|avr|mai|juin|juil|août|"
            r"sept|oct|nov|déc)[.\s]+\d{2,4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
        )
        amount_pattern = r"€?\s*\d+[.,]\d+"

        # French month abbreviations (map to English for dateutil)
        # Order matters: longer abbreviations first to avoid partial matches
        month_map = {
            "janv": "january",
            "févr": "february",
            "fév": "february",
            "mars": "march",
            "avr": "april",
            "mai": "may",
            "juin": "june",
            "juil": "july",
            "août": "august",
            "sept": "september",
            "oct": "october",
            "nov": "november",
            "déc": "december",
        }

        # Skip header lines
        skip_keywords = [
            "Relevé",
            "Généré le",
            "Transactions du compte",
            "Date",
            "Description",
            "Argent sortant",
            "Argent entrant",
            "Solde",
            "Résumé",
            "COMPTE",
            "TOTAL",
            "Renvoyé",
            "Page",
        ]

        current_date = None
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Skip header/summary lines
            if any(kw in line for kw in skip_keywords):
                continue

            # Extract date (try French format first)
            date_match = re.search(date_pattern, line, re.IGNORECASE)
            if date_match:
                date_str = date_match.group()
                try:
                    # Try to parse French format (sort by length desc)
                    sorted_months = sorted(month_map.items(), key=lambda x: -len(x[0]))
                    for fr_month, en_month in sorted_months:
                        if fr_month in date_str.lower():
                            date_str_eng = date_str.lower().replace(fr_month, en_month)
                            current_date = self._parse_date(date_str_eng)
                            break
                    else:
                        # Try normal format
                        current_date = self._parse_date(date_str)
                except Exception:
                    pass

            # Extract amount with € symbol
            amount_match = re.search(amount_pattern, line)
            if amount_match and current_date:
                amount_str = (
                    amount_match.group().replace("€", "").replace(",", ".").strip()
                )
                try:
                    amount = abs(float(amount_str))
                    if amount > 0.01:  # Filter out tiny amounts
                        # Get merchant name (usually before the amount)
                        desc = line.split("€")[0].strip() if "€" in line else line
                        # Clean up description
                        desc = re.sub(r"\s+\d+[.,]\d+\s*$", "", desc).strip()

                        transactions.append(
                            {
                                "date": current_date,
                                "description": desc,
                                "amount": amount,
                                "merchant": self._extract_merchant(desc),
                            }
                        )
                except ValueError:
                    continue

        return transactions

    def _parse_date(self, date_str: str) -> datetime:
        """Parse various date formats"""
        from dateutil import parser

        if isinstance(date_str, datetime):
            return date_str

        try:
            return parser.parse(str(date_str))
        except Exception:
            return datetime.now()

    def _parse_amount(self, amount_str: str) -> float:
        """Parse amount string to float"""
        if isinstance(amount_str, (int, float)):
            return float(amount_str)

        # Remove currency symbols and commas
        cleaned = str(amount_str).replace("$", "").replace(",", "").strip()

        try:
            return float(cleaned)
        except ValueError:
            return 0.0

    def _extract_merchant(self, description: str) -> str:
        """Extract merchant name from transaction description"""
        # Common patterns: "MERCHANT NAME", "Merchant Name", etc.
        # Remove common prefixes
        desc = description.upper()

        # Remove transaction codes, card numbers, etc.
        desc = re.sub(r"\d{4,}", "", desc)  # Remove long numbers
        desc = re.sub(r"\s+", " ", desc).strip()

        # Return first meaningful words (up to 3 words typically)
        words = desc.split()[:3]
        return " ".join(words) if words else description[:30]
