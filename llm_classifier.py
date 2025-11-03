from typing import List, Dict
from collections import defaultdict
from config import Config

try:
    from openai import OpenAI

    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    from groq import Groq

    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False


class MembershipClassifier:
    """Use LLM to classify transactions as membership vs one-off payments"""

    def __init__(self):
        self.client = None
        self.model_name = None
        self.provider = None

        # Priority: Groq > Ollama > OpenAI
        if HAS_GROQ and Config.GROQ_API_KEY:
            self.client = Groq(api_key=Config.GROQ_API_KEY)
            self.model_name = Config.GROQ_MODEL_NAME
            self.provider = "Groq AI"
        # Try Ollama (free, runs locally)
        elif Config.OLLAMA_BASE_URL:
            self.client = OpenAI(
                base_url=Config.OLLAMA_BASE_URL,
                api_key="ollama",  # Not needed, but OpenAI client requires it
            )
            self.model_name = Config.OLLAMA_MODEL_NAME
            self.provider = "Ollama AI"
        # Fallback to OpenAI if available
        elif HAS_OPENAI and Config.OPENAI_API_KEY:
            self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
            self.model_name = Config.MODEL_NAME
            self.provider = "OpenAI GPT"

    def classify_transactions(self, transactions: List[Dict]) -> List[Dict]:
        """Classify transactions and return ONLY memberships"""
        if not self.client or not Config.USE_AI_CLASSIFICATION:
            print(
                "Using rule-based classification "
                "(set USE_AI_CLASSIFICATION=true for AI)"
            )
            classified = self._rule_based_classify(transactions)
        else:
            # Process in batches to avoid rate limits
            batch_size = 20
            classified = []

            for i in range(0, len(transactions), batch_size):
                batch = transactions[i : i + batch_size]
                classified_batch = self._classify_batch(
                    batch, all_transactions=transactions
                )
                classified.extend(classified_batch)

        # Post-process: use frequency analysis to filter out one-time payments
        classified = self._filter_one_time_payments(classified)

        # Return ONLY memberships (filter out non-memberships)
        memberships_only = [t for t in classified if t.get("is_membership")]

        # Add monthly cost estimation
        memberships_only = self._add_monthly_costs(memberships_only)

        return memberships_only

    def _classify_batch(
        self, transactions: List[Dict], all_transactions: List[Dict] = None
    ) -> List[Dict]:
        """Classify a batch of transactions using LLM"""
        import re

        # If all_transactions provided, add global context
        if all_transactions:
            # Count occurrences of each merchant across all transactions
            merchant_counts = {}
            for t in all_transactions:
                merchant = t.get("merchant", "").upper()
                # Normalize merchant name
                date_pattern = r"\d+\s+[A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ]+\.?\s*"
                merchant_clean = re.sub(date_pattern, "", merchant)
                abbrev_pattern = r"^[A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ]+\.\s*"
                merchant_clean = re.sub(abbrev_pattern, "", merchant_clean)
                merchant_clean = re.sub(r"\d+", "", merchant_clean).strip()
                if merchant_clean:
                    merchant_counts[merchant_clean] = (
                        merchant_counts.get(merchant_clean, 0) + 1
                    )

            context = (
                f"\nMerchant frequency across ALL {len(all_transactions)} "
                f"transactions:\n"
            )
            sorted_merchants = sorted(merchant_counts.items(), key=lambda x: -x[1])[:10]
            for merchant, count in sorted_merchants:
                context += f"- {merchant}: {count} occurrence(s)\n"
        else:
            context = ""

        # Prepare prompt with context
        transaction_list = "\n".join(
            [
                f"- {t.get('merchant', 'Unknown')}: "
                f"${t['amount']:.2f} on "
                f"{t['date'].strftime('%Y-%m-%d')} "
                f"({t.get('description', '')[:50]})"
                for t in transactions
            ]
        )

        prompt = (
            "Identify ONLY recurring membership/subscription payments from "
            "the transactions below.\n\n"
            f"{context}"
            "For each transaction:\n"
            "- is_membership: true ONLY if merchant appears several times and with a similar amount paid and similar date in the month\n"
            "- membership_type: Sport/Software/Streaming/News/Services\n"
            "- frequency: Monthly/Weekly/Yearly based on date gaps\n"
            "- category: Clean merchant name (remove dates)\n\n"
            f"Transactions:\n{transaction_list}\n\n"
            "Return JSON array matching input order:\n"
            '[{"is_membership": boolean, "membership_type": string|null, '
            '"frequency": string|null, "category": string}]\n'
        )

        try:
            system_msg = (
                "You are a financial transaction classifier. Analyze "
                "transactions and classify them accurately. Always respond "
                "with valid JSON only."
            )
            params = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt},
                ],
                "temperature": Config.TEMPERATURE,
            }

            # Only add response_format for OpenAI API (not Groq/Ollama)
            if HAS_OPENAI and Config.OPENAI_API_KEY and not HAS_GROQ:
                params["response_format"] = {"type": "json_object"}

            response = self.client.chat.completions.create(**params)

            # Parse response
            content = response.choices[0].message.content

            # Try to extract JSON array
            import json
            import re

            # If wrapped in json_object, extract the array
            try:
                result = json.loads(content)
                if isinstance(result, dict) and "transactions" in result:
                    classifications = result["transactions"]
                elif isinstance(result, list):
                    classifications = result
                else:
                    # Try to find array in the response
                    array_match = re.search(r"\[.*\]", content, re.DOTALL)
                    if array_match:
                        classifications = json.loads(array_match.group())
                    else:
                        classifications = [result]
            except Exception:
                # Fallback: try to extract as list directly
                array_match = re.search(r"\[.*\]", content, re.DOTALL)
                if array_match:
                    classifications = json.loads(array_match.group())
                else:
                    return self._rule_based_classify(transactions)

            # Merge classifications with transactions
            for i, transaction in enumerate(transactions):
                if i < len(classifications):
                    classification = classifications[i]
                    transaction["is_membership"] = classification.get(
                        "is_membership", False
                    )
                    transaction["membership_type"] = classification.get(
                        "membership_type"
                    )
                    transaction["frequency"] = classification.get("frequency")
                    transaction["category"] = classification.get(
                        "category", transaction.get("merchant", "Unknown")
                    )
                else:
                    # Fallback for missing classifications
                    transaction.update(self._classify_single(transaction))

            return transactions

        except Exception as e:
            print(f"Error in LLM classification: {e}")
            return self._rule_based_classify(transactions)

    def _rule_based_classify(self, transactions: List[Dict]) -> List[Dict]:
        """Fallback rule-based classification"""
        classified = []

        for transaction in transactions:
            result = self._classify_single(transaction)
            transaction.update(result)
            classified.append(transaction)

        return classified

    def _classify_single(self, transaction: Dict) -> Dict:
        """Classify a single transaction using rules"""
        description = transaction.get("description", "").upper()
        merchant = transaction.get("merchant", "").upper()
        text = f"{description} {merchant}"

        # Common membership keywords
        membership_keywords = [
            "SUBSCRIPTION",
            "MEMBERSHIP",
            "MONTHLY",
            "ANNUAL",
            "RECURRING",
            "NETFLIX",
            "SPOTIFY",
            "AMAZON PRIME",
            "ADOBE",
            "MICROSOFT 365",
            "MICROSOFT",
            "CURSOR",
            "APPLE",
            "GYM",
            "FITNESS",
            "GOLF",
            "TENNIS",
            "YOGI",
            "PILATES",
            "OFFICE",
            "SOFTWARE",
            "SaaS",
            "CLOUD",
            "NEWS",
            "TIMES",
            "JOURNAL",
            "MAGAZINE",
        ]

        is_membership = any(keyword in text for keyword in membership_keywords)

        # Determine type and category
        import re

        membership_type = None
        frequency = None

        # Clean merchant name for category (remove dates)
        merchant_clean = merchant
        if merchant_clean:
            date_pattern = r"\d+\s+[A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ]+\.?\s*"
            merchant_clean = re.sub(date_pattern, "", merchant_clean)
            abbrev_pattern = r"^[A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ]+\.\s*"
            merchant_clean = re.sub(abbrev_pattern, "", merchant_clean)
            merchant_clean = re.sub(r"\d+", "", merchant_clean).strip()

        if description:
            category = merchant_clean if merchant_clean else description.split()[0]
        else:
            category = merchant_clean if merchant_clean else "Unknown"

        if is_membership:
            if any(
                k in text
                for k in [
                    "GYM",
                    "FITNESS",
                    "GOLF",
                    "TENNIS",
                    "YOGI",
                    "PILATES",
                    "SPORT",
                ]
            ):
                membership_type = "Sport"
            elif any(
                k in text
                for k in [
                    "NETFLIX",
                    "SPOTIFY",
                    "DISNEY",
                    "HULU",
                    "PRIME VIDEO",
                    "STREAMING",
                ]
            ):
                membership_type = "Streaming"
                frequency = "Monthly"
            elif any(
                k in text
                for k in [
                    "ADOBE",
                    "MICROSOFT",
                    "OFFICE",
                    "SOFTWARE",
                    "SaaS",
                    "CURSOR",
                    "APPLE",
                ]
            ):
                membership_type = "Software"
            elif any(k in text for k in ["NEWS", "TIMES", "JOURNAL", "MAGAZINE"]):
                membership_type = "News"
            else:
                membership_type = "Services"

            # Detect frequency
            if "MONTHLY" in text or "MONTH" in text:
                frequency = "Monthly"
            elif "YEARLY" in text or "ANNUAL" in text or "YEAR" in text:
                frequency = "Yearly"
            elif "WEEKLY" in text or "WEEK" in text:
                frequency = "Weekly"
            else:
                frequency = "Monthly"  # Default assumption

        return {
            "is_membership": is_membership,
            "membership_type": membership_type,
            "frequency": frequency,
            "category": category,
        }

    def _filter_one_time_payments(self, transactions: List[Dict]) -> List[Dict]:
        """Filter out one-time payments by analyzing frequency"""
        import re

        # Group by normalized merchant name to count occurrences
        by_merchant = defaultdict(list)

        for t in transactions:
            if t.get("is_membership"):
                # Normalize merchant name by removing dates and numbers
                merchant = t.get("merchant", "").upper()
                # Remove patterns like "21 DÉC.", "8 JUIL.", etc.
                date_pattern = r"\d+\s+[A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ]+\.?\s*"
                merchant_clean = re.sub(date_pattern, "", merchant)
                abbrev_pattern = r"^[A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ]+\.\s*"
                merchant_clean = re.sub(abbrev_pattern, "", merchant_clean)
                # Remove remaining dates and numbers
                merchant_clean = re.sub(r"\d+", "", merchant_clean).strip()
                if not merchant_clean:
                    merchant_clean = "Unknown"
                by_merchant[merchant_clean].append(t)

        # Mark transactions as non-memberships if they only appear once
        for merchant, txns in by_merchant.items():
            if len(txns) == 1:
                # Only one occurrence - likely a one-time payment
                for t in txns:
                    t["is_membership"] = False
                    t["membership_type"] = None
                    t["frequency"] = None

        return transactions

    def _add_monthly_costs(self, memberships: List[Dict]) -> List[Dict]:
        """Add monthly cost estimates to memberships"""
        # Group by category to calculate averages
        by_category = defaultdict(list)

        for t in memberships:
            category = t.get("category", "Unknown")
            by_category[category].append(
                {"amount": t["amount"], "frequency": t.get("frequency", "Monthly")}
            )

        # Calculate monthly costs for each category
        for category, items in by_category.items():
            amounts = [item["amount"] for item in items]
            avg_amount = sum(amounts) / len(amounts)
            frequency = items[0].get("frequency", "Monthly")

            # Convert to monthly cost
            if frequency == "Yearly":
                monthly_cost = avg_amount / 12
            elif frequency == "Weekly":
                monthly_cost = avg_amount * 4.33
            elif frequency == "Quarterly":
                monthly_cost = avg_amount / 3
            elif frequency == "Bi-annual":
                monthly_cost = avg_amount / 6
            else:  # Monthly
                monthly_cost = avg_amount

            # Add to all memberships in this category
            for t in memberships:
                if t.get("category") == category:
                    t["monthly_cost"] = round(monthly_cost, 2)
                    t["total_paid"] = sum(amounts)

        return memberships

    def analyze_frequency(self, transactions: List[Dict]) -> Dict:
        """Analyze payment frequency patterns"""
        # Group by merchant/category
        by_category = defaultdict(list)

        for t in transactions:
            if t.get("is_membership"):
                category = t.get("category", "Unknown")
                by_category[category].append({"date": t["date"], "amount": t["amount"]})

        # Analyze frequency for each category
        frequency_analysis = {}

        for category, payments in by_category.items():
            if len(payments) < 2:
                continue

            # Sort by date
            payments.sort(key=lambda x: x["date"])

            # Calculate intervals
            intervals = []
            for i in range(1, len(payments)):
                delta = payments[i]["date"] - payments[i - 1]["date"]
                intervals.append(delta.days)

            if intervals:
                avg_interval = sum(intervals) / len(intervals)

                # Classify frequency
                if 25 <= avg_interval <= 35:
                    frequency = "Monthly"
                elif 85 <= avg_interval <= 95:
                    frequency = "Quarterly"
                elif 360 <= avg_interval <= 370:
                    frequency = "Yearly"
                elif 175 <= avg_interval <= 185:
                    frequency = "Bi-annual"
                elif 7 <= avg_interval <= 9:
                    frequency = "Weekly"
                else:
                    frequency = f"Every {int(avg_interval)} days"

                frequency_analysis[category] = {
                    "frequency": frequency,
                    "avg_interval_days": avg_interval,
                    "count": len(payments),
                    "total_amount": sum(p["amount"] for p in payments),
                    "avg_amount": (sum(p["amount"] for p in payments) / len(payments)),
                }

        return frequency_analysis
