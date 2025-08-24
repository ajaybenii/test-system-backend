# Test System Backend

A backend service for handling test answer events with duplicate prevention and concurrency safety.

## Problem

Handle answer events from an online test platform that may arrive:

* **Duplicated** (network retries)
* **Out of order** (network delays)
* **Simultaneously** (concurrent users)

## Solution

* Store all events for audit trail
* Use unique indexes to prevent duplicates
* Only apply latest events to current answers
* MongoDB atomic operations for concurrency safety

## Quick Start

### 1. Install

bash

```bash
pip install -r requirements.txt
```

### 2. Setup Environment

bash

```bash
# Create .env file
cp .env.example .env

# Edit .env with your MongoDB Atlas connection string
MONGODB_URI="mongodb+srv://username:password@cluster0.wea2klw.mongodb.net/..."
```

### 3. Run

bash

```bash
python setup_db.py    # Create indexes
python main.py         # Start service (port 8000)
```

## API

### Submit Event

bash

```bash
POST /attempts/{attempt_id}/events
{
"question":"Q1",
"answer":"Yes", 
"timestamp":"2025-08-23T10:00:00Z"
}
```

### Get Answers

bash

```bash
GET /attempts/{attempt_id}
# Returns: latest answers and total score
```

### Get Analytics

bash

```bash
GET /analytics/attempts/{attempt_id}
# Returns: score, question count, last updated times
```

## Test

bash

```bash
python test_suite.py
```

Tests verify:

* Duplicate events ignored
* Old events don't overwrite new ones
* Concurrent events handled safely

## Key Features

* **Idempotent** : Same event can be sent multiple times safely
* **Ordered** : Latest timestamp always wins
* **Concurrent** : Thread-safe atomic operations
* **Fast** : Optimized MongoDB indexes

## Files

* `main.py` - FastAPI service
* `setup_db.py` - Database indexes
* `test_suite.py` - Test cases
* `design_notes.md` - Technical details
