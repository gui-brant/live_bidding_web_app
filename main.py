from datetime import datetime, timezone
from typing import List, Optional
import os

from bson import ObjectId
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient, ReturnDocument


def load_env_file(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_origins(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


def parse_object_id(value: str, field_name: str = "id") -> ObjectId:
    try:
        return ObjectId(value)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}.") from exc


def stringify_id(value: object) -> str:
    return str(value) if isinstance(value, ObjectId) else str(value)


project_root = os.path.dirname(os.path.abspath(__file__))
load_env_file(os.path.join(project_root, ".env"))
load_env_file(os.path.join(project_root, "backend", "server", ".env"))

MONGO_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGODB_DB_NAME", "auction_system")
CORS_ALLOW_ORIGINS = parse_origins(os.getenv("CORS_ALLOW_ORIGINS"))

mongo_client = MongoClient(MONGO_URI)
db = mongo_client[MONGO_DB]
auctions_collection = db["auctions"]
items_collection = db["auction_items"]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ItemCreate(BaseModel):
    name: str
    category: str
    description: Optional[str] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None


class AuctionCreate(BaseModel):
    title: str
    category: str
    startAt: str
    endAt: str
    status: str
    description: Optional[str] = None
    itemIds: List[str] = []


class AuctionUpdate(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    startAt: Optional[str] = None
    endAt: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    itemIds: Optional[List[str]] = None


class AuctionStatusUpdate(BaseModel):
    status: str


def serialize_item(doc: dict) -> dict:
    return {
        "id": stringify_id(doc.get("_id")),
        "name": doc.get("name") or doc.get("title") or "Untitled Item",
        "category": doc.get("category") or "General",
        "description": doc.get("description"),
    }


def serialize_public_item(doc: dict) -> dict:
    return {
        "id": stringify_id(doc.get("_id")),
        "title": doc.get("name") or doc.get("title") or "Untitled Item",
        "category": doc.get("category") or "General",
        "status": doc.get("status") or "UPCOMING",
        "start_at": doc.get("start_at") or doc.get("startAt") or doc.get("start_time"),
        "end_at": doc.get("end_at") or doc.get("endAt") or doc.get("end_time"),
        "current_highest_bid": doc.get("current_bid")
        or doc.get("currentHighestBid")
        or 0,
        "highest_bidder_id": doc.get("highest_bidder_id"),
        "description": doc.get("description"),
    }


def serialize_auction(doc: dict) -> dict:
    raw_item_ids = doc.get("itemIds") or []
    item_ids = [stringify_id(item_id) for item_id in raw_item_ids]
    return {
        "id": stringify_id(doc.get("_id")),
        "title": doc.get("title") or "",
        "category": doc.get("category") or "",
        "status": doc.get("status") or "UPCOMING",
        "startAt": doc.get("startAt") or "",
        "endAt": doc.get("endAt") or "",
        "currentHighestBid": doc.get("currentHighestBid") or 0,
        "description": doc.get("description"),
        "updatedAt": doc.get("updatedAt"),
        "itemIds": item_ids,
    }


def normalize_item_ids(raw_ids: Optional[List[str]]) -> List[ObjectId]:
    if not raw_ids:
        return []
    return [parse_object_id(item_id, "item_id") for item_id in raw_ids]


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}


@app.get("/items")
def list_items():
    items = list(items_collection.find().sort("updatedAt", -1))
    return [serialize_item(item) for item in items]


@app.post("/items")
def create_item(payload: ItemCreate):
    doc = {
        "name": payload.name,
        "category": payload.category,
        "description": payload.description,
        "status": "UPCOMING",
        "current_bid": 0,
        "updatedAt": now_iso(),
    }
    result = items_collection.insert_one(doc)
    created = items_collection.find_one({"_id": result.inserted_id})
    return serialize_item(created)


@app.get("/items/{item_id}")
def get_item(item_id: str):
    doc = items_collection.find_one({"_id": parse_object_id(item_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Item not found.")
    return serialize_item(doc)


@app.patch("/items/{item_id}")
def update_item(item_id: str, payload: ItemUpdate):
    update_data = {key: value for key, value in payload.dict(exclude_unset=True).items() if value is not None}
    if not update_data:
        doc = items_collection.find_one({"_id": parse_object_id(item_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Item not found.")
        return serialize_item(doc)
    update_data["updatedAt"] = now_iso()
    doc = items_collection.find_one_and_update(
        {"_id": parse_object_id(item_id)},
        {"$set": update_data},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Item not found.")
    return serialize_item(doc)


@app.get("/auctions/items")
def list_public_items():
    items = list(items_collection.find().sort("updatedAt", -1))
    return [serialize_public_item(item) for item in items]


@app.get("/auctions/items/{item_id}")
def get_public_item(item_id: str):
    doc = items_collection.find_one({"_id": parse_object_id(item_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Item not found.")
    return serialize_public_item(doc)


@app.get("/admin/auctions")
def list_admin_auctions():
    auctions = list(auctions_collection.find().sort("updatedAt", -1))
    return [serialize_auction(auction) for auction in auctions]


@app.post("/admin/auctions")
def create_admin_auction(payload: AuctionCreate):
    item_ids = normalize_item_ids(payload.itemIds)
    doc = {
        "title": payload.title,
        "category": payload.category,
        "startAt": payload.startAt,
        "endAt": payload.endAt,
        "status": payload.status,
        "description": payload.description,
        "currentHighestBid": 0,
        "itemIds": item_ids,
        "updatedAt": now_iso(),
    }
    result = auctions_collection.insert_one(doc)
    created = auctions_collection.find_one({"_id": result.inserted_id})
    return serialize_auction(created)


@app.patch("/admin/auctions/{auction_id}")
def update_admin_auction(auction_id: str, payload: AuctionUpdate):
    update_data = {
        "title": payload.title,
        "category": payload.category,
        "startAt": payload.startAt,
        "endAt": payload.endAt,
        "status": payload.status,
        "description": payload.description,
    }
    update_data = {key: value for key, value in update_data.items() if value is not None}
    if payload.itemIds is not None:
        update_data["itemIds"] = normalize_item_ids(payload.itemIds)
    if not update_data:
        doc = auctions_collection.find_one({"_id": parse_object_id(auction_id)})
        if not doc:
            raise HTTPException(status_code=404, detail="Auction not found.")
        return serialize_auction(doc)
    update_data["updatedAt"] = now_iso()
    doc = auctions_collection.find_one_and_update(
        {"_id": parse_object_id(auction_id)},
        {"$set": update_data},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Auction not found.")
    return serialize_auction(doc)


@app.patch("/admin/auctions/{auction_id}/status")
def update_admin_auction_status(auction_id: str, payload: AuctionStatusUpdate):
    doc = auctions_collection.find_one_and_update(
        {"_id": parse_object_id(auction_id)},
        {"$set": {"status": payload.status, "updatedAt": now_iso()}},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Auction not found.")
    return serialize_auction(doc)
