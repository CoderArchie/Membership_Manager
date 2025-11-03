import imaplib
import email
from email.header import decode_header
from bs4 import BeautifulSoup
import re
from datetime import datetime
from typing import List, Dict, Optional
from config import Config


class EmailParser:
    """Parse emails to extract transaction information"""

    def __init__(self):
        self.imap = None

    def connect(
        self, host: str = None, port: int = None, user: str = None, password: str = None
    ):
        """Connect to IMAP server"""
        host = host or Config.EMAIL_HOST
        port = port or Config.EMAIL_PORT
        user = user or Config.EMAIL_USER
        password = password or Config.EMAIL_PASSWORD

        if not user or not password:
            raise ValueError("Email credentials not configured")

        try:
            self.imap = imaplib.IMAP4_SSL(host, port)
            self.imap.login(user, password)
            return True
        except Exception as e:
            print(f"Error connecting to email: {e}")
            return False

    def parse_emails_from_imap(
        self,
        folder: str = "INBOX",
        sender_filter: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Parse emails from IMAP server"""
        if not self.imap:
            if not self.connect():
                return []

        transactions = []

        try:
            self.imap.select(folder)

            # Search for emails (optionally filter by sender)
            search_criteria = "ALL"
            if sender_filter:
                search_criteria = f'(FROM "{sender_filter}")'

            status, messages = self.imap.search(None, search_criteria)

            if status != "OK":
                return []

            email_ids = messages[0].split()[-limit:]

            for email_id in reversed(email_ids):  # Start with newest
                status, msg_data = self.imap.fetch(email_id, "(RFC822)")

                if status == "OK":
                    email_body = msg_data[0][1]
                    email_message = email.message_from_bytes(email_body)

                    parsed = self._parse_email_message(email_message)
                    if parsed:
                        transactions.extend(parsed)

        except Exception as e:
            print(f"Error parsing emails: {e}")
        finally:
            if self.imap:
                self.imap.close()

        return transactions

    def parse_email_file(self, file_path: str) -> List[Dict]:
        """Parse a single email file"""
        with open(file_path, "rb") as f:
            email_message = email.message_from_bytes(f.read())
            return self._parse_email_message(email_message)

    def _parse_email_message(self, email_message: email.message.Message) -> List[Dict]:
        """Extract transaction info from email message"""
        transactions = []

        # Get subject and body
        subject = self._decode_header(email_message["Subject"])
        body = self._get_email_body(email_message)

        # Common patterns for transaction emails
        amount_pattern = r"[\$£€]?\s*(\d+[.,]?\d*)"

        # Extract date from email
        email_date = email_message.get("Date")
        parsed_date = datetime.now()
        if email_date:
            try:
                from email.utils import parsedate_to_datetime

                parsed_date = parsedate_to_datetime(email_date)
            except Exception:
                pass

        # Look for transaction patterns in subject and body
        text_to_parse = f"{subject}\n{body}"

        # Try to extract structured transaction info
        # Pattern: "charged $XX.XX", "payment of $XX.XX", etc.
        charge_patterns = [
            r"charged\s+[\$£€]?(\d+[.,]?\d*)",
            r"payment\s+of\s+[\$£€]?(\d+[.,]?\d*)",
            r"[\$£€](\d+[.,]?\d*)\s+(?:was|has been)",
            r"amount[:\s]+[\$£€]?(\d+[.,]?\d*)",
        ]

        amounts_found = []
        for pattern in charge_patterns:
            matches = re.finditer(pattern, text_to_parse, re.IGNORECASE)
            for match in matches:
                try:
                    amount = float(match.group(1).replace(",", ""))
                    if amount > 0.01:
                        amounts_found.append((amount, match.start()))
                except:
                    continue

        # Extract merchant from subject or body
        merchant = self._extract_merchant_from_email(subject, body)

        # Create transaction entries
        if amounts_found:
            for amount, _ in amounts_found:
                transactions.append(
                    {
                        "date": parsed_date,
                        "description": f"{merchant} - {subject}",
                        "amount": amount,
                        "merchant": merchant,
                    }
                )
        elif (
            amounts_found == [] and merchant
        ):  # No amount found but merchant identified
            # Try to find amount in body more aggressively
            amount_matches = re.finditer(amount_pattern, text_to_parse)
            for match in amount_matches:
                try:
                    amount = float(match.group(1).replace(",", ""))
                    if 1.0 <= amount <= 10000.0:  # Reasonable range
                        transactions.append(
                            {
                                "date": parsed_date,
                                "description": f"{merchant} - {subject}",
                                "amount": amount,
                                "merchant": merchant,
                            }
                        )
                        break
                except:
                    continue

        return transactions

    def _decode_header(self, header: str) -> str:
        """Decode email header"""
        if not header:
            return ""

        decoded = decode_header(header)
        decoded_string = ""

        for part, encoding in decoded:
            if isinstance(part, bytes):
                decoded_string += part.decode(encoding or "utf-8", errors="ignore")
            else:
                decoded_string += part

        return decoded_string

    def _get_email_body(self, email_message: email.message.Message) -> str:
        """Extract email body text"""
        body = ""

        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))

                if (
                    content_type == "text/plain"
                    and "attachment" not in content_disposition
                ):
                    try:
                        body_bytes = part.get_payload(decode=True)
                        charset = part.get_content_charset() or "utf-8"
                        body += body_bytes.decode(charset, errors="ignore")
                    except Exception:
                        pass
                elif content_type == "text/html":
                    try:
                        html_body = part.get_payload(decode=True)
                        charset = part.get_content_charset() or "utf-8"
                        html_content = html_body.decode(charset, errors="ignore")
                        soup = BeautifulSoup(html_content, "html.parser")
                        body += soup.get_text()
                    except Exception:
                        pass
        else:
            try:
                body_bytes = email_message.get_payload(decode=True)
                charset = email_message.get_content_charset() or "utf-8"
                body = body_bytes.decode(charset, errors="ignore")
            except Exception:
                pass

        return body

    def _extract_merchant_from_email(self, subject: str, body: str) -> str:
        """Extract merchant name from email subject or body"""
        # Common patterns: "Receipt from [Merchant]", "[Merchant] - Payment", etc.
        text = f"{subject} {body}".upper()

        # Remove common email prefixes
        patterns_to_remove = [
            r"RECEIPT\s+FROM\s+",
            r"PAYMENT\s+(?:RECEIPT|CONFIRMATION)\s+FROM\s+",
            r"CHARGE\s+(?:FROM|AT)\s+",
        ]

        for pattern in patterns_to_remove:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE)

        # Extract first meaningful words (likely merchant name)
        words = text.split()[:3]
        return " ".join(words) if words else subject[:30]
