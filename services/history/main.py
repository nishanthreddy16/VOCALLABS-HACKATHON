import datetime
import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header, Depends, status
from pydantic import BaseModel
from sqlalchemy import Column, String, DateTime, JSON, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sakshi_db.db")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class ReconciliationRecord(Base):
    __tablename__ = "reconciliations"
    id = Column(String(50), primary_key=True)
    user_id = Column(String(50), nullable=False, index=True)
    image_url = Column(String(1024), nullable=False)
    audio_url = Column(String(1024), nullable=True)
    transcript = Column(String, nullable=False)
    document_data = Column(JSON, nullable=False)
    result_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Sakshi History Service")

class HistorySaveRequest(BaseModel):
    id: str
    image_url: str
    audio_url: Optional[str] = None
    transcript: str
    document_data: dict
    result_data: dict

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/save")
def save_history(
    record_data: HistorySaveRequest, 
    x_user_id: Optional[str] = Header(None), 
    db = Depends(get_db)
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized: User header missing")
        
    # Check if record already exists
    existing = db.query(ReconciliationRecord).filter(ReconciliationRecord.id == record_data.id).first()
    if existing:
        # Update or ignore. Let's update to support retries
        existing.image_url = record_data.image_url
        existing.audio_url = record_data.audio_url
        existing.transcript = record_data.transcript
        existing.document_data = record_data.document_data
        existing.result_data = record_data.result_data
        db.commit()
        return {"status": "updated", "id": existing.id}
        
    db_record = ReconciliationRecord(
        id=record_data.id,
        user_id=x_user_id,
        image_url=record_data.image_url,
        audio_url=record_data.audio_url,
        transcript=record_data.transcript,
        document_data=record_data.document_data,
        result_data=record_data.result_data
    )
    db.add(db_record)
    db.commit()
    return {"status": "saved", "id": db_record.id}

@app.get("/list")
def list_history(x_user_id: Optional[str] = Header(None), db = Depends(get_db)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized: User header missing")
        
    records = db.query(ReconciliationRecord)\
                .filter(ReconciliationRecord.user_id == x_user_id)\
                .order_by(ReconciliationRecord.created_at.desc())\
                .all()
                
    result = []
    for r in records:
        result.append({
            "id": r.id,
            "user_id": r.user_id,
            "image_url": r.image_url,
            "audio_url": r.audio_url,
            "transcript": r.transcript,
            "document_data": r.document_data,
            "result_data": r.result_data,
            "created_at": r.created_at.isoformat()
        })
    return result

@app.delete("/delete/{comparison_id}")
def delete_history(
    comparison_id: str,
    x_user_id: Optional[str] = Header(None),
    db = Depends(get_db)
):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Unauthorized: User header missing")
        
    record = db.query(ReconciliationRecord)\
               .filter(ReconciliationRecord.id == comparison_id, ReconciliationRecord.user_id == x_user_id)\
               .first()
               
    if not record:
        raise HTTPException(status_code=404, detail="Comparison record not found or access denied")
        
    db.delete(record)
    db.commit()
    return {"status": "deleted", "id": comparison_id}
