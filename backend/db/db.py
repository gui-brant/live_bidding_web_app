from pymongo import AsyncMongoClient
from pymongo.server_api import ServerApi
from pymongo.client_session import AsyncClientSession
from typing import Callable, Awaitable, Any
import os

# Config
MONGO_URI: str = os.getenv("MONGODB_URI", "")
DB_NAME: str = "Setup"

# Singleton Client
_client: AsyncMongoClient | None = None


def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        _client = AsyncMongoClient(
            MONGO_URI,
            server_api=ServerApi("1"),
        )
    return _client


def get_database():
    return get_client()[DB_NAME]


def get_users_collection():
    return get_database()["users"]


def get_auctions_collection():
    return get_database()["auctions"]


# Transaction fuction that accepts an async operation and runs it inside a transaction. The operation must accept a `session` argument.

async def run_transaction(
    operation: Callable[[AsyncClientSession], Awaitable[Any]]
) -> Any:
    
    #Run an async operation inside a MongoDB transaction.
    #The operation must accept a `session` argument.
    

    client = get_client()

    async with await client.start_session() as session:
        async with session.start_transaction():
            result = await operation(session)
            return result