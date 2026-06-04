from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os
from dotenv import load_dotenv

# 1. load environment variables
load_dotenv()
mongo_uri = os.getenv('MONGODB_URI')

# 2. initialize MongoDB client
client = MongoClient(mongo_uri, server_api=ServerApi('1'))

# 3. access database and collection
db = client['auction_system']      # database name
items_col = db['auction_items']    # item list collection

def add_auction_item(name, starting_price):
    """insert a new auction item"""
    item = {
        "name": name,
        "current_bid": starting_price,
        "status": 1
    }
    result = items_col.insert_one(item)
    print(f"item created，ID: {result.inserted_id}")

def get_all_items():
    """search and print all auction items"""
    items = items_col.find()
    for item in items:
        print(item)

def edit_auction_item(item_id, new_name=None, new_price=None):
    """update an existing auction item"""
    update_fields = {}
    if new_name:
        update_fields["name"] = new_name
    if new_price is not None:
        update_fields["current_bid"] = new_price
    
    if update_fields:
        result = items_col.update_one({"_id": item_id}, {"$set": update_fields})
        print(f"item updated，matched: {result.matched_count}, modified: {result.modified_count}")
    else:
        print("no fields to update")

def clear_items():
    """delete all items in the collection"""
    result = items_col.delete_many({})
    print(f"deleted {result.deleted_count} items")
# test connection and run example functions
try:
    client.admin.command('ping')
    print("successfully connected to MongoDB!")
    
    # here we can try to insert or fetch items
    #add_auction_item("Antique Vase", 200)
    #get_all_items()
    #edit_auction_item(item_id=items_col.find_one({"name": "Antique Vase"})["_id"], new_price=250)
    #or edit_auction_item(item_id='', new_name="Rare Antique Vase")
    clear_items()
    add_auction_item("Iphone", 100)
    get_all_items()
    edit_auction_item(item_id=items_col.find_one({"name": "Iphone"})["_id"],new_name='Lenovo', new_price=150)
    get_all_items()
except Exception as e:
    print(f"connection error:{e}")