"""Procurement centre slot schemas, capacity validation, and API endpoints."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from bson.decimal128 import Decimal128
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from database import get_database, mongo_client

router = APIRouter(tags=["Slots"])

SlotId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique slot ID.",
    ),
]
CentreId = Annotated[
    str,
    Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$"),
]
CropCode = Annotated[
    str,
    Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$"),
]
QuantityKg = Annotated[Decimal, Field(gt=0)]


class SlotStatus(str, Enum):
    """Availability state of a procurement time window."""

    AVAILABLE = "AVAILABLE"
    FULL = "FULL"
    CLOSED = "CLOSED"


class SlotSchedule(BaseModel):
    """Centre, crop, date, time window, and maximum capacity for a slot."""

    model_config = ConfigDict(populate_by_name=True)

    centre_id: CentreId = Field(alias="centreId")
    crop_code: CropCode = Field(alias="cropCode")
    slot_date: date = Field(alias="date")
    start_time: time = Field(alias="startTime")
    end_time: time = Field(alias="endTime")
    capacity_kg: QuantityKg = Field(alias="capacityKg")
    max_farmers: Annotated[int, Field(alias="maxFarmers", gt=0)]

    @model_validator(mode="after")
    def end_time_must_be_later(self):
        """Reject time windows that do not move forward within the same day."""
        if self.end_time <= self.start_time:
            raise ValueError("endTime must be later than startTime.")
        return self


class SlotCreate(SlotSchedule):
    """Request body for creating an empty procurement slot."""

    slot_id: SlotId = Field(alias="slotId")

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "slotId": "SLOT-001",
                "centreId": "CENTRE-001",
                "cropCode": "WHEAT",
                "date": "2026-10-01",
                "startTime": "10:00:00",
                "endTime": "10:30:00",
                "capacityKg": 10000,
                "maxFarmers": 25,
            }
        },
    )


class SlotUpdate(BaseModel):
    """Slot fields that may change before future bookings are implemented."""

    model_config = ConfigDict(populate_by_name=True)

    centre_id: Optional[CentreId] = Field(default=None, alias="centreId")
    crop_code: Optional[CropCode] = Field(default=None, alias="cropCode")
    slot_date: Optional[date] = Field(default=None, alias="date")
    start_time: Optional[time] = Field(default=None, alias="startTime")
    end_time: Optional[time] = Field(default=None, alias="endTime")
    capacity_kg: Optional[QuantityKg] = Field(default=None, alias="capacityKg")
    max_farmers: Optional[int] = Field(default=None, alias="maxFarmers", gt=0)
    status: Optional[SlotStatus] = None


class SlotResponse(SlotSchedule):
    """Slot record with allocation and calculated remaining capacity."""

    slot_id: SlotId = Field(alias="slotId")
    allocated_kg: Annotated[Decimal, Field(alias="allocatedKg", ge=0)]
    max_farmers: Annotated[int, Field(alias="maxFarmers", gt=0)]
    allocated_farmers: Annotated[int, Field(alias="allocatedFarmers", ge=0)]
    remaining_capacity_kg: Annotated[Decimal, Field(alias="remainingCapacityKg", ge=0)]
    remaining_farmer_capacity: Annotated[
        int, Field(alias="remainingFarmerCapacity", ge=0)
    ]
    status: SlotStatus
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


def slots_collection():
    """Return the shared MongoDB slots collection."""
    return get_database()["slots"]


def ensure_slot_indexes() -> None:
    """Create indexes required by the Slot module if they do not already exist."""
    collection = slots_collection()
    collection.create_index("slotId", unique=True, name="slot_id_unique")
    collection.create_index(
        [
            ("centreId", ASCENDING),
            ("cropCode", ASCENDING),
            ("date", ASCENDING),
            ("startTime", ASCENDING),
            ("endTime", ASCENDING),
        ],
        unique=True,
        name="centre_crop_date_time_unique",
    )
    collection.create_index([("centreId", ASCENDING)], name="centre_id_index")
    collection.create_index([("cropCode", ASCENDING)], name="crop_code_index")
    collection.create_index([("date", ASCENDING)], name="date_index")
    collection.create_index([("status", ASCENDING)], name="status_index")
    collection.create_index(
        [
            ("centreId", ASCENDING),
            ("cropCode", ASCENDING),
            ("date", ASCENDING),
            ("status", ASCENDING),
        ],
        name="centre_crop_date_status_index",
    )


def _derived_status(slot: dict) -> SlotStatus:
    """Derive slot availability from current allocations.

    Status derivation rules:
    - CLOSED slots are never reopened automatically (persisted status wins)
    - FULL when allocatedKg >= capacityKg OR allocatedFarmers >= maxFarmers
    - AVAILABLE otherwise

    The derived status is computed on each API response via _slot_response.
    Increasing capacityKg on a FULL slot will cause the next response to show AVAILABLE
    (provided allocatedKg < new capacityKg and allocatedFarmers < maxFarmers).
    CLOSED status is never mutated by this function; only explicit PATCH to CLOSED
    or reopening via explicit status change (not implemented) affects it.
    """
    if slot["status"] == SlotStatus.CLOSED.value:
        return SlotStatus.CLOSED
    if (
        _as_decimal(slot["allocatedKg"]) >= _as_decimal(slot["capacityKg"])
        or slot["allocatedFarmers"] >= slot["maxFarmers"]
    ):
        return SlotStatus.FULL
    return SlotStatus.AVAILABLE


def _slot_response(document: dict) -> SlotResponse:
    """Add calculated capacities to a document without persisting those fields.

    The returned status is always derived from current allocations via _derived_status.
    This ensures capacity increases are immediately reflected in the API response.
    """
    response_document = dict(document)
    response_document["capacityKg"] = _as_decimal(document["capacityKg"])
    response_document["allocatedKg"] = _as_decimal(document["allocatedKg"])
    response_document["remainingCapacityKg"] = max(
        Decimal("0"), response_document["capacityKg"] - response_document["allocatedKg"]
    )
    response_document["remainingFarmerCapacity"] = max(
        0, document["maxFarmers"] - document["allocatedFarmers"]
    )
    response_document["status"] = _derived_status(document).value
    return SlotResponse.model_validate(response_document)


def _as_decimal(value: Decimal | Decimal128 | int | float) -> Decimal:
    """Return exact quantities, including legacy integer MongoDB values."""
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return Decimal(str(value))


def _as_decimal128(value: Decimal | Decimal128 | int | float) -> Decimal128:
    """Encode a quantity exactly for BSON storage."""
    if isinstance(value, Decimal128):
        return value
    return Decimal128(_as_decimal(value))


def _validate_centre_and_crop(centre_id: str, crop_code: str, session=None) -> dict:
    """Ensure the active centre supports the crop and its configuration is active."""
    database = get_database()
    centre = database["centres"].find_one({"_id": centre_id}, session=session)
    if centre is None:
        raise HTTPException(status_code=404, detail="Centre not found.")
    if centre.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Centre is not ACTIVE.")
    if crop_code not in centre.get("supportedCrops", []):
        raise HTTPException(
            status_code=400,
            detail="Centre does not support this cropCode.",
        )

    crop = database["cropConfigurations"].find_one({"_id": crop_code}, session=session)
    if crop is None:
        raise HTTPException(status_code=404, detail="Crop configuration not found.")
    if crop.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Crop configuration is not ACTIVE.")
    return centre


def _validate_daily_centre_capacity(
    centre: dict,
    slot_date: str,
    capacity_kg: Decimal | Decimal128 | int,
    excluding_slot_id: Optional[str] = None,
    session=None,
) -> None:
    """Ensure all slot capacities for a centre/date fit its daily capacity."""
    match = {"centreId": centre["_id"], "date": slot_date}
    if excluding_slot_id is not None:
        match["_id"] = {"$ne": excluding_slot_id}

    result = list(
        slots_collection().aggregate(
            [
                {"$match": match},
                {"$group": {"_id": None, "totalCapacityKg": {"$sum": "$capacityKg"}}},
            ],
            session=session,
        )
    )
    existing_capacity_kg = _as_decimal(result[0]["totalCapacityKg"]) if result else Decimal("0")
    if existing_capacity_kg + _as_decimal(capacity_kg) > _as_decimal(centre["dailyProcurementCapacityKg"]):
        raise HTTPException(
            status_code=400,
            detail="Total slot capacity exceeds the centre's daily procurement capacity.",
        )


def _validate_slot_values(slot: dict) -> None:
    """Validate allocations and the completed candidate time window."""
    if _as_decimal(slot["allocatedKg"]) < 0 or _as_decimal(slot["allocatedKg"]) > _as_decimal(slot["capacityKg"]):
        raise HTTPException(
            status_code=400,
            detail="allocatedKg must be between zero and capacityKg.",
        )
    if slot["allocatedFarmers"] < 0 or slot["allocatedFarmers"] > slot["maxFarmers"]:
        raise HTTPException(
            status_code=400,
            detail="allocatedFarmers must be between zero and maxFarmers.",
        )
    if slot["endTime"] <= slot["startTime"]:
        raise HTTPException(status_code=400, detail="endTime must be later than startTime.")


def slot_can_accept(slot: dict, requested_quantity_kg: Decimal | Decimal128 | int) -> bool:
    """Return whether a slot has quantity and one-farmer capacity for a request."""
    requested_quantity_kg = _as_decimal(requested_quantity_kg)
    if requested_quantity_kg <= 0:
        return False
    return (
        _derived_status(slot) != SlotStatus.CLOSED
        and _as_decimal(slot["allocatedKg"]) + requested_quantity_kg <= _as_decimal(slot["capacityKg"])
        and slot["allocatedFarmers"] + 1 <= slot["maxFarmers"]
    )


def reserve_slot_capacity(
    slot_id: str,
    requested_quantity_kg: Decimal | Decimal128 | int,
    session=None,
) -> Optional[dict]:
    """Atomically reserve one farmer and quantity for a future booking service.

    This helper intentionally creates no procurement request or booking record.
    It returns the updated slot, or ``None`` when the slot cannot accept the request.
    """
    requested_quantity_kg = _as_decimal(requested_quantity_kg)
    if requested_quantity_kg <= 0:
        return None

    now = datetime.now(timezone.utc)
    return slots_collection().find_one_and_update(
        {
            "_id": slot_id,
            "status": {"$ne": SlotStatus.CLOSED.value},
            "$expr": {
                "$and": [
                    {
                        "$lte": [
                            {"$add": ["$allocatedKg", _as_decimal128(requested_quantity_kg)]},
                            "$capacityKg",
                        ]
                    },
                    {
                        "$lte": [
                            {"$add": ["$allocatedFarmers", 1]},
                            "$maxFarmers",
                        ]
                    },
                ]
            },
        },
        [
            {
                "$set": {
                    "allocatedKg": {"$add": ["$allocatedKg", _as_decimal128(requested_quantity_kg)]},
                    "allocatedFarmers": {"$add": ["$allocatedFarmers", 1]},
                    "updatedAt": now,
                }
            },
            {
                "$set": {
                    "status": {
                        "$cond": [
                            {
                                "$or": [
                                    {"$gte": ["$allocatedKg", "$capacityKg"]},
                                    {"$gte": ["$allocatedFarmers", "$maxFarmers"]},
                                ]
                            },
                            SlotStatus.FULL.value,
                            SlotStatus.AVAILABLE.value,
                        ]
                    }
                }
            },
        ],
        return_document=ReturnDocument.AFTER,
        session=session,
    )


def release_slot_capacity(
    slot_id: str,
    released_quantity_kg: Decimal | Decimal128 | int,
    session=None,
) -> Optional[dict]:
    """Atomically release one farmer and quantity for a cancelled future booking."""
    released_quantity_kg = _as_decimal(released_quantity_kg)
    if released_quantity_kg <= 0:
        return None

    now = datetime.now(timezone.utc)
    return slots_collection().find_one_and_update(
        {
            "_id": slot_id,
            "$expr": {"$gte": ["$allocatedKg", _as_decimal128(released_quantity_kg)]},
            "allocatedFarmers": {"$gte": 1},
        },
        [
            {
                "$set": {
                    "allocatedKg": {"$subtract": ["$allocatedKg", _as_decimal128(released_quantity_kg)]},
                    "allocatedFarmers": {"$subtract": ["$allocatedFarmers", 1]},
                    "updatedAt": now,
                }
            },
            {
                "$set": {
                    "status": {
                        "$cond": [
                            {"$eq": ["$status", SlotStatus.CLOSED.value]},
                            SlotStatus.CLOSED.value,
                            {
                                "$cond": [
                                    {
                                        "$or": [
                                            {"$gte": ["$allocatedKg", "$capacityKg"]},
                                            {"$gte": ["$allocatedFarmers", "$maxFarmers"]},
                                        ]
                                    },
                                    SlotStatus.FULL.value,
                                    SlotStatus.AVAILABLE.value,
                                ]
                            },
                        ]
                    }
                }
            },
        ],
        return_document=ReturnDocument.AFTER,
        session=session,
    )


@router.post("/slots", response_model=SlotResponse, status_code=status.HTTP_201_CREATED)
def create_slot(slot: SlotCreate) -> SlotResponse:
    """Create an empty capacity-managed slot for an active centre and crop."""
    document = slot.model_dump(by_alias=True, mode="json")
    document["_id"] = document["slotId"]
    document["capacityKg"] = _as_decimal128(slot.capacity_kg)
    document["allocatedKg"] = _as_decimal128(Decimal("0"))
    document["allocatedFarmers"] = 0
    document["status"] = SlotStatus.AVAILABLE.value
    now = datetime.now(timezone.utc)
    document["createdAt"] = now
    document["updatedAt"] = now

    try:
        def create_slot_transaction(session) -> None:
            # This write deliberately makes concurrent capacity checks for a
            # centre conflict; with_transaction retries the losing operation.
            locked_centre = get_database()["centres"].find_one_and_update(
                {"_id": document["centreId"], "status": "ACTIVE"},
                {"$set": {"status": "ACTIVE"}},
                session=session,
            )
            # Always validate centre supports the crop and crop config is active,
            # even when the centre was successfully locked above.
            _validate_centre_and_crop(document["centreId"], document["cropCode"], session)
            centre = locked_centre or _validate_centre_and_crop(
                document["centreId"], document["cropCode"], session
            )
            _validate_daily_centre_capacity(
                centre, document["date"], document["capacityKg"], session=session
            )
            slots_collection().insert_one(document, session=session)

        with mongo_client.start_session() as session:
            session.with_transaction(create_slot_transaction)
    except DuplicateKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A slot with this ID or time window already exists.",
        ) from error
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not create the slot safely. Please retry.",
        ) from error

    return _slot_response(document)


@router.get("/slots", response_model=list[SlotResponse])
def list_slots(
    centre_id: Optional[CentreId] = Query(default=None, alias="centreId"),
    crop_code: Optional[CropCode] = Query(default=None, alias="cropCode"),
    slot_date: Optional[date] = Query(default=None, alias="date"),
    slot_status: Optional[SlotStatus] = Query(default=None, alias="status"),
    skip: int = 0,
    limit: int = 100,
) -> list[SlotResponse]:
    """List slots with optional centre, crop, date, and status filters."""
    if skip < 0:
        raise HTTPException(status_code=400, detail="skip must be zero or greater.")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100.")

    query = {}
    if centre_id is not None:
        query["centreId"] = centre_id
    if crop_code is not None:
        query["cropCode"] = crop_code
    if slot_date is not None:
        query["date"] = slot_date.isoformat()
    if slot_status is not None:
        query["status"] = slot_status.value

    documents = slots_collection().find(query).skip(skip).limit(limit)
    return [_slot_response(document) for document in documents]


@router.get("/slots/{slot_id}", response_model=SlotResponse)
def get_slot(slot_id: SlotId) -> SlotResponse:
    """Get one slot and its calculated remaining capacities."""
    document = slots_collection().find_one({"_id": slot_id})
    if document is None:
        raise HTTPException(status_code=404, detail="Slot not found.")

    return _slot_response(document)


@router.patch("/slots/{slot_id}", response_model=SlotResponse)
def update_slot(slot_id: SlotId, slot: SlotUpdate) -> SlotResponse:
    """Update a slot while preserving capacity, centre, crop, and close rules."""
    existing = slots_collection().find_one({"_id": slot_id})
    if existing is None:
        raise HTTPException(status_code=404, detail="Slot not found.")

    updates = slot.model_dump(by_alias=True, exclude_unset=True, exclude_none=True, mode="json")
    if not updates:
        raise HTTPException(status_code=400, detail="Provide at least one slot field to update.")
    requested_status = updates.pop("status", None)
    if "capacityKg" in updates:
        updates["capacityKg"] = _as_decimal128(slot.capacity_kg)
    has_allocations = (
        _as_decimal(existing["allocatedKg"]) > 0 or existing["allocatedFarmers"] > 0
    )
    protected_fields = {"centreId", "cropCode", "date", "startTime", "endTime"}
    if has_allocations and any(
        field in updates and updates[field] != existing[field] for field in protected_fields
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A slot with allocations cannot change centreId, cropCode, date, startTime, or endTime.",
        )
    if existing["status"] == SlotStatus.CLOSED.value:
        if requested_status is not None and requested_status != SlotStatus.CLOSED.value:
            raise HTTPException(status_code=400, detail="A CLOSED slot cannot be reopened.")
        final_status = SlotStatus.CLOSED.value
    elif requested_status is None:
        final_status = existing["status"]
    elif requested_status == SlotStatus.CLOSED.value:
        final_status = SlotStatus.CLOSED.value
    else:
        raise HTTPException(
            status_code=400,
            detail="AVAILABLE and FULL are calculated automatically; only CLOSED can be set.",
        )

    candidate = dict(existing)
    candidate.update(updates)
    _validate_slot_values(candidate)
    centre = _validate_centre_and_crop(candidate["centreId"], candidate["cropCode"])
    _validate_daily_centre_capacity(
        centre,
        candidate["date"],
        candidate["capacityKg"],
        excluding_slot_id=slot_id,
    )

    candidate["status"] = final_status
    if final_status != SlotStatus.CLOSED.value:
        candidate["status"] = _derived_status(candidate).value
    updates["status"] = candidate["status"]
    updates["updatedAt"] = datetime.now(timezone.utc)

    document = slots_collection().find_one_and_update(
        {"_id": slot_id},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Slot not found.")
    return _slot_response(document)


def _centre_slot_query(
    centre_id: CentreId,
    crop_code: Optional[CropCode],
    slot_date: Optional[date],
    slot_status: Optional[SlotStatus],
) -> dict:
    """Build shared filters for centre-scoped slot listing."""
    query = {"centreId": centre_id}
    if crop_code is not None:
        query["cropCode"] = crop_code
    if slot_date is not None:
        query["date"] = slot_date.isoformat()
    if slot_status is not None:
        query["status"] = slot_status.value
    return query


@router.get("/centres/{centre_id}/slots", response_model=list[SlotResponse])
def list_centre_slots(
    centre_id: CentreId,
    crop_code: Optional[CropCode] = Query(default=None, alias="cropCode"),
    slot_date: Optional[date] = Query(default=None, alias="date"),
    slot_status: Optional[SlotStatus] = Query(default=None, alias="status"),
    skip: int = 0,
    limit: int = 100,
) -> list[SlotResponse]:
    """List one centre's slots with optional crop, date, and status filters."""
    if skip < 0 or not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="Use skip >= 0 and limit from 1 to 100.")
    query = _centre_slot_query(centre_id, crop_code, slot_date, slot_status)
    documents = slots_collection().find(query).skip(skip).limit(limit)
    return [_slot_response(document) for document in documents]


@router.get("/centres/{centre_id}/slots/available", response_model=list[SlotResponse])
def list_available_centre_slots(
    centre_id: CentreId,
    crop_code: Optional[CropCode] = Query(default=None, alias="cropCode"),
    slot_date: Optional[date] = Query(default=None, alias="date"),
    skip: int = 0,
    limit: int = 100,
) -> list[SlotResponse]:
    """List only centre slots with quantity and farmer capacity remaining."""
    if skip < 0 or not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="Use skip >= 0 and limit from 1 to 100.")
    query = _centre_slot_query(centre_id, crop_code, slot_date, None)
    query["status"] = {"$ne": SlotStatus.CLOSED.value}
    query["$expr"] = {
        "$and": [
            {"$lt": ["$allocatedKg", "$capacityKg"]},
            {"$lt": ["$allocatedFarmers", "$maxFarmers"]},
        ]
    }
    documents = slots_collection().find(query).skip(skip).limit(limit)
    return [_slot_response(document) for document in documents]


class SlotAssignRequest(BaseModel):
    """Query payload to determine an eligible centre and slot deterministically."""

    model_config = ConfigDict(populate_by_name=True)

    farmer_id: str = Field(alias="farmerId")
    crop_code: str = Field(alias="cropCode")
    expected_quantity_kg: QuantityKg = Field(alias="expectedQuantityKg")
    farmer_area: Optional[str] = Field(default=None, alias="farmerArea")


class SlotAssignResponse(BaseModel):
    """Deterministically selected centre and slot for a given request."""

    model_config = ConfigDict(populate_by_name=True)

    centre_id: str = Field(alias="centreId")
    slot_id: str = Field(alias="slotId")
    centre: dict
    slot: SlotResponse


def find_deterministic_slot(
    farmer_id: str,
    crop_code: str,
    expected_quantity_kg: Decimal | Decimal128 | int | float | str,
    farmer_area: Optional[str] = None,
    session=None,
    reserve: bool = False,
) -> tuple[dict, dict]:
    """Find (and optionally atomically reserve) the best deterministic slot for a request.

    Deterministic selection rules:
    - Centre:
      1. Priority 1: Exact area match (centre.area == farmer_area)
      2. Priority 2: Same district match (centre.district == farmer_district)
      Tie-breaker: centreId ascending
    - Slot:
      1. Earliest available date
      2. Earliest startTime
      3. Highest remaining capacity sufficient for the request
      4. slotId ascending
    """
    database = get_database()
    farmer = database["farmers"].find_one({"_id": farmer_id}, session=session)
    if farmer is None:
        raise HTTPException(status_code=404, detail="Farmer not found.")

    crop = database["cropConfigurations"].find_one({"_id": crop_code}, session=session)
    if crop is None:
        raise HTTPException(status_code=404, detail="Crop configuration not found.")
    if crop.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Crop configuration is not ACTIVE.")

    qty = _as_decimal(expected_quantity_kg)
    if qty <= 0:
        raise HTTPException(status_code=400, detail="expectedQuantityKg must be greater than zero.")

    target_area = (farmer_area or farmer.get("area") or "").strip().lower()
    target_district = (farmer.get("district") or "").strip().lower()

    centres_cursor = database["centres"].find({}, session=session)
    priority_1_centres = []
    priority_2_centres = []

    for centre in centres_cursor:
        if centre.get("status") != "ACTIVE":
            continue
        supported = centre.get("supportedCrops", [])
        if crop_code not in supported:
            continue

        c_area = (centre.get("area") or "").strip().lower()
        c_district = (centre.get("district") or "").strip().lower()

        if target_area and c_area == target_area:
            priority_1_centres.append(centre)
        elif target_district and c_district == target_district:
            priority_2_centres.append(centre)

    priority_1_centres.sort(key=lambda c: str(c.get("centreId", c.get("_id", ""))))
    priority_2_centres.sort(key=lambda c: str(c.get("centreId", c.get("_id", ""))))

    candidate_centres = priority_1_centres + priority_2_centres

    for centre in candidate_centres:
        centre_id = centre.get("centreId") or centre.get("_id")
        slots_cursor = database["slots"].find(
            {"centreId": centre_id, "cropCode": crop_code},
            session=session,
        )

        candidate_slots = []
        for slot in slots_cursor:
            if slot.get("status") == SlotStatus.CLOSED.value:
                continue
            if _derived_status(slot) == SlotStatus.CLOSED:
                continue
            if slot_can_accept(slot, qty):
                candidate_slots.append(slot)

        if not candidate_slots:
            continue

        def _slot_sort_key(s: dict) -> tuple:
            rem_capacity = _as_decimal(s.get("capacityKg", 0)) - _as_decimal(s.get("allocatedKg", 0))
            s_id = str(s.get("slotId", s.get("_id", "")))
            date_val = str(s.get("date", ""))
            time_val = str(s.get("startTime", ""))
            return (date_val, time_val, -rem_capacity, s_id)

        candidate_slots.sort(key=_slot_sort_key)

        if not reserve:
            return centre, candidate_slots[0]

        for slot in candidate_slots:
            s_id = slot.get("slotId", slot.get("_id"))
            reserved = reserve_slot_capacity(s_id, qty, session=session)
            if reserved is not None:
                return centre, reserved

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="No eligible procurement slot can accommodate the requested quantity.",
    )


def _clean_centre_doc(doc: dict) -> dict:
    """Ensure centre doc fields (like Decimal128) are serializable by Pydantic."""
    clean = dict(doc)
    for k, v in clean.items():
        if isinstance(v, Decimal128):
            clean[k] = v.to_decimal()
        elif isinstance(v, dict):
            clean[k] = _clean_centre_doc(v)
    if "_id" in clean and not isinstance(clean["_id"], str):
        clean["_id"] = str(clean["_id"])
    return clean


@router.post("/slots/assign", response_model=SlotAssignResponse)
def assign_slot_endpoint(request: SlotAssignRequest) -> SlotAssignResponse:
    """Preview or determine the best deterministic centre and slot for a request."""
    centre, slot = find_deterministic_slot(
        farmer_id=request.farmer_id,
        crop_code=request.crop_code,
        expected_quantity_kg=request.expected_quantity_kg,
        farmer_area=request.farmer_area,
        reserve=False,
    )
    return SlotAssignResponse(
        centreId=centre.get("centreId") or centre.get("_id"),
        slotId=slot.get("slotId") or slot.get("_id"),
        centre=_clean_centre_doc(centre),
        slot=_slot_response(slot),
    )


