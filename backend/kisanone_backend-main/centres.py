"""Government procurement centre schemas and API endpoints."""

from __future__ import annotations

from enum import Enum
from decimal import Decimal
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from bson.decimal128 import Decimal128
from pymongo import ASCENDING, GEOSPHERE, ReturnDocument
from pymongo.errors import DuplicateKeyError

from database import get_database

router = APIRouter(prefix="/centres", tags=["Centres"])

CentreId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique government procurement centre ID.",
    ),
]
Crop = Annotated[str, Field(min_length=1, max_length=50)]
OperatingDay = Annotated[str, Field(min_length=1, max_length=20)]
QuantityKg = Annotated[Decimal, Field(gt=0)]


class CentreStatus(str, Enum):
    """Operational state of a government procurement centre."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class Coordinates(BaseModel):
    """Latitude/longitude supplied when creating or updating a centre."""

    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]


class GeoJsonPoint(BaseModel):
    """MongoDB GeoJSON Point returned for a centre location."""

    type: Literal["Point"]
    coordinates: list[float] = Field(
        description="GeoJSON coordinate order: [longitude, latitude].",
        min_length=2,
        max_length=2,
    )


class CentreProfile(BaseModel):
    """Permanent operational information for a government procurement centre."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    centre_name: Annotated[str, Field(alias="centreName", min_length=1, max_length=150)]
    state: Annotated[str, Field(min_length=1, max_length=100)]
    district: Annotated[str, Field(min_length=1, max_length=100)]
    area: Annotated[str, Field(min_length=1, max_length=100)]
    address: Annotated[str, Field(min_length=1, max_length=300)]
    location: Coordinates
    supported_crops: Annotated[
        list[Crop], Field(alias="supportedCrops", min_length=1, max_length=25)
    ]
    operating_days: Annotated[
        list[OperatingDay], Field(alias="operatingDays", min_length=1, max_length=7)
    ]
    operating_hours: Annotated[
        str, Field(alias="operatingHours", min_length=1, max_length=100)
    ]
    daily_procurement_capacity_kg: QuantityKg = Field(alias="dailyProcurementCapacityKg")
    daily_qc_capacity: Annotated[int, Field(alias="dailyQcCapacity", gt=0)]
    daily_weighment_capacity: Annotated[
        int, Field(alias="dailyWeighmentCapacity", gt=0)
    ]
    status: CentreStatus


class CentreCreate(CentreProfile):
    """Request body for registering a government procurement centre."""

    centre_id: CentreId = Field(alias="centreId")

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "centreId": "CENTRE-001",
                "centreName": "Sinnar Government Procurement Centre",
                "state": "Maharashtra",
                "district": "Nashik",
                "area": "Sinnar",
                "address": "Market Yard Road, Sinnar",
                "location": {"latitude": 19.846, "longitude": 74.000},
                "supportedCrops": ["ONION", "WHEAT"],
                "operatingDays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                "operatingHours": "09:00-17:00",
                "dailyProcurementCapacityKg": 50000,
                "dailyQcCapacity": 250,
                "dailyWeighmentCapacity": 300,
                "status": "ACTIVE",
            }
        },
    )


class CentreUpdate(BaseModel):
    """Profile fields that may be changed without changing the Centre ID."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    centre_name: Annotated[Optional[str], Field(alias="centreName", min_length=1, max_length=150)] = None
    state: Annotated[Optional[str], Field(min_length=1, max_length=100)] = None
    district: Annotated[Optional[str], Field(min_length=1, max_length=100)] = None
    area: Annotated[Optional[str], Field(min_length=1, max_length=100)] = None
    address: Annotated[Optional[str], Field(min_length=1, max_length=300)] = None
    location: Optional[Coordinates] = None
    supported_crops: Annotated[
        Optional[list[Crop]], Field(alias="supportedCrops", min_length=1, max_length=25)
    ] = None
    operating_days: Annotated[
        Optional[list[OperatingDay]], Field(alias="operatingDays", min_length=1, max_length=7)
    ] = None
    operating_hours: Annotated[
        Optional[str], Field(alias="operatingHours", min_length=1, max_length=100)
    ] = None
    daily_procurement_capacity_kg: Optional[QuantityKg] = Field(
        default=None, alias="dailyProcurementCapacityKg"
    )
    daily_qc_capacity: Annotated[Optional[int], Field(alias="dailyQcCapacity", gt=0)] = None
    daily_weighment_capacity: Annotated[
        Optional[int], Field(alias="dailyWeighmentCapacity", gt=0)
    ] = None
    status: Optional[CentreStatus] = None


class CentreResponse(BaseModel):
    """Centre profile returned by the API, including its GeoJSON location."""

    model_config = ConfigDict(populate_by_name=True)

    centre_id: CentreId = Field(alias="centreId")
    centre_name: Annotated[str, Field(alias="centreName")]
    state: str
    district: str
    area: str
    address: str
    location: GeoJsonPoint
    supported_crops: list[str] = Field(alias="supportedCrops")
    operating_days: list[str] = Field(alias="operatingDays")
    operating_hours: str = Field(alias="operatingHours")
    daily_procurement_capacity_kg: Decimal = Field(alias="dailyProcurementCapacityKg")
    daily_qc_capacity: int = Field(alias="dailyQcCapacity")
    daily_weighment_capacity: int = Field(alias="dailyWeighmentCapacity")
    status: CentreStatus


def centres_collection():
    """Return the shared MongoDB centres collection."""
    return get_database()["centres"]


def ensure_centre_indexes() -> None:
    """Create indexes required by the Centre module if they do not already exist."""
    collection = centres_collection()
    collection.create_index("centreId", unique=True, name="centre_id_unique")
    collection.create_index([("district", ASCENDING)], name="district_index")
    collection.create_index([("supportedCrops", ASCENDING)], name="supported_crops_index")
    collection.create_index([("location", GEOSPHERE)], name="location_2dsphere")


def _geojson_point(location: dict) -> dict:
    """Convert validated latitude/longitude input into MongoDB GeoJSON."""
    return {
        "type": "Point",
        "coordinates": [location["longitude"], location["latitude"]],
    }


def _as_decimal(value: Decimal | Decimal128 | int | float) -> Decimal:
    """Return an exact quantity, including values stored before Decimal128."""
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return Decimal(str(value))


def _as_decimal128(value: Decimal | Decimal128 | int | float) -> Decimal128:
    if isinstance(value, Decimal128):
        return value
    return Decimal128(_as_decimal(value))


def _centre_response(document: dict) -> CentreResponse:
    """Convert a MongoDB centre document into the public response shape."""
    response_document = dict(document)
    response_document["dailyProcurementCapacityKg"] = _as_decimal(
        document["dailyProcurementCapacityKg"]
    )
    return CentreResponse.model_validate(response_document)


def _validate_centre_update(existing: dict, updates: dict) -> None:
    """Reject changes that invalidate this centre's slots or live requests."""
    database = get_database()
    if "dailyProcurementCapacityKg" in updates:
        proposed_capacity = _as_decimal(updates["dailyProcurementCapacityKg"])
        daily_slots = database["slots"].aggregate(
            [
                {"$match": {"centreId": existing["_id"]}},
                {"$group": {"_id": "$date", "capacityKg": {"$sum": "$capacityKg"}}},
            ]
        )
        for daily_slot in daily_slots:
            if _as_decimal(daily_slot["capacityKg"]) > proposed_capacity:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="dailyProcurementCapacityKg is below existing slot capacity for a date.",
                )

    if "supportedCrops" in updates:
        removed_crops = set(existing["supportedCrops"]) - set(updates["supportedCrops"])
        if removed_crops:
            slot_exists = database["slots"].find_one(
                {
                    "centreId": existing["_id"],
                    "cropCode": {"$in": list(removed_crops)},
                    "status": {"$ne": "CLOSED"},
                }
            )
            request_exists = database["procurementRequests"].find_one(
                {
                    "assignedCentreId": existing["_id"],
                    "cropCode": {"$in": list(removed_crops)},
                    "requestStatus": {"$ne": "CANCELLED"},
                }
            )
            if slot_exists or request_exists:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot remove a supported crop referenced by active slots or procurement requests.",
                )


@router.post("", response_model=CentreResponse, status_code=status.HTTP_201_CREATED)
def create_centre(centre: CentreCreate) -> CentreResponse:
    """Register a government procurement centre."""
    document = centre.model_dump(by_alias=True)
    document["_id"] = document["centreId"]
    document["dailyProcurementCapacityKg"] = _as_decimal128(
        centre.daily_procurement_capacity_kg
    )
    document["location"] = _geojson_point(document["location"])

    try:
        centres_collection().insert_one(document)
    except DuplicateKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A centre with this Centre ID already exists.",
        ) from error

    return _centre_response(document)


@router.get("", response_model=list[CentreResponse])
def list_centres(skip: int = 0, limit: int = 100) -> list[CentreResponse]:
    """List government procurement centres for development and testing."""
    if skip < 0:
        raise HTTPException(status_code=400, detail="skip must be zero or greater.")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100.")

    documents = centres_collection().find().skip(skip).limit(limit)
    return [_centre_response(document) for document in documents]


@router.get("/{centre_id}", response_model=CentreResponse)
def get_centre(centre_id: CentreId) -> CentreResponse:
    """Get one government procurement centre by its Centre ID."""
    document = centres_collection().find_one({"_id": centre_id})
    if document is None:
        raise HTTPException(status_code=404, detail="Centre not found.")

    return _centre_response(document)


@router.patch("/{centre_id}", response_model=CentreResponse)
def update_centre(centre_id: CentreId, centre_update: CentreUpdate) -> CentreResponse:
    """Update centre profile fields without changing the Centre ID."""
    updates = centre_update.model_dump(by_alias=True, exclude_unset=True, exclude_none=True)
    if "location" in updates:
        updates["location"] = _geojson_point(updates["location"])
    if not updates:
        raise HTTPException(status_code=400, detail="Provide at least one centre field to update.")

    existing = centres_collection().find_one({"_id": centre_id})
    if existing is None:
        raise HTTPException(status_code=404, detail="Centre not found.")
    if "dailyProcurementCapacityKg" in updates:
        updates["dailyProcurementCapacityKg"] = _as_decimal128(
            centre_update.daily_procurement_capacity_kg
        )
    _validate_centre_update(existing, updates)

    document = centres_collection().find_one_and_update(
        {"_id": centre_id},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    return _centre_response(document)
