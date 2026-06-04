from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from typing import Literal, Optional, Any
from bson import ObjectId
from datetime import datetime

class UserCreate(BaseModel):
    name: str
    email: EmailStr
    role: Literal['rep', 'admin']
    balance_amount: int = 0
    balance_committed: bool = False
    has_bid: bool = False
    gift_card_winner: bool = False

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None    
    role: Optional[Literal['rep', 'admin']] = None
    balance_amount: Optional[int] = None
    balance_committed: Optional[bool] = None
    has_bid: Optional[bool] = None
    gift_card_winner: Optional[bool] = None


class SetUserKogbucksIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    balance_amount: int = Field(..., ge=0)

class UserSettingsUpdate(BaseModel):
    enable_email: Optional[bool] = None
    enable_in_app: Optional[bool] = None
    notify_outbid: Optional[bool] = None
    notify_auction_timeframe: Optional[bool] = None
    notify_auction_win: Optional[bool] = None

class UserOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True) #allows for model flexibility by accepting both "id" (as in the API response) and "_id" (as in the Mongo document) as the user identifier field.

    id: str = Field(..., alias="_id") #The alias="_id" means that when creating a UserOut instance, you can provide the user ID using either the "id" field or the "_id" field. This is useful for handling data from MongoDB, which uses "_id" as the default identifier field, while your API might want to use "id" for consistency. The Field(...) indicates that this field is required.
    name: str
    email: EmailStr
    role: Literal['rep', 'admin']
    balance_amount: int
    balance_committed: bool
    has_bid: bool
    gift_card_winner: bool = False

    created_at: Optional[datetime] = None #Copilot suggested. Do we really want this?
    updated_at: Optional[datetime] = None #Copilot suggested. Do we really want this? If so, how would them use it later? 
    @field_validator("id", mode="before") #This validator runs before the standard validation process and is used to ensure that the "id" field is always treated as a string, even if it comes in as an ObjectId from MongoDB. This helps maintain consistency in the API response format.
    @classmethod #This decorator indicates that the method is a class method, which means it receives the class (cls) as the first argument instead of an instance of the class. This is appropriate for a field validator since it operates on the class level rather than on individual instances.
    def _id_to_str(cls, v: Any) -> Any:
        # v is whatever came in for "_id"
        if isinstance(v, ObjectId):
            return str(v)
        return v

#Are these all the models that we need? Do we need a UserOut model for the response shape?
