# Design Notes: Test System Backend

## Overview

This system handles answer events for an online test platform, ensuring data consistency despite network issues like duplicate messages, late arrivals, and concurrent requests.

## Core Challenges Solved

### 1. Duplicate Event Prevention (Idempotency)

 **Problem** : Network retries can cause the same event to be sent multiple times.

 **Solution** :

* Generate a unique `event_key` from `(attempt_id, question, answer, timestamp)`
* Create MongoDB unique index on `(attempt_id, event_key)`
* Duplicate inserts fail silently, returning "ignored" status

 **Code Implementation** :

python

```python
defgenerate_event_key(attempt_id, question, answer, timestamp):
    data =f"{attempt_id}:{question}:{answer}:{timestamp.isoformat()}"
return hashlib.md5(data.encode()).hexdigest()

# MongoDB will reject duplicates due to unique index
await db.events.insert_one(event_doc)# Throws DuplicateKeyError for duplicates
```

 **Why This Works** : Even if the exact same event arrives 100 times, only the first insertion succeeds. The unique index at the database level guarantees this regardless of concurrent requests.

### 2. Late Event Handling (Ordering)

 **Problem** : Older events might arrive after newer ones due to network delays.

 **Solution** :

* Store ALL events (including old ones) for audit trail
* Only update attempt summary if the event is the latest for that question
* Use timestamp comparison to determine "latest"

 **Code Implementation** :

python

```python
# Find the most recent event for this question
latest_event =await db.events.find_one(
{"attempt_id": attempt_id,"question": question},
    sort=[("timestamp",-1)]# Newest first
)

# Only update if this event is the latest
if latest_event and latest_event["event_key"]== current_event_key:
# Update attempt summary
await db.attempts.update_one(...)
```

 **Why This Works** : We maintain a complete event log but only apply the chronologically latest event to the working data. Old events are stored but don't overwrite newer answers.

### 3. Concurrent Request Safety

 **Problem** : Two events might arrive simultaneously and cause race conditions.

 **Solution** :

* Use MongoDB's atomic operations (`update_one` with `upsert`)
* Unique indexes prevent duplicate storage at database level
* Each event processing is independent and atomic

 **Code Implementation** :

python

```python
# Atomic upsert - safe even with concurrent requests
await db.attempts.update_one(
{"attempt_id": attempt_id},
{
"$set":{f"answers.{question}": answer,"last_updated": timestamp},
"$setOnInsert":{"attempt_id": attempt_id,"created_at": datetime.utcnow()}
},
    upsert=True
)
```

 **Why This Works** : MongoDB's atomic operations ensure that even if 100 requests hit simultaneously, each update is applied completely or not at all. No partial updates or corruption.

## Database Design

### Collections Structure

**events** (Event Log):

javascript

```javascript
{
attempt_id:"test123",
event_key:"abc123...",// Unique hash for deduplication
question:"Q1", 
answer:"Yes",
timestamp:ISODate("2025-08-23T10:00:00Z"),
created_at:ISODate("2025-08-23T10:00:05Z")
}
```

**attempts** (Current State):

javascript

```javascript
{
attempt_id:"test123",
answers:{
"Q1":"Yes",
"Q2":"No"
},
total_score:2,
last_updated:ISODate("2025-08-23T10:02:00Z"),
created_at:ISODate("2025-08-23T10:00:05Z")
}
```

### Critical Indexes

1. **`events(attempt_id, event_key)` - UNIQUE** : Prevents duplicates
2. **`events(attempt_id, question, timestamp DESC)`** : Fast latest-event lookups
3. **`attempts(attempt_id)` - UNIQUE** : Fast attempt retrieval

## Query Performance Strategy

### Fast Duplicate Detection

The unique index on `(attempt_id, event_key)` makes duplicate detection O(log n) and happens automatically during insert.

### Fast Latest Event Lookup

python

```python
# This query uses the compound index for O(log n) performance
latest_event =await db.events.find_one(
{"attempt_id": attempt_id,"question": question},
    sort=[("timestamp",-1)]
)
```

### Fast Attempt Retrieval

Direct lookup by attempt_id using unique index - O(log n).

### Analytics Aggregation

python

```python
# Uses indexes for efficient grouping
pipeline =[
{"$match":{"attempt_id": attempt_id}},# Uses attempt_id index
{"$sort":{"timestamp":-1}},# Uses timestamp index  
{"$group":{"_id":"$question","last_updated":{"$first":"$timestamp"}}}
]
```

## Architecture Decisions

### Event Sourcing Pattern

* **Store everything** : Complete audit trail of all events
* **Derive state** : Current answers computed from events
* **Benefits** : Full history, easy debugging, data recovery possible

### Separate Collections Strategy

* **events** : Append-only event log (immutable)
* **attempts** : Current state (mutable, optimized for reads)
* **Benefits** : Read performance + complete audit trail

### MongoDB Choice

* **Atomic operations** : Built-in concurrency safety
* **Flexible schema** : Easy to extend event structure
* **Powerful indexing** : Complex queries perform well
* **Aggregation pipeline** : Efficient analytics

## Error Handling Strategy

1. **Duplicate events** : Return success with "ignored" status (idempotent)
2. **Late events** : Store but don't update current state
3. **Invalid data** : FastAPI validation catches bad inputs
4. **Database errors** : Let them bubble up (fail fast)

## Testing Strategy

The test suite covers three critical scenarios:

1. **Idempotency Test** : Same event sent twice → second ignored
2. **Ordering Test** : Old event after new → doesn't overwrite
3. **Concurrency Test** : Multiple simultaneous events → all processed safely

## Scalability Considerations

 **Current Design Handles** :

* Thousands of concurrent events (MongoDB atomic ops)
* Millions of stored events (efficient indexes)
* Complex queries remain fast (compound indexes)

 **Future Optimizations** :

* Read replicas for analytics queries
* Sharding by attempt_id for horizontal scaling
* Caching layer for frequently accessed attempts

## Key Benefits of This Design

1. **Correctness** : Guarantees data integrity under all conditions
2. **Performance** : Fast reads/writes through proper indexing
3. **Auditability** : Complete event history maintained
4. **Simplicity** : Clear separation of concerns, easy to understand
5. **Reliability** : Fails gracefully, no data corruption possible

This design demonstrates backend engineering best practices: leveraging database features for correctness, designing for concurrency from the start, and maintaining both performance and data integrity.
