"""Weighment schemas and API endpoints for government procurement."""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Optional

from bson.decimal128 import Decimal128
from fastapi import APIRouter, HTTPException, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from database import get_database, mongo_client

router = APIRouter(tags=["Weighments"])

WeighmentId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique Weighment ID.",
    ),
]
LotId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique Lot ID.",
    ),
]
EmployeeId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique Employee ID.",
    ),
]
WeightKg = Annotated[Decimal, Field(gt=0)]
TareWeightKg = Annotated[Decimal, Field(ge=0)]
DeviceId = Annotated[str, Field(min_length=1, max_length=100)]
Remarks = Annotated[str, Field(min_length=1, max_length=500)]


class WeighmentStatus(str, Enum):
    """Operational state of a Weighment attempt."""

    RECORDED = "RECORDED"


def _as_decimal(value: Decimal | Decimal128 | int | float | str) -> Decimal:
    """Return exact quantities, including MongoDB Decimal128 values."""
    if isinstance(value, Decimal128):
        return value.to_decimal()
    return Decimal(str(value))


def _as_decimal128(value: Decimal | Decimal128 | int | float | str) -> Decimal128:
    """Encode a quantity exactly for BSON storage."""
    if isinstance(value, Decimal128):
        return value
    return Decimal128(_as_decimal(value))


class WeighmentCreate(BaseModel):
    """Request body for recording produce weighment on a Lot."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    employee_id: EmployeeId = Field(
        validation_alias=AliasChoices("employeeId", "performedByEmployeeId"),
        alias="employeeId",
        description="ID of the weighment officer conducting the measurement.",
    )
    gross_weight_kg: WeightKg = Field(alias="grossWeightKg")
    tare_weight_kg: TareWeightKg = Field(default=Decimal("0"), alias="tareWeightKg")
    device_id: Optional[DeviceId] = Field(default=None, alias="deviceId")
    remarks: Optional[Remarks] = None
    performed_at: Optional[datetime] = Field(
        default=None,
        alias="performedAt",
        description="Optional timestamp when the weighment took place. Defaults to current time.",
    )


class WeighmentResponse(BaseModel):
    """Stored weighment attempt record returned by the API."""

    model_config = ConfigDict(populate_by_name=True)

    weighment_id: WeighmentId = Field(alias="weighmentId")
    lot_id: LotId = Field(alias="lotId")
    request_id: str = Field(alias="requestId")
    farmer_id: str = Field(alias="farmerId")
    centre_id: str = Field(alias="centreId")
    crop_code: str = Field(alias="cropCode")
    attempt_number: Annotated[int, Field(alias="attemptNumber", gt=0)]
    gross_weight_kg: Decimal = Field(alias="grossWeightKg")
    tare_weight_kg: Decimal = Field(alias="tareWeightKg")
    net_weight_kg: Decimal = Field(alias="netWeightKg")
    performed_by_employee_id: str = Field(alias="performedByEmployeeId")
    performed_at: datetime = Field(alias="performedAt")
    status: WeighmentStatus
    device_id: Optional[str] = Field(default=None, alias="deviceId")
    remarks: Optional[str] = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


def weighments_collection():
    """Return the shared MongoDB weighments collection."""
    return get_database()["weighments"]


def counters_collection():
    """Return the shared MongoDB counters collection."""
    return get_database()["counters"]


def ensure_weighment_indexes() -> None:
    """Create indexes required by the Weighment module."""
    collection = weighments_collection()
    collection.create_index(
        "weighmentId", unique=True, name="weighment_id_unique"
    )
    collection.create_index(
        [("lotId", ASCENDING), ("attemptNumber", ASCENDING)],
        unique=True,
        name="lot_weighment_attempt_unique",
    )
    collection.create_index([("lotId", ASCENDING)], name="lot_id_index")
    collection.create_index([("requestId", ASCENDING)], name="request_id_index")
    collection.create_index([("farmerId", ASCENDING)], name="farmer_id_index")
    collection.create_index([("centreId", ASCENDING)], name="centre_id_index")
    collection.create_index([("cropCode", ASCENDING)], name="crop_code_index")
    collection.create_index(
        [("performedByEmployeeId", ASCENDING)], name="employee_id_index"
    )
    collection.create_index([("status", ASCENDING)], name="status_index")
    collection.create_index(
        [("performedAt", DESCENDING)], name="performed_at_index"
    )

    try:
        _initialize_weighment_counter_if_needed()
    except PyMongoError:
        pass


def _initialize_weighment_counter_if_needed(session=None) -> None:
    """Initialize the weighmentId counter from existing weighments if not present."""
    counters = counters_collection()
    if counters.find_one({"_id": "weighmentId"}, session=session) is None:
        latest = weighments_collection().find_one(
            projection={"weighmentId": 1},
            sort=[("weighmentId", DESCENDING)],
            session=session,
        )
        current_seq = 0
        if latest and "weighmentId" in latest:
            try:
                current_seq = int(latest["weighmentId"].split("-")[-1])
            except (ValueError, IndexError):
                current_seq = 0
        counters.update_one(
            {"_id": "weighmentId"},
            {"$setOnInsert": {"seq": current_seq}},
            upsert=True,
            session=session,
        )


def _generate_weighment_id(session=None) -> str:
    """Generate the next Weighment ID in sequence (WEIGH-000001, WEIGH-000002, ...) concurrency-safely."""
    _initialize_weighment_counter_if_needed(session=session)
    counter = counters_collection().find_one_and_update(
        {"_id": "weighmentId"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    seq = counter["seq"]
    return f"WEIGH-{seq:06d}"


def _next_attempt_number(lot_id: str, session=None) -> int:
    """Get the next attempt number for a Lot within a transaction."""
    latest = weighments_collection().find_one(
        {"lotId": lot_id},
        projection={"attemptNumber": 1},
        sort=[("attemptNumber", DESCENDING)],
        session=session,
    )
    return (latest["attemptNumber"] if latest and "attemptNumber" in latest else 0) + 1


def _weighment_response(document: dict) -> WeighmentResponse:
    """Convert a MongoDB weighment document into the public response shape."""
    resp_doc = dict(document)
    resp_doc["grossWeightKg"] = _as_decimal(document["grossWeightKg"])
    resp_doc["tareWeightKg"] = _as_decimal(document["tareWeightKg"])
    resp_doc["netWeightKg"] = _as_decimal(document["netWeightKg"])
    return WeighmentResponse.model_validate(resp_doc)


def _validate_weighment_preconditions(
    lot_id: str,
    employee_id: str,
    gross_weight_kg: Decimal,
    tare_weight_kg: Decimal,
    session=None,
) -> tuple[dict, Decimal]:
    """Validate weight values, lot, centre, crop, request, QC existence, and employee."""
    # 1. Weight validations
    gross = _as_decimal(gross_weight_kg)
    tare = _as_decimal(tare_weight_kg)
    if gross.is_nan() or gross.is_infinite() or tare.is_nan() or tare.is_infinite():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Weight values must be finite numbers.",
        )
    if gross <= Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="grossWeightKg must be greater than 0.",
        )
    if tare < Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tareWeightKg cannot be negative.",
        )
    if tare >= gross:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tareWeightKg must be less than grossWeightKg so netWeightKg is greater than 0.",
        )
    net = gross - tare

    database = get_database()

    # 2. Lot validation
    lot = database["lots"].find_one({"lotId": lot_id}, session=session)
    if lot is None:
        lot = database["lots"].find_one({"_id": lot_id}, session=session)
    if lot is None:
        raise HTTPException(status_code=404, detail="Lot not found.")
    if lot.get("status") in ("CANCELLED", "REJECTED", "QC_FAILED"):
        raise HTTPException(
            status_code=409, detail=f"Cannot perform weighment on a {lot.get('status')} lot."
        )

    # 3. Centre validation
    centre = database["centres"].find_one({"_id": lot["centreId"]}, session=session)
    if centre is None:
        raise HTTPException(status_code=404, detail="Centre not found.")
    if centre.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Centre is not ACTIVE.")

    # 4. Crop validation
    crop = database["cropConfigurations"].find_one(
        {"_id": lot["cropCode"]}, session=session
    )
    if crop is None:
        raise HTTPException(status_code=404, detail="Crop configuration not found.")
    if crop.get("status") != "ACTIVE":
        raise HTTPException(
            status_code=400, detail="Crop configuration is not ACTIVE."
        )

    # 5. Linked procurement request validation
    req = database["procurementRequests"].find_one(
        {"_id": lot["requestId"]}, session=session
    )
    if req is None:
        req = database["procurementRequests"].find_one(
            {"requestId": lot["requestId"]}, session=session
        )
    if req is None:
        raise HTTPException(
            status_code=404, detail="Linked procurement request not found."
        )
    if req.get("requestStatus") in ("CANCELLED", "REJECTED", "QC_FAILED"):
        raise HTTPException(
            status_code=409, detail=f"Cannot perform weighment on a {req.get('requestStatus')} request."
        )

    # 6. QC prerequisite: Lot must have at least one recorded QC attempt
    qc = database["qualityChecks"].find_one(
        {"lotId": lot["lotId"]}, projection={"_id": 1}, session=session
    )
    if qc is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="At least one Quality Check (QC) must be recorded for this Lot before weighment.",
        )

    # 7. Employee validation
    employee = database["employees"].find_one(
        {"_id": employee_id}, session=session
    )
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found.")
    if employee.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Employee is not ACTIVE.")
    if employee.get("role") != "WEIGHMENT_OFFICER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee must have the WEIGHMENT_OFFICER role to perform weighment.",
        )
    if employee.get("centreId") != lot["centreId"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee does not belong to the lot's assigned centre.",
        )

    return lot, net


def _create_weighment_transaction(
    session,
    lot_id: str,
    weighment: WeighmentCreate,
    now: datetime,
) -> dict:
    """Execute all precondition checks and record the weighment within a transaction."""
    lot, net_weight_kg = _validate_weighment_preconditions(
        lot_id=lot_id,
        employee_id=weighment.employee_id,
        gross_weight_kg=weighment.gross_weight_kg,
        tare_weight_kg=weighment.tare_weight_kg,
        session=session,
    )

    weighment_id = _generate_weighment_id(session=session)
    attempt_number = _next_attempt_number(lot["lotId"], session=session)
    performed_at = (
        weighment.performed_at if weighment.performed_at is not None else now
    )

    document = {
        "_id": weighment_id,
        "weighmentId": weighment_id,
        "lotId": lot["lotId"],
        "requestId": lot["requestId"],
        "farmerId": lot["farmerId"],
        "centreId": lot["centreId"],
        "cropCode": lot["cropCode"],
        "attemptNumber": attempt_number,
        "grossWeightKg": _as_decimal128(weighment.gross_weight_kg),
        "tareWeightKg": _as_decimal128(weighment.tare_weight_kg),
        "netWeightKg": _as_decimal128(net_weight_kg),
        "performedByEmployeeId": weighment.employee_id,
        "performedAt": performed_at,
        "status": WeighmentStatus.RECORDED.value,
        "deviceId": weighment.device_id,
        "remarks": weighment.remarks,
        "createdAt": now,
        "updatedAt": now,
    }

    weighments_collection().insert_one(document, session=session)
    return document


@router.post(
    "/lots/{lot_id}/weighments",
    response_model=WeighmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_weighment(
    lot_id: LotId,
    weighment: WeighmentCreate,
) -> WeighmentResponse:
    """Record a physical produce weighment attempt on a Lot."""
    now = datetime.now(timezone.utc)

    for attempt in range(3):
        try:
            with mongo_client.start_session() as session:
                document = session.with_transaction(
                    lambda active_session: _create_weighment_transaction(
                        active_session, lot_id, weighment, now
                    )
                )
            return _weighment_response(document)
        except HTTPException:
            raise
        except DuplicateKeyError as error:
            if attempt == 2:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not safely record weighment due to concurrent write conflict. Please retry.",
                ) from error
        except PyMongoError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not record weighment safely. Please retry.",
            ) from error

    raise HTTPException(
        status_code=409, detail="Could not record weighment."
    )


@router.get(
    "/lots/{lot_id}/weighments",
    response_model=list[WeighmentResponse],
)
def list_weighments_for_lot(
    lot_id: LotId,
) -> list[WeighmentResponse]:
    """Retrieve all weighment attempts for a Lot ordered by attemptNumber ascending."""
    try:
        lot = get_database()["lots"].find_one({"lotId": lot_id})
        if lot is None:
            lot = get_database()["lots"].find_one({"_id": lot_id})
        if lot is None:
            raise HTTPException(status_code=404, detail="Lot not found.")

        documents = (
            weighments_collection()
            .find({"lotId": lot["lotId"]})
            .sort("attemptNumber", ASCENDING)
        )
        return [_weighment_response(doc) for doc in documents]
    except HTTPException:
        raise
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while retrieving weighments.",
        ) from error


@router.get(
    "/weighments/{weighment_id}",
    response_model=WeighmentResponse,
)
def get_weighment(
    weighment_id: WeighmentId,
) -> WeighmentResponse:
    """Retrieve one Weighment attempt by ID."""
    try:
        document = weighments_collection().find_one(
            {"weighmentId": weighment_id}
        )
        if document is None:
            document = weighments_collection().find_one(
                {"_id": weighment_id}
            )
        if document is None:
            raise HTTPException(
                status_code=404, detail="Weighment not found."
            )
        return _weighment_response(document)
    except HTTPException:
        raise
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while retrieving weighment.",
        ) from error
