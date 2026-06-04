import asyncio
import os
from pymongo import AsyncMongoClient
from pymongo.server_api import ServerApi

MONGO_URI: str = os.getenv("MONGODB_URI", "")
DB_NAME: str = "Setup"

if not MONGO_URI:
    raise ValueError("MONGODB_URI environment variable is not set.")


#Client Setup
client = AsyncMongoClient(
    MONGO_URI,
    server_api=ServerApi("1"),
)

db = client[DB_NAME]
users = db["users"]
auctions = db["auctions"]


#Transaction test - demonstrates how to use transactions with the MongoDB client. 
#This is not a unit test, just a standalone script to verify transaction functionality. 
#You can run this with -------->`python db.py`<------- and check your database to see the inserted documents if the transaction commits successfully.

async def main():
    print("--Starting transaction test--")

    async with await client.start_session() as session:
        async with session.start_transaction():

            print("Inserting user...")
            await users.insert_one(
                {"name": "GuiIsMyHero"},
                session=session,
            )

            print("Inserting auction...")
            await auctions.insert_one(
                {"item": "1WeekExtention", "owner": "TransactionTestUser"},
                session=session,
            )

    print("--Transaction committed--")


if __name__ == "__main__":
    asyncio.run(main())