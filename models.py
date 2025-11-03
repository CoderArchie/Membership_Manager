from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from config import Config

Base = declarative_base()


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, nullable=False, index=True)
    description = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    merchant = Column(String, index=True)
    is_membership = Column(Boolean, default=False)
    membership_type = Column(String)  # e.g., "Sport", "Software", "Services"
    frequency = Column(String)  # e.g., "Monthly", "Weekly", "Yearly"
    category = Column(String, index=True)  # e.g., "Gym", "Netflix", "Adobe"
    source = Column(String)  # "bank_statement" or "email"
    created_at = Column(DateTime, default=datetime.utcnow)


# Database setup
engine = create_engine(Config.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

