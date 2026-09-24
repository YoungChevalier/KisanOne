"""Lot schemas and API endpoints for government procurement."""

from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from database import get_database, mongo_client

router = APIRouter(tags=["Lots"])

LotId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique Lot ID.",
    ),
]
RequestId = Annotated[
    str, Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
]
FarmerId = Annotated[
    str, Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
]
CentreId = Annotated[
    str, Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
]
CropCode = Annotated[
    str, Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
]
SlotId = Annotated[
    str, Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
]


class LotStatus(str, Enum):
    """Operational state of a Lot."""

    CREATED = "CREATED"
    QC_IN_PROGRESS = "QC_IN_PROGRESS"
    QC_PASSED = "QC_PASSED"
    QC_FAILED = "QC_FAILED"
    WEIGHMENT_COMPLETED = "WEIGHMENT_COMPLETED"
    PROCURED = "PROCURED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class LotResponse(BaseModel):
    """Lot record returned by the API."""

    model_config = ConfigDict(populate_by_name=True)

    lot_id: LotId = Field(alias="lotId")
    request_id: RequestId = Field(alias="requestId")
    farmer_id: FarmerId = Field(alias="farmerId")
    crop_code: CropCode = Field(alias="cropCode")
    centre_id: CentreId = Field(alias="centreId")
    slot_id: SlotId = Field(alias="slotId")
    scheduled_date: date = Field(alias="scheduledDate")
    scheduled_start_time: time = Field(alias="scheduledStartTime")
    scheduled_end_time: time = Field(alias="scheduledEndTime")
    arrived_at: datetime = Field(alias="arrivedAt")
    status: LotStatus
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


def lots_collection():
    """Return the shared MongoDB lots collection."""
    return get_database()["lots"]


def counters_collection():
    """Return the shared MongoDB counters collection."""
    return get_database()["counters"]


def ensure_lot_indexes() -> None:
    """Create indexes required by the Lot module."""
    collection = lots_collection()
    collection.create_index("lotId", unique=True, name="lot_id_unique")
    collection.create_index("requestId", unique=True, name="request_id_unique")
    collection.create_index([("farmerId", ASCENDING)], name="farmer_id_index")
    collection.create_index([("centreId", ASCENDING)], name="centre_id_index")
    collection.create_index([("cropCode", ASCENDING)], name="crop_code_index")
    collection.create_index([("slotId", ASCENDING)], name="slot_id_index")
    collection.create_index([("status", ASCENDING)], name="status_index")
    collection.create_index([("createdAt", DESCENDING)], name="created_at_index")
    try:
        _initialize_lot_counter_if_needed()
    except PyMongoError:
        pass


def _initialize_lot_counter_if_needed(session=None) -> None:
    """Initialize the lotId counter from existing lots if not present."""
    counters = counters_collection()
    if counters.find_one({"_id": "lotId"}, session=session) is None:
        latest = lots_collection().find_one(
            projection={"lotId": 1},
            sort=[("lotId", DESCENDING)],
            session=session,
        )
        current_seq = 0
        if latest and "lotId" in latest:
            try:
                current_seq = int(latest["lotId"].split("-")[-1])
            except (ValueError, IndexError):
                current_seq = 0
        counters.update_one(
            {"_id": "lotId"},
            {"$setOnInsert": {"seq": current_seq}},
            upsert=True,
            session=session,
        )


def _generate_lot_id(session=None) -> str:
    """Generate the next Lot ID in sequence (LOT-000001, LOT-000002, ...) concurrency-safely."""
    _initialize_lot_counter_if_needed(session=session)
    counter = counters_collection().find_one_and_update(
        {"_id": "lotId"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    seq = counter["seq"]
    return f"LOT-{seq:06d}"


def _lot_response(document: dict) -> LotResponse:
    """Convert a MongoDB lot document into the public response shape."""
    return LotResponse.model_validate(document)


def create_lot_for_arrival(
    request: dict,
    slot: dict,
    arrived_at: datetime,
    session=None,
) -> dict:
    """
    Create a Lot document for an arrived procurement request.

    This function is called within the arrival transaction to ensure
    atomic Lot creation with arrival state change.
    """
    lot_id = _generate_lot_id(session=session)

    now = datetime.now(timezone.utc)
    lot_document = {
        "_id": lot_id,
        "lotId": lot_id,
        "requestId": request["requestId"],
        "farmerId": request["farmerId"],
        "cropCode": request["cropCode"],
        "centreId": request["assignedCentreId"],
        "slotId": request["assignedSlotId"],
        "scheduledDate": str(slot["date"]),
        "scheduledStartTime": str(slot.get("startTime", "00:00:00")),
        "scheduledEndTime": str(slot.get("endTime", "00:00:00")),
        "arrivedAt": arrived_at,
        "status": LotStatus.CREATED.value,
        "createdAt": now,
        "updatedAt": now,
    }

    lots_collection().insert_one(lot_document, session=session)
    return lot_document


def get_lot_by_request_id(request_id: str, session=None) -> Optional[dict]:
    """Get Lot by procurement request ID."""
    return lots_collection().find_one({"requestId": request_id}, session=session)


def get_lot_by_id(lot_id: str, session=None) -> Optional[dict]:
    """Get Lot by Lot ID."""
    return lots_collection().find_one({"lotId": lot_id}, session=session)


@router.get("/lots/{lot_id}", response_model=LotResponse)
def get_lot(lot_id: LotId) -> LotResponse:
    """Get one Lot by Lot ID."""
    try:
        document = get_lot_by_id(lot_id)
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while retrieving lot.",
        ) from error
    if document is None:
        raise HTTPException(status_code=404, detail="Lot not found.")
    return _lot_response(document)


@router.get("/procurement-requests/{request_id}/lot", response_model=LotResponse)
def get_lot_by_request(request_id: RequestId) -> LotResponse:
    """Get the Lot associated with a procurement request."""
    try:
        request = get_database()["procurementRequests"].find_one({"_id": request_id})
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while verifying procurement request.",
        ) from error

    if request is None:
        raise HTTPException(status_code=404, detail="Procurement request not found.")
    if request.get("arrivalStatus") != "ARRIVED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Procurement request has not yet arrived.",
        )

    try:
        document = get_lot_by_request_id(request_id)
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while retrieving lot.",
        ) from error

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Lot not found for this procurement request.",
        )
    return _lot_response(document)