from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional
import os

from models import init_db, get_db, Transaction
from bank_parser import BankStatementParser
from email_parser import EmailParser
from llm_classifier import MembershipClassifier
from config import Config

app = FastAPI(title="Membership Classifier")

# Initialize database
init_db()

# Create upload directories
os.makedirs(Config.UPLOAD_DIR, exist_ok=True)
os.makedirs(Config.STATEMENTS_DIR, exist_ok=True)
os.makedirs(Config.EMAILS_DIR, exist_ok=True)

# Initialize parsers and classifier
bank_parser = BankStatementParser()
email_parser = EmailParser()
classifier = MembershipClassifier()

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main web interface"""
    with open("static/index.html", "r") as f:
        return f.read()


@app.get("/api/model-info")
async def get_model_info():
    """Get current AI model information"""
    if classifier.provider and classifier.model_name:
        return {
            "model_name": classifier.model_name,
            "model_type": classifier.provider,
            "use_ai": Config.USE_AI_CLASSIFICATION,
        }
    else:
        return {
            "model_name": "Pattern Matching",
            "model_type": "Rule-based",
            "use_ai": False,
        }


@app.post("/api/upload/statement")
async def upload_statement(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload and parse a bank statement"""
    try:
        # Save file
        file_path = os.path.join(Config.STATEMENTS_DIR, file.filename)
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Parse based on file extension
        transactions = []
        if file.filename.endswith(".pdf"):
            transactions = bank_parser.parse_pdf(file_path)
        elif file.filename.endswith(".csv"):
            transactions = bank_parser.parse_csv(file_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format")

        # Classify transactions - returns ONLY memberships
        memberships = classifier.classify_transactions(transactions)

        # Save to database - only memberships are returned now
        for t in memberships:
            db_transaction = Transaction(
                date=t["date"],
                description=t.get("description", ""),
                amount=t["amount"],
                merchant=t.get("merchant", ""),
                is_membership=True,  # Always true since only memberships returned
                membership_type=t.get("membership_type"),
                frequency=t.get("frequency"),
                category=t.get("category", ""),
                source="bank_statement",
            )
            db.add(db_transaction)

        db.commit()

        return {
            "message": (
                f"Found {len(memberships)} recurring memberships "
                f"from {len(transactions)} total transactions"
            ),
            "count": len(memberships),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload/email")
async def upload_email(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload and parse an email file"""
    try:
        # Save file
        file_path = os.path.join(Config.EMAILS_DIR, file.filename)
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Parse email
        transactions = email_parser.parse_email_file(file_path)

        if not transactions:
            return {"message": "No transactions found in email", "count": 0}

        # Classify transactions
        classified = classifier.classify_transactions(transactions)

        # Save to database
        for t in classified:
            db_transaction = Transaction(
                date=t["date"],
                description=t.get("description", ""),
                amount=t["amount"],
                merchant=t.get("merchant", ""),
                is_membership=t.get("is_membership", False),
                membership_type=t.get("membership_type"),
                frequency=t.get("frequency"),
                category=t.get("category", ""),
                source="email",
            )
            db.add(db_transaction)

        db.commit()

        return {
            "message": f"Processed {len(classified)} transactions",
            "count": len(classified),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/fetch/emails")
async def fetch_emails(
    sender_filter: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)
):
    """Fetch and parse emails from IMAP server"""
    try:
        transactions = email_parser.parse_emails_from_imap(
            sender_filter=sender_filter, limit=limit
        )

        if not transactions:
            return {"message": "No transactions found in emails", "count": 0}

        # Classify transactions
        classified = classifier.classify_transactions(transactions)

        # Save to database
        for t in classified:
            db_transaction = Transaction(
                date=t["date"],
                description=t.get("description", ""),
                amount=t["amount"],
                merchant=t.get("merchant", ""),
                is_membership=t.get("is_membership", False),
                membership_type=t.get("membership_type"),
                frequency=t.get("frequency"),
                category=t.get("category", ""),
                source="email",
            )
            db.add(db_transaction)

        db.commit()

        return {
            "message": f"Processed {len(classified)} transactions",
            "count": len(classified),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/transactions")
async def get_transactions(
    is_membership: Optional[bool] = None,
    membership_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get all transactions with optional filters"""
    query = db.query(Transaction)

    if is_membership is not None:
        query = query.filter(Transaction.is_membership == is_membership)

    if membership_type:
        query = query.filter(Transaction.membership_type == membership_type)

    transactions = query.order_by(Transaction.date.desc()).all()

    return [
        {
            "id": t.id,
            "date": t.date.isoformat(),
            "description": t.description,
            "amount": t.amount,
            "merchant": t.merchant,
            "is_membership": t.is_membership,
            "membership_type": t.membership_type,
            "frequency": t.frequency,
            "category": t.category,
            "source": t.source,
        }
        for t in transactions
    ]


@app.get("/api/summary")
async def get_summary(db: Session = Depends(get_db)):
    """Get summary of expenses grouped by type"""
    # Get all membership transactions
    memberships = (
        db.query(Transaction).filter(Transaction.is_membership.is_(True)).all()
    )

    # Group by membership type
    by_type = {}
    by_category = {}

    for t in memberships:
        # Group by type
        mtype = t.membership_type or "Other"
        if mtype not in by_type:
            by_type[mtype] = {"total": 0, "count": 0, "categories": {}}

        by_type[mtype]["total"] += t.amount
        by_type[mtype]["count"] += 1

        # Group by category
        category = t.category or "Unknown"
        if category not in by_category:
            by_category[category] = {
                "total": 0,
                "count": 0,
                "frequency": t.frequency,
                "membership_type": mtype,
            }

        by_category[category]["total"] += t.amount
        by_category[category]["count"] += 1

    # Calculate monthly estimates
    for category, data in by_category.items():
        frequency = data.get("frequency", "Monthly")
        if frequency == "Monthly":
            data["monthly_estimate"] = (
                data["total"] / data["count"] if data["count"] > 0 else 0
            )
        elif frequency == "Yearly":
            data["monthly_estimate"] = (
                (data["total"] / data["count"]) / 12 if data["count"] > 0 else 0
            )
        elif frequency == "Weekly":
            data["monthly_estimate"] = (
                (data["total"] / data["count"]) * 4.33 if data["count"] > 0 else 0
            )
        else:
            data["monthly_estimate"] = 0

    # Calculate totals
    total_membership_spending = sum(t.amount for t in memberships)
    total_monthly_estimate = sum(c["monthly_estimate"] for c in by_category.values())

    return {
        "by_type": by_type,
        "by_category": by_category,
        "total_membership_spending": total_membership_spending,
        "total_monthly_estimate": total_monthly_estimate,
        "total_memberships": len(by_category),
    }


@app.get("/api/frequency-analysis")
async def get_frequency_analysis(db: Session = Depends(get_db)):
    """Get frequency analysis for recurring payments"""
    memberships = (
        db.query(Transaction).filter(Transaction.is_membership.is_(True)).all()
    )

    # Convert to dict format
    transactions_dict = [
        {
            "date": t.date,
            "amount": t.amount,
            "category": t.category,
            "merchant": t.merchant,
        }
        for t in memberships
    ]

    analysis = classifier.analyze_frequency(transactions_dict)

    return analysis


@app.delete("/api/transactions")
async def clear_transactions(db: Session = Depends(get_db)):
    """Clear all transactions from database"""
    db.query(Transaction).delete()
    db.commit()
    return {"message": "All transactions cleared"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
