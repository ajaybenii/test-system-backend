from dotenv import load_dotenv

import os
import hashlib

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict
from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError


app = FastAPI(title="Test System Backend")

load_dotenv()

# MongoDB connection
MONGO_URI = os.environ["MONGODB_URI"]
client = AsyncIOMotorClient(MONGO_URI)
db = client.test_system

class AnswerEvent(BaseModel):
    question: str
    answer: str
    timestamp: datetime

class AttemptSummary(BaseModel):
    attempt_id: str
    answers: Dict[str, str]
    total_score: int
    last_updated: datetime

class Analytics(BaseModel):
    attempt_id: str
    total_score: int
    questions_answered: int
    question_updates: Dict[str, datetime]

def generate_event_key(attempt_id: str, question: str, answer: str, timestamp: datetime) -> str:
    """Generate unique key for event deduplication"""
    data = f"{attempt_id}:{question}:{answer}:{timestamp.isoformat()}"
    return hashlib.md5(data.encode()).hexdigest()

@app.on_event("startup")
async def create_indexes():
    """Create MongoDB indexes for performance and uniqueness"""
    # Unique index to prevent duplicate events
    await db.events.create_index([
        ("attempt_id", 1),
        ("event_key", 1)
    ], unique=True)
    

    # Index for fast attempt queries
    await db.attempts.create_index("attempt_id", unique=True)
    
    # Compound index for analytics queries
    await db.events.create_index([
        ("attempt_id", 1),
        ("question", 1),
        ("timestamp", -1)  # Newest first
    ])

@app.post("/attempts/{attempt_id}/events")
async def handle_event(attempt_id: str, event: AnswerEvent):
    """Handle answer event with deduplication and ordering logic"""
    
    # Generate unique event key for deduplication
    event_key = generate_event_key(attempt_id, event.question, event.answer, event.timestamp)
    
    # Try to store the event (will fail if duplicate due to unique index)
    event_doc = {
        "attempt_id": attempt_id,
        "event_key": event_key,
        "question": event.question,
        "answer": event.answer,
        "timestamp": event.timestamp,
        "created_at": datetime.utcnow()
    }
    
    try:
        await db.events.insert_one(event_doc)
    except DuplicateKeyError:
        # Duplicate event - ignore silently (idempotency)
        return {"status": "ignored", "reason": "duplicate_event"}
    
    # Check if this is the latest event for this question
    latest_event = await db.events.find_one(
        {
            "attempt_id": attempt_id,
            "question": event.question
        },
        sort=[("timestamp", -1)]  # Get newest first
    )
    
    # Only update attempt if this is the latest event for this question
    if latest_event and latest_event["event_key"] == event_key:
        # Update attempt summary atomically
        await db.attempts.update_one(
            {"attempt_id": attempt_id},
            {
                "$set": {
                    f"answers.{event.question}": event.answer,
                    "last_updated": event.timestamp
                },
                "$setOnInsert": {
                    "attempt_id": attempt_id,
                    "created_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        # Recalculate total score (simple scoring: 1 point per answered question)
        answers_count = await db.events.distinct("question", {"attempt_id": attempt_id})
        await db.attempts.update_one(
            {"attempt_id": attempt_id},
            {"$set": {"total_score": len(answers_count)}}
        )
        
        return {"status": "processed", "latest": True}
    
    return {"status": "processed", "latest": False, "reason": "older_event"}

@app.get("/attempts/{attempt_id}")
async def get_attempt(attempt_id: str):
    """Get attempt summary with latest answers and score"""
    
    attempt = await db.attempts.find_one({"attempt_id": attempt_id})
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    
    return AttemptSummary(
        attempt_id=attempt["attempt_id"],
        answers=attempt.get("answers", {}),
        total_score=attempt.get("total_score", 0),
        last_updated=attempt.get("last_updated", attempt.get("created_at"))
    )

@app.get("/analytics/attempts/{attempt_id}")
async def get_analytics(attempt_id: str):
    """Get analytics for an attempt"""
    
    # Get latest event for each question
    pipeline = [
        {"$match": {"attempt_id": attempt_id}},
        {"$sort": {"timestamp": -1}},
        {"$group": {
            "_id": "$question",
            "last_updated": {"$first": "$timestamp"}
        }}
    ]
    
    question_updates = {}
    async for doc in db.events.aggregate(pipeline):
        question_updates[doc["_id"]] = doc["last_updated"]
    
    # Get total score from attempt summary
    attempt = await db.attempts.find_one({"attempt_id": attempt_id})
    total_score = attempt.get("total_score", 0) if attempt else 0
    
    return Analytics(
        attempt_id=attempt_id,
        total_score=total_score,
        questions_answered=len(question_updates),
        question_updates=question_updates
    )