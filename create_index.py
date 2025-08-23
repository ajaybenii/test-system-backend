import os
import asyncio
import motor.motor_asyncio
from pymongo.errors import OperationFailure
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.environ["MONGODB_URI"]
DATABASE = "test_system"

async def create_indexes():
    """Create all required MongoDB indexes"""
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
    db = client[DATABASE]
    
    print("Creating MongoDB indexes...")
    
    try:
        # 1. Unique index for event deduplication
        # This prevents duplicate events from being stored
        await db.events.create_index([
            ("attempt_id", 1),
            ("event_key", 1)
        ], unique=True, name="unique_event_key")
        print("✓ Created unique index on events (attempt_id, event_key)")
        
        # 2. Index for attempt lookups
        await db.attempts.create_index(
            "attempt_id", 
            unique=True, 
            name="unique_attempt_id"
        )
        print("✓ Created unique index on attempts (attempt_id)")
        
        # 3. Compound index for finding latest events per question
        # This makes our "latest event" queries fast
        await db.events.create_index([
            ("attempt_id", 1),
            ("question", 1),
            ("timestamp", -1)  # Descending for latest first
        ], name="attempt_question_timestamp")
        print("✓ Created compound index on events (attempt_id, question, timestamp)")
        
        # 4. Index for analytics aggregation
        await db.events.create_index([
            ("attempt_id", 1),
            ("timestamp", -1)
        ], name="attempt_timestamp")
        print("✓ Created index on events (attempt_id, timestamp)")
        
        print("\n✅ All indexes created successfully!")
        
        # Show created indexes
        print("\nIndexes on 'events' collection:")
        async for index in db.events.list_indexes():
            print(f"  - {index['name']}: {index['key']}")
            
        print("\nIndexes on 'attempts' collection:")
        async for index in db.attempts.list_indexes():
            print(f"  - {index['name']}: {index['key']}")
            
    except OperationFailure as e:
        print(f"❌ Error creating indexes: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(create_indexes())