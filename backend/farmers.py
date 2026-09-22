"""Farmer profile schemas and API endpoints."""

from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from database import get_database

router = APIRouter(prefix="/farmers", tags=["Farmers"])

FarmerId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique Farmer ID.",
    ),
]
PhoneNumber = Annotated[
    str,
    Field(
        min_length=7,
        max_length=20,
        pattern=r"^[0-9+() -]+$",
        description="Farmer contact phone number.",
    ),
]


class FarmerProfile(BaseModel):
    """Permanent farmer profile fields stored in the farmers collection."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=100)]
    phone: PhoneNumber
    address: Annotated[str, Field(min_length=1, max_length=300)]
    district: Annotated[str, Field(min_length=1, max_length=100)]
    area: Annotated[str, Field(min_length=1, max_length=100)]
    preferred_language: Annotated[
        str, Field(alias="preferredLanguage", min_length=1, max_length=50)
    ]
    ekyc_verified: bool = Field(alias="ekycVerified")


class FarmerCreate(FarmerProfile):
    """Request body for registering a farmer."""

    farmer_id: FarmerId = Field(alias="farmerId")

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "farmerId": "FARMER-001",
                "name": "Asha Patil",
                "phone": "+919876543210",
                "address": "Village Road, Ward 2",
                "district": "Nashik",
                "area": "Sinnar",
                "preferredLanguage": "Marathi",
                "ekycVerified": True,
            }
        },
    )


class FarmerUpdate(BaseModel):
    """Fields that can be changed on an existing farmer profile."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: Annotated[Optional[str], Field(min_length=1, max_length=100)] = None
    phone: Optional[PhoneNumber] = None
    address: Annotated[Optional[str], Field(min_length=1, max_length=300)] = None
    district: Annotated[Optional[str], Field(min_length=1, max_length=100)] = None
    area: Annotated[Optional[str], Field(min_length=1, max_length=100)] = None
    preferred_language: Annotated[
        Optional[str], Field(alias="preferredLanguage", min_length=1, max_length=50)
    ] = None
    ekyc_verified: Optional[bool] = Field(default=None, alias="ekycVerified")


class FarmerResponse(FarmerProfile):
    """Farmer profile returned by the API."""

    farmer_id: FarmerId = Field(alias="farmerId")


def farmers_collection():
    """Return the shared MongoDB farmers collection."""
    return get_database()["farmers"]


def ensure_farmer_indexes() -> None:
    """Create indexes required by the Farmer module if they do not already exist."""
    collection = farmers_collection()
    collection.create_index("farmerId", unique=True, name="farmer_id_unique")
    collection.create_index([("phone", ASCENDING)], name="phone_index")


def _farmer_response(document: dict) -> FarmerResponse:
    """Convert a MongoDB farmer document into the public response shape."""
    return FarmerResponse.model_validate(document)


@router.post("", response_model=FarmerResponse, status_code=status.HTTP_201_CREATED)
def create_farmer(farmer: FarmerCreate) -> FarmerResponse:
    """Register a farmer with an application-owned Farmer ID."""
    document = farmer.model_dump(by_alias=True)
    document["_id"] = document["farmerId"]

    try:
        farmers_collection().insert_one(document)
    except DuplicateKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A farmer with this Farmer ID already exists.",
        ) from error

    return _farmer_response(document)


@router.get("", response_model=list[FarmerResponse])
def list_farmers(skip: int = 0, limit: int = 100) -> list[FarmerResponse]:
    """List farmer profiles for development and testing."""
    if skip < 0:
        raise HTTPException(status_code=400, detail="skip must be zero or greater.")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100.")

    documents = farmers_collection().find().skip(skip).limit(limit)
    return [_farmer_response(document) for document in documents]


@router.get("/{farmer_id}", response_model=FarmerResponse)
def get_farmer(farmer_id: FarmerId) -> FarmerResponse:
    """Get one farmer profile by its Farmer ID."""
    document = farmers_collection().find_one({"_id": farmer_id})
    if document is None:
        raise HTTPException(status_code=404, detail="Farmer not found.")

    return _farmer_response(document)


@router.patch("/{farmer_id}", response_model=FarmerResponse)
def update_farmer(farmer_id: FarmerId, farmer: FarmerUpdate) -> FarmerResponse:
    """Update permanent profile fields without changing the Farmer ID."""
    updates = farmer.model_dump(by_alias=True, exclude_unset=True, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Provide at least one profile field to update.")

    document = farmers_collection().find_one_and_update(
        {"_id": farmer_id},
        {"$set": updates},
        return_document=True,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Farmer not found.")

    return _farmer_response(document)
