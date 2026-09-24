"""Capacity-safe procurement request booking endpoints."""

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from bson.decimal128 import Decimal128
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from database import get_database, mongo_client
from lots import create_lot_for_arrival, get_lot_by_request_id
from slots import (
    SlotStatus,
    _as_decimal,
    _as_decimal128,
    find_deterministic_slot,
    release_slot_capacity,
    reserve_slot_capacity,
    slot_can_accept,
)
from auth import get_current_user

router = APIRouter(tags=["Procurement Requests"])

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
QuantityKg = Annotated[Decimal, Field(gt=0)]


class BookingStatus(str, Enum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class ArrivalStatus(str, Enum):
    NOT_ARRIVED = "NOT_ARRIVED"
    ARRIVED = "ARRIVED"


class RequestStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    ARRIVED = "ARRIVED"
    QC_IN_PROGRESS = "QC_IN_PROGRESS"
    QC_FAILED = "QC_FAILED"
    QC_PASSED = "QC_PASSED"
    WEIGHMENT_COMPLETED = "WEIGHMENT_COMPLETED"
    PROCURED = "PROCURED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class ProcurementRequestCreate(BaseModel):
    """Input needed to reserve one selected centre and slot for a farmer."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "requestId": "REQ-001",
                "farmerId": "FARMER-001",
                "cropCode": "WHEAT",
                "farmerArea": "Sinnar",
                "expectedQuantityKg": 2500.5,
                "assignedCentreId": "CENTRE-001",
                "assignedSlotId": "SLOT-001",
            }
        },
    )

    request_id: RequestId = Field(alias="requestId")
    farmer_id: FarmerId = Field(alias="farmerId")
    crop_code: CropCode = Field(alias="cropCode")
    farmer_area: Annotated[str, Field(alias="farmerArea", min_length=1, max_length=150)]
    expected_quantity_kg: QuantityKg = Field(alias="expectedQuantityKg")
    assigned_centre_id: Optional[CentreId] = Field(default=None, alias="assignedCentreId")
    assigned_slot_id: Optional[SlotId] = Field(default=None, alias="assignedSlotId")
    auto_assign: Optional[bool] = Field(default=False, alias="autoAssign")


class ProcurementRequestResponse(ProcurementRequestCreate):
    """Stored request record returned after a successful slot reservation."""

    assigned_centre_id: CentreId = Field(alias="assignedCentreId")
    assigned_slot_id: SlotId = Field(alias="assignedSlotId")
    booking_status: BookingStatus = Field(alias="bookingStatus")
    arrival_status: ArrivalStatus = Field(alias="arrivalStatus")
    arrived_at: Optional[datetime] = Field(default=None, alias="arrivedAt")
    arrival_marked_by_employee_id: Optional[str] = Field(
        default=None, alias="arrivalMarkedByEmployeeId"
    )
    queue_number: Annotated[int, Field(alias="queueNumber", gt=0)]
    request_status: RequestStatus = Field(alias="requestStatus")
    lot_id: Optional[str] = Field(default=None, alias="lotId")
    rejection_reason: Optional[str] = Field(default=None, alias="rejectionReason")
    rejected_by_employee_id: Optional[str] = Field(default=None, alias="rejectedByEmployeeId")
    rejected_at: Optional[datetime] = Field(default=None, alias="rejectedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class QueueResponse(BaseModel):
    """Queue information for a confirmed procurement request."""

    model_config = ConfigDict(populate_by_name=True)

    request_id: RequestId = Field(alias="requestId")
    farmer_id: FarmerId = Field(alias="farmerId")
    centre_id: CentreId = Field(alias="centreId")
    slot_id: SlotId = Field(alias="slotId")
    queue_number: Annotated[int, Field(alias="queueNumber", gt=0)]
    expected_quantity_kg: QuantityKg = Field(alias="expectedQuantityKg")
    request_status: RequestStatus = Field(alias="requestStatus")


class RequestStatusResponse(BaseModel):
    """Small status response suitable for future mobile or IVR callers."""

    model_config = ConfigDict(populate_by_name=True)

    request_id: RequestId = Field(alias="requestId")
    booking_status: BookingStatus = Field(alias="bookingStatus")
    arrival_status: ArrivalStatus = Field(alias="arrivalStatus")
    request_status: RequestStatus = Field(alias="requestStatus")


class ArrivalMarkRequest(BaseModel):
    """Worker-confirmed farmer identity for a scheduled arrival."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    farmer_id: FarmerId = Field(alias="farmerId")
    employee_id: Annotated[
        str, Field(alias="employeeId", min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    ]


class ArrivalResponse(BaseModel):
    """Arrival state recorded on the procurement request itself."""

    model_config = ConfigDict(populate_by_name=True)

    request_id: RequestId = Field(alias="requestId")
    farmer_id: FarmerId = Field(alias="farmerId")
    centre_id: CentreId = Field(alias="centreId")
    arrival_status: ArrivalStatus = Field(alias="arrivalStatus")
    arrived_at: Optional[datetime] = Field(default=None, alias="arrivedAt")
    arrival_marked_by_employee_id: Optional[str] = Field(
        default=None, alias="arrivalMarkedByEmployeeId"
    )
    request_status: RequestStatus = Field(alias="requestStatus")
    lot_id: Optional[str] = Field(default=None, alias="lotId")


def procurement_requests_collection():
    """Return the shared MongoDB procurementRequests collection."""
    return get_database()["procurementRequests"]


def ensure_procurement_request_indexes() -> None:
    """Create indexes required by the Procurement Request module."""
    collection = procurement_requests_collection()
    collection.create_index("requestId", unique=True, name="request_id_unique")
    collection.create_index([("farmerId", ASCENDING)], name="farmer_id_index")
    collection.create_index([("assignedCentreId", ASCENDING)], name="centre_id_index")
    collection.create_index([("assignedSlotId", ASCENDING)], name="slot_id_index")
    collection.create_index([("cropCode", ASCENDING)], name="crop_code_index")
    collection.create_index([("requestStatus", ASCENDING)], name="request_status_index")
    collection.create_index(
        [("farmerId", ASCENDING), ("createdAt", DESCENDING)],
        name="farmer_created_at_index",
    )
    collection.create_index(
        [("assignedCentreId", ASCENDING), ("assignedSlotId", ASCENDING)],
        name="centre_slot_index",
    )
    collection.create_index(
        [
            ("assignedCentreId", ASCENDING),
            ("requestStatus", ASCENDING),
            ("createdAt", DESCENDING),
        ],
        name="centre_status_created_at_index",
    )
    collection.create_index(
        [
            ("assignedCentreId", ASCENDING),
            ("assignedSlotId", ASCENDING),
            ("queueNumber", ASCENDING),
        ],
        unique=True,
        name="centre_slot_queue_unique",
    )


def _request_response(document: dict) -> ProcurementRequestResponse:
    """Convert a MongoDB request document into the public response shape."""
    response_document = dict(document)
    response_document["expectedQuantityKg"] = _as_decimal(document["expectedQuantityKg"])
    return ProcurementRequestResponse.model_validate(response_document)


def _arrival_response(document: dict) -> ArrivalResponse:
    """Convert a procurement request into its public arrival state."""
    return ArrivalResponse(
        requestId=document["requestId"],
        farmerId=document["farmerId"],
        centreId=document["assignedCentreId"],
        arrivalStatus=document["arrivalStatus"],
        arrivedAt=document.get("arrivedAt"),
        arrivalMarkedByEmployeeId=document.get("arrivalMarkedByEmployeeId"),
        requestStatus=document["requestStatus"],
        lotId=document.get("lotId"),
    )


def _validate_scheduled_slot(request: dict, session=None) -> dict:
    """Ensure the request still points to a valid scheduled slot and date."""
    slot = get_database()["slots"].find_one({"_id": request["assignedSlotId"]}, session=session)
    if slot is None:
        raise HTTPException(status_code=409, detail="The request's scheduled slot is unavailable.")
    if slot.get("centreId") != request["assignedCentreId"]:
        raise HTTPException(status_code=409, detail="The scheduled slot does not belong to the request centre.")
    if slot.get("cropCode") != request["cropCode"]:
        raise HTTPException(status_code=409, detail="The scheduled slot cropCode does not match the request.")
    if slot.get("status") == SlotStatus.CLOSED.value:
        raise HTTPException(status_code=409, detail="The request's scheduled slot is CLOSED.")
    try:
        date.fromisoformat(str(slot["date"]))
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(status_code=409, detail="The request's scheduled date is invalid.") from error
    return slot


def _validate_booking_references(document: dict, session) -> dict:
    """Validate farmer, crop, centre, and selected slot before reserving capacity."""
    database = get_database()
    if database["farmers"].find_one({"_id": document["farmerId"]}, session=session) is None:
        raise HTTPException(status_code=404, detail="Farmer not found.")

    crop = database["cropConfigurations"].find_one(
        {"_id": document["cropCode"]}, session=session
    )
    if crop is None:
        raise HTTPException(status_code=404, detail="Crop configuration not found.")
    if crop.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Crop configuration is not ACTIVE.")

    centre = database["centres"].find_one(
        {"_id": document["assignedCentreId"]}, session=session
    )
    if centre is None:
        raise HTTPException(status_code=404, detail="Centre not found.")
    if centre.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Centre is not ACTIVE.")
    if document["cropCode"] not in centre.get("supportedCrops", []):
        raise HTTPException(status_code=400, detail="Centre does not support this cropCode.")

    slot = database["slots"].find_one({"_id": document["assignedSlotId"]}, session=session)
    if slot is None:
        raise HTTPException(status_code=404, detail="Slot not found.")
    if slot["centreId"] != document["assignedCentreId"]:
        raise HTTPException(status_code=400, detail="Slot does not belong to assignedCentreId.")
    if slot["cropCode"] != document["cropCode"]:
        raise HTTPException(status_code=400, detail="Slot cropCode does not match the request.")
    if slot["status"] == SlotStatus.CLOSED.value:
        raise HTTPException(status_code=400, detail="Slot is CLOSED.")
    if not slot_can_accept(slot, document["expectedQuantityKg"]):
        raise HTTPException(status_code=409, detail="Slot does not have enough remaining capacity.")
    return slot


def _next_queue_number(centre_id: str, slot_id: str, session) -> int:
    """Get the next queue position within a centre/slot transaction."""
    latest = procurement_requests_collection().find_one(
        {"assignedCentreId": centre_id, "assignedSlotId": slot_id},
        projection={"queueNumber": 1},
        sort=[("queueNumber", DESCENDING)],
        session=session,
    )
    return (latest["queueNumber"] if latest else 0) + 1


def _create_request_transaction(session, request_data: dict) -> dict:
    """Run all booking writes in one transaction callback."""
    # Check requestId uniqueness inside the transaction to avoid race conditions
    if procurement_requests_collection().find_one({"_id": request_data["requestId"]}, session=session):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A procurement request with this requestId already exists.",
        )
    txn_data = dict(request_data)
    auto_assign = bool(txn_data.get("autoAssign") or not txn_data.get("assignedSlotId"))

    if auto_assign:
        centre, reserved_slot = find_deterministic_slot(
            farmer_id=txn_data["farmerId"],
            crop_code=txn_data["cropCode"],
            expected_quantity_kg=txn_data["expectedQuantityKg"],
            farmer_area=txn_data.get("farmerArea"),
            session=session,
            reserve=True,
        )
        txn_data["assignedCentreId"] = centre.get("centreId") or centre.get("_id")
        txn_data["assignedSlotId"] = reserved_slot.get("slotId") or reserved_slot.get("_id")
    else:
        _validate_booking_references(txn_data, session)
        reserved_slot = reserve_slot_capacity(
            txn_data["assignedSlotId"], txn_data["expectedQuantityKg"], session=session
        )
        if reserved_slot is None:
            raise HTTPException(status_code=409, detail="Slot capacity is no longer available.")

    now = datetime.now(timezone.utc)
    document = dict(txn_data)
    document["_id"] = document["requestId"]
    document["queueNumber"] = _next_queue_number(
        document["assignedCentreId"], document["assignedSlotId"], session
    )
    document["bookingStatus"] = BookingStatus.CONFIRMED.value
    document["arrivalStatus"] = ArrivalStatus.NOT_ARRIVED.value
    document["arrivedAt"] = None
    document["arrivalMarkedByEmployeeId"] = None
    document["requestStatus"] = RequestStatus.SCHEDULED.value
    document["createdAt"] = now
    document["updatedAt"] = now
    document["expectedQuantityKg"] = _as_decimal128(document["expectedQuantityKg"])
    procurement_requests_collection().insert_one(document, session=session)
    return document


@router.post(
    "/procurement-requests",
    response_model=ProcurementRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_procurement_request(
    request: ProcurementRequestCreate,
    current_user: Optional[dict] = Depends(get_current_user),
) -> ProcurementRequestResponse:
    """Validate a selected slot and atomically create a confirmed request."""
    request_data = request.model_dump(by_alias=True)

    # Prevent impersonation if a farmer is logged in
    if current_user and current_user.get("userType") == "farmer":
        if request_data.get("farmerId") != current_user.get("farmerId"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to book for another farmer.",
            )

    for attempt in range(3):
        try:
            with mongo_client.start_session() as session:
                document = session.with_transaction(
                    lambda active_session: _create_request_transaction(
                        active_session, request_data
                    )
                )
            return _request_response(document)
        except HTTPException:
            raise
        except DuplicateKeyError as error:
            # Distinguish between requestId conflict and centre+slot+queueNumber conflict
            if procurement_requests_collection().find_one({"_id": request_data["requestId"]}):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A procurement request with this requestId already exists.",
                ) from error
            if attempt == 2:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not safely assign a queue number. Please retry.",
                ) from error
        except PyMongoError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not complete the booking safely. Please retry.",
            ) from error

    raise HTTPException(status_code=409, detail="Could not safely create the request.")


@router.get("/procurement-requests/{request_id}/queue", response_model=QueueResponse)
def get_request_queue(request_id: RequestId) -> QueueResponse:
    """Return the slot-specific queue information for one request."""
    document = procurement_requests_collection().find_one({"_id": request_id})
    if document is None:
        raise HTTPException(status_code=404, detail="Procurement request not found.")
    return QueueResponse(
        requestId=document["requestId"],
        farmerId=document["farmerId"],
        centreId=document["assignedCentreId"],
        slotId=document["assignedSlotId"],
        queueNumber=document["queueNumber"],
        expectedQuantityKg=_as_decimal(document["expectedQuantityKg"]),
        requestStatus=document["requestStatus"],
    )


@router.get("/procurement-requests/{request_id}/status", response_model=RequestStatusResponse)
def get_request_status(request_id: RequestId) -> RequestStatusResponse:
    """Return current booking, arrival, and request status for one request."""
    document = procurement_requests_collection().find_one({"_id": request_id})
    if document is None:
        raise HTTPException(status_code=404, detail="Procurement request not found.")
    return RequestStatusResponse.model_validate(document)


def _mark_arrival_transaction(
    session,
    request_id: str,
    arrival: ArrivalMarkRequest,
    now: datetime,
) -> dict:
    """Run all arrival checks, Lot creation, and request updates in one transaction callback."""
    collection = procurement_requests_collection()
    request = collection.find_one({"_id": request_id}, session=session)
    if request is None:
        raise HTTPException(status_code=404, detail="Procurement request not found.")
    if arrival.farmer_id != request["farmerId"]:
        raise HTTPException(status_code=400, detail="farmerId does not match the procurement request.")
    if request.get("bookingStatus") == BookingStatus.CANCELLED.value or request.get(
        "requestStatus"
    ) == RequestStatus.CANCELLED.value:
        raise HTTPException(status_code=409, detail="A cancelled procurement request cannot arrive.")
    if request.get("arrivalStatus") == ArrivalStatus.ARRIVED.value:
        raise HTTPException(status_code=409, detail="Procurement request is already marked ARRIVED.")
    if request.get("requestStatus") != RequestStatus.SCHEDULED.value:
        raise HTTPException(
            status_code=409,
            detail="Only a SCHEDULED procurement request can be marked ARRIVED.",
        )

    if get_lot_by_request_id(request_id, session=session) is not None:
        raise HTTPException(
            status_code=409,
            detail="A Lot already exists for this procurement request.",
        )

    employee = get_database()["employees"].find_one({"_id": arrival.employee_id}, session=session)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found.")
    if employee.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Employee is not ACTIVE.")
    if employee.get("centreId") != request["assignedCentreId"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee does not belong to the request's assigned centre.",
        )

    slot = _validate_scheduled_slot(request, session=session)

    lot = create_lot_for_arrival(
        request=request,
        slot=slot,
        arrived_at=now,
        session=session,
    )

    updated = collection.find_one_and_update(
        {
            "_id": request_id,
            "farmerId": arrival.farmer_id,
            "bookingStatus": BookingStatus.CONFIRMED.value,
            "arrivalStatus": ArrivalStatus.NOT_ARRIVED.value,
            "requestStatus": RequestStatus.SCHEDULED.value,
        },
        {
            "$set": {
                "arrivalStatus": ArrivalStatus.ARRIVED.value,
                "arrivedAt": now,
                "arrivalMarkedByEmployeeId": arrival.employee_id,
                "requestStatus": RequestStatus.ARRIVED.value,
                "lotId": lot["lotId"],
                "updatedAt": now,
            }
        },
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    if updated is None:
        raise HTTPException(
            status_code=409,
            detail="Arrival could not be recorded because the request state changed. Please retry.",
        )

    return updated


@router.post(
    "/procurement-requests/{request_id}/arrival",
    response_model=ArrivalResponse,
)
def mark_procurement_request_arrival(
    request_id: RequestId,
    arrival: ArrivalMarkRequest,
) -> ArrivalResponse:
    """Mark one scheduled request ARRIVED at its assigned employee's centre and create its Lot."""
    now = datetime.now(timezone.utc)

    for attempt in range(3):
        try:
            with mongo_client.start_session() as session:
                updated = session.with_transaction(
                    lambda active_session: _mark_arrival_transaction(
                        active_session, request_id, arrival, now
                    )
                )
            return _arrival_response(updated)
        except HTTPException:
            raise
        except DuplicateKeyError as error:
            existing_request = procurement_requests_collection().find_one({"_id": request_id})
            if existing_request and existing_request.get("arrivalStatus") == ArrivalStatus.ARRIVED.value:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Procurement request is already marked ARRIVED.",
                ) from error
            existing_lot = get_lot_by_request_id(request_id)
            if existing_lot:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A Lot already exists for this procurement request.",
                ) from error
            if attempt == 2:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not safely create Lot due to ID collision. Please retry.",
                ) from error
        except PyMongoError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not record arrival safely. Please retry.",
            ) from error

    raise HTTPException(status_code=409, detail="Could not safely mark arrival.")


@router.get(
    "/procurement-requests/{request_id}/arrival",
    response_model=ArrivalResponse,
)
def get_procurement_request_arrival(request_id: RequestId) -> ArrivalResponse:
    """Read the arrival state held on a procurement request."""
    document = procurement_requests_collection().find_one({"_id": request_id})
    if document is None:
        raise HTTPException(status_code=404, detail="Procurement request not found.")
    return _arrival_response(document)


@router.patch(
    "/procurement-requests/{request_id}/cancel", response_model=ProcurementRequestResponse
)
def cancel_procurement_request(request_id: RequestId) -> ProcurementRequestResponse:
    """Cancel a request and atomically return its capacity to the assigned slot."""
    def cancel_transaction(session):
        document = procurement_requests_collection().find_one({"_id": request_id}, session=session)
        if document is None:
            raise HTTPException(status_code=404, detail="Procurement request not found.")
        if document["bookingStatus"] == BookingStatus.CANCELLED.value:
            raise HTTPException(status_code=409, detail="Procurement request is already cancelled.")
        if document["requestStatus"] != RequestStatus.SCHEDULED.value:
            raise HTTPException(
                status_code=409,
                detail="Only SCHEDULED procurement requests can be cancelled.",
            )

        released_slot = release_slot_capacity(
            document["assignedSlotId"], document["expectedQuantityKg"], session=session
        )
        if released_slot is None:
            raise HTTPException(
                status_code=409,
                detail="Slot allocation could not be safely released.",
            )
        updated = procurement_requests_collection().find_one_and_update(
            {"_id": request_id, "bookingStatus": BookingStatus.CONFIRMED.value},
            {
                "$set": {
                    "bookingStatus": BookingStatus.CANCELLED.value,
                    "requestStatus": RequestStatus.CANCELLED.value,
                    "updatedAt": datetime.now(timezone.utc),
                }
            },
            return_document=ReturnDocument.AFTER,
            session=session,
        )
        if updated is None:
            raise HTTPException(status_code=409, detail="Request cancellation could not be completed.")
        return updated

    try:
        with mongo_client.start_session() as session:
            document = session.with_transaction(cancel_transaction)
    except HTTPException:
        raise
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not cancel the request safely. Please retry.",
        ) from error
    return _request_response(document)


class RejectRequestInput(BaseModel):
    """Employee-authorized rejection for a procurement request."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    employee_id: Annotated[
        str, Field(alias="employeeId", min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    ]
    rejection_reason: Optional[str] = Field(default=None, alias="rejectionReason", max_length=500)


@router.post(
    "/procurement-requests/{request_id}/reject",
    response_model=ProcurementRequestResponse,
)
def reject_procurement_request(
    request_id: RequestId,
    reject_input: RejectRequestInput,
) -> ProcurementRequestResponse:
    """Mark a procurement request and its linked Lot as REJECTED."""
    now = datetime.now(timezone.utc)
    database = get_database()

    employee = database["employees"].find_one({"_id": reject_input.employee_id})
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found.")
    if employee.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Employee is not ACTIVE.")

    req = procurement_requests_collection().find_one({"_id": request_id})
    if req is None:
        raise HTTPException(status_code=404, detail="Procurement request not found.")
    if req.get("requestStatus") in (
        RequestStatus.CANCELLED.value,
        RequestStatus.COMPLETED.value,
        RequestStatus.REJECTED.value,
    ):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reject a request that is already {req.get('requestStatus')}.",
        )
    if employee.get("centreId") != req.get("assignedCentreId"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee does not belong to the request's assigned centre.",
        )

    updated = procurement_requests_collection().find_one_and_update(
        {"_id": request_id},
        {
            "$set": {
                "requestStatus": RequestStatus.REJECTED.value,
                "rejectionReason": reject_input.rejection_reason or "Rejected by officer",
                "rejectedByEmployeeId": reject_input.employee_id,
                "rejectedAt": now,
                "updatedAt": now,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    lot_id = req.get("lotId")
    if lot_id:
        database["lots"].update_one(
            {"$or": [{"_id": lot_id}, {"lotId": lot_id}]},
            {"$set": {"status": "REJECTED", "updatedAt": now}},
        )

    return _request_response(updated)


@router.get(
    "/farmers/{farmer_id}/procurement-requests",
    response_model=list[ProcurementRequestResponse],
)
def list_farmer_procurement_requests(
    farmer_id: FarmerId,
    skip: int = 0,
    limit: int = 100,
) -> list[ProcurementRequestResponse]:
    """List all procurement requests belonging to one farmer."""
    if skip < 0 or not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="Use skip >= 0 and limit from 1 to 100.")
    documents = (
        procurement_requests_collection()
        .find({"farmerId": farmer_id})
        .sort("createdAt", DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    return [_request_response(document) for document in documents]


@router.get(
    "/centres/{centre_id}/procurement-requests",
    response_model=list[ProcurementRequestResponse],
)
def list_centre_procurement_requests(
    centre_id: CentreId,
    slot_date: Optional[str] = Query(default=None, alias="date", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    crop_code: Optional[CropCode] = Query(default=None, alias="cropCode"),
    request_status: Optional[RequestStatus] = Query(default=None, alias="status"),
    skip: int = 0,
    limit: int = 100,
) -> list[ProcurementRequestResponse]:
    """List one centre's requests with optional slot date, crop, and status filters."""
    if skip < 0 or not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="Use skip >= 0 and limit from 1 to 100.")
    query = {"assignedCentreId": centre_id}
    if crop_code is not None:
        query["cropCode"] = crop_code
    if request_status is not None:
        query["requestStatus"] = request_status.value
    if slot_date is not None:
        slot_ids = [
            slot["_id"]
            for slot in get_database()["slots"].find(
                {"centreId": centre_id, "date": slot_date}, projection={"_id": 1}
            )
        ]
        query["assignedSlotId"] = {"$in": slot_ids}

    documents = (
        procurement_requests_collection()
        .find(query)
        .sort("createdAt", DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    return [_request_response(document) for document in documents]


@router.get("/procurement-requests/{request_id}", response_model=ProcurementRequestResponse)
def get_procurement_request(request_id: RequestId) -> ProcurementRequestResponse:
    """Get one procurement request by request ID."""
    document = procurement_requests_collection().find_one({"_id": request_id})
    if document is None:
        raise HTTPException(status_code=404, detail="Procurement request not found.")
    return _request_response(document)
