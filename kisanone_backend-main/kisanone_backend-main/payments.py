"""Payment schemas and API endpoints for KisanOne."""

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

router = APIRouter(tags=["Payment"])

PaymentId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique Payment ID.",
    ),
]
ProcurementId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique Government Procurement ID.",
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


class PaymentStatus(str, Enum):
    """Operational states of a farmer payment."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PAID = "PAID"
    FAILED = "FAILED"


class PaymentMethod(str, Enum):
    """Controlled payment disbursement method."""

    BANK_TRANSFER = "BANK_TRANSFER"
    UPI = "UPI"
    CASH = "CASH"
    OTHER = "OTHER"


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


class PaymentCreate(BaseModel):
    """Request body for creating a Payment record for a Government Procurement."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    employee_id: EmployeeId = Field(
        validation_alias=AliasChoices("employeeId", "processedByEmployeeId"),
        alias="employeeId",
        description="ID of the authorized employee creating/initiating the payment record.",
    )
    payment_method: Optional[PaymentMethod] = Field(
        default=None,
        alias="paymentMethod",
        description="Optional payment method if known at initiation.",
    )
    payment_reference: Optional[str] = Field(
        default=None,
        alias="paymentReference",
        max_length=100,
        description="Optional payment reference if known at initiation.",
    )
    initiated_at: Optional[datetime] = Field(
        default=None,
        alias="initiatedAt",
        description="Optional timestamp when payment was initiated. Defaults to current time.",
    )


class PaymentStatusUpdate(BaseModel):
    """Request body for updating the operational status of a payment."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    payment_status: PaymentStatus = Field(
        validation_alias=AliasChoices("paymentStatus", "status"),
        alias="paymentStatus",
        description="Target status for the payment (PROCESSING, PAID, or FAILED).",
    )
    employee_id: EmployeeId = Field(
        validation_alias=AliasChoices("employeeId", "processedByEmployeeId"),
        alias="employeeId",
        description="ID of the authorized employee performing the status update.",
    )
    payment_method: Optional[PaymentMethod] = Field(
        default=None,
        alias="paymentMethod",
        description="Required when transitioning to PAID.",
    )
    payment_reference: Optional[str] = Field(
        default=None,
        alias="paymentReference",
        min_length=1,
        max_length=100,
        description="Required when transitioning to PAID.",
    )
    failure_reason: Optional[str] = Field(
        default=None,
        alias="failureReason",
        max_length=500,
        description="Optional reason explaining why the payment failed.",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        alias="completedAt",
        description="Optional completion timestamp when transitioning to PAID.",
    )


class PaymentResponse(BaseModel):
    """Stored payment record returned by the API."""

    model_config = ConfigDict(populate_by_name=True)

    payment_id: PaymentId = Field(alias="paymentId")
    procurement_id: ProcurementId = Field(alias="procurementId")
    lot_id: str = Field(alias="lotId")
    request_id: str = Field(alias="requestId")
    farmer_id: str = Field(alias="farmerId")
    centre_id: str = Field(alias="centreId")
    crop_code: str = Field(alias="cropCode")

    procurement_quantity_kg: Decimal = Field(alias="procurementQuantityKg")
    price_per_kg: Decimal = Field(alias="pricePerKg")
    payable_amount: Decimal = Field(alias="payableAmount")

    payment_status: PaymentStatus = Field(alias="paymentStatus")

    payment_method: Optional[PaymentMethod] = Field(default=None, alias="paymentMethod")
    payment_reference: Optional[str] = Field(default=None, alias="paymentReference")

    initiated_at: datetime = Field(alias="initiatedAt")
    completed_at: Optional[datetime] = Field(default=None, alias="completedAt")

    processed_by_employee_id: str = Field(alias="processedByEmployeeId")
    failure_reason: Optional[str] = Field(default=None, alias="failureReason")

    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


def payments_collection():
    """Return the shared MongoDB payments collection."""
    return get_database()["payments"]


def counters_collection():
    """Return the shared MongoDB counters collection."""
    return get_database()["counters"]


def ensure_payment_indexes() -> None:
    """Create indexes required by the Payment module."""
    collection = payments_collection()
    collection.create_index(
        "paymentId", unique=True, name="payment_id_unique"
    )
    collection.create_index(
        "procurementId", unique=True, name="payment_procurement_id_unique"
    )
    collection.create_index([("lotId", ASCENDING)], name="payment_lot_id_index")
    collection.create_index([("requestId", ASCENDING)], name="payment_request_id_index")
    collection.create_index([("farmerId", ASCENDING)], name="payment_farmer_id_index")
    collection.create_index([("centreId", ASCENDING)], name="payment_centre_id_index")
    collection.create_index([("cropCode", ASCENDING)], name="payment_crop_code_index")
    collection.create_index([("paymentStatus", ASCENDING)], name="payment_status_index")
    collection.create_index([("paymentMethod", ASCENDING)], name="payment_method_index")
    collection.create_index(
        [("processedByEmployeeId", ASCENDING)], name="payment_processed_by_employee_index"
    )
    collection.create_index(
        [("createdAt", DESCENDING)], name="payment_created_at_index"
    )
    collection.create_index(
        [("completedAt", DESCENDING)], name="payment_completed_at_index"
    )

    try:
        _initialize_payment_counter_if_needed()
    except PyMongoError:
        pass


def _initialize_payment_counter_if_needed(session=None) -> None:
    """Initialize the paymentId counter from existing records if not present."""
    counters = counters_collection()
    if counters.find_one({"_id": "paymentId"}, session=session) is None:
        latest = payments_collection().find_one(
            projection={"paymentId": 1},
            sort=[("paymentId", DESCENDING)],
            session=session,
        )
        current_seq = 0
        if latest and "paymentId" in latest:
            try:
                current_seq = int(latest["paymentId"].split("-")[-1])
            except (ValueError, IndexError):
                current_seq = 0
        counters.update_one(
            {"_id": "paymentId"},
            {"$setOnInsert": {"seq": current_seq}},
            upsert=True,
            session=session,
        )


def _generate_payment_id(session=None) -> str:
    """Generate the next Payment ID in sequence (PAY-000001, PAY-000002, ...) concurrency-safely."""
    _initialize_payment_counter_if_needed(session=session)
    counter = counters_collection().find_one_and_update(
        {"_id": "paymentId"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    seq = counter["seq"]
    return f"PAY-{seq:06d}"


def _payment_response(document: dict) -> PaymentResponse:
    """Convert a MongoDB payment document into the public response shape."""
    resp_doc = dict(document)
    resp_doc["procurementQuantityKg"] = _as_decimal(document["procurementQuantityKg"])
    resp_doc["pricePerKg"] = _as_decimal(document["pricePerKg"])
    resp_doc["payableAmount"] = _as_decimal(document["payableAmount"])
    return PaymentResponse.model_validate(resp_doc)


def _validate_employee(employee_id: str, centre_id: str, session=None) -> dict:
    """Validate that the employee exists, is active, authorized, and matches the centre."""
    database = get_database()
    employee = database["employees"].find_one({"_id": employee_id}, session=session)
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found.")
    if employee.get("status") != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Employee is not ACTIVE."
        )
    if employee.get("role") not in ("PROCUREMENT_OFFICER", "CENTRE_MANAGER"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee must have the PROCUREMENT_OFFICER or CENTRE_MANAGER role to process payments.",
        )
    if employee.get("centreId") != centre_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee does not belong to the procurement's assigned centre.",
        )
    return employee


def _validate_payment_preconditions(
    procurement_id: str,
    employee_id: str,
    session=None,
) -> dict:
    """Validate procurement, lot, farmer, centre, crop, quantities, and employee."""
    database = get_database()

    # 1. Government Procurement validation
    procurement = database["governmentProcurements"].find_one(
        {"procurementId": procurement_id}, session=session
    )
    if procurement is None:
        procurement = database["governmentProcurements"].find_one(
            {"_id": procurement_id}, session=session
        )
    if procurement is None:
        raise HTTPException(status_code=404, detail="Government procurement record not found.")

    if procurement.get("status") != "COMPLETED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot create payment for procurement with status {procurement.get('status')}. Must be COMPLETED.",
        )

    # 2. Check if payment already exists
    existing = payments_collection().find_one(
        {"procurementId": procurement["procurementId"]}, session=session
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A payment record already exists for this Government Procurement.",
        )

    # 3. Linked Lot validation
    lot_id = procurement["lotId"]
    lot = database["lots"].find_one({"lotId": lot_id}, session=session)
    if lot is None:
        lot = database["lots"].find_one({"_id": lot_id}, session=session)
    if lot is None:
        raise HTTPException(status_code=404, detail="Linked Lot not found.")
    if lot.get("status") == "CANCELLED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot create payment for a CANCELLED lot.",
        )

    # 4. Farmer validation
    farmer_id = procurement["farmerId"]
    farmer = database["farmers"].find_one({"_id": farmer_id}, session=session)
    if farmer is None:
        farmer = database["farmers"].find_one({"farmerId": farmer_id}, session=session)
    if farmer is None:
        raise HTTPException(status_code=404, detail="Farmer not found.")

    # 5. Centre validation
    centre_id = procurement["centreId"]
    centre = database["centres"].find_one({"_id": centre_id}, session=session)
    if centre is None:
        raise HTTPException(status_code=404, detail="Centre not found.")
    if centre.get("status") != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Centre is not ACTIVE."
        )

    # 6. Crop validation
    crop_code = procurement["cropCode"]
    crop = database["cropConfigurations"].find_one({"_id": crop_code}, session=session)
    if crop is None:
        raise HTTPException(status_code=404, detail="Crop configuration not found.")
    if crop.get("status") != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Crop configuration is not ACTIVE.",
        )

    # 7. Procurement quantity and gross amount validation
    qty = _as_decimal(procurement["procurementQuantityKg"])
    gross_amount = _as_decimal(procurement["grossAmount"])
    if qty <= Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Procurement quantity must be greater than 0.",
        )
    if gross_amount <= Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Procurement grossAmount must be greater than 0.",
        )

    # 8. Employee validation
    _validate_employee(employee_id, procurement["centreId"], session=session)

    return procurement


def _create_payment_transaction(
    session,
    procurement_id: str,
    payment: PaymentCreate,
    now: datetime,
) -> dict:
    """Validate preconditions and insert initial PENDING payment within a transaction."""
    procurement = _validate_payment_preconditions(
        procurement_id=procurement_id,
        employee_id=payment.employee_id,
        session=session,
    )

    payment_id = _generate_payment_id(session=session)
    initiated_at = payment.initiated_at if payment.initiated_at is not None else now

    document = {
        "_id": payment_id,
        "paymentId": payment_id,
        "procurementId": procurement["procurementId"],
        "lotId": procurement["lotId"],
        "requestId": procurement["requestId"],
        "farmerId": procurement["farmerId"],
        "centreId": procurement["centreId"],
        "cropCode": procurement["cropCode"],
        "procurementQuantityKg": _as_decimal128(procurement["procurementQuantityKg"]),
        "pricePerKg": _as_decimal128(procurement["pricePerKg"]),
        "payableAmount": _as_decimal128(procurement["grossAmount"]),
        "paymentStatus": PaymentStatus.PENDING.value,
        "paymentMethod": payment.payment_method.value if payment.payment_method else None,
        "paymentReference": payment.payment_reference,
        "initiatedAt": initiated_at,
        "completedAt": None,
        "processedByEmployeeId": payment.employee_id,
        "failureReason": None,
        "createdAt": now,
        "updatedAt": now,
    }

    payments_collection().insert_one(document, session=session)
    return document


@router.post(
    "/procurements/{procurement_id}/payment",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_payment(
    procurement_id: ProcurementId,
    payment: PaymentCreate,
) -> PaymentResponse:
    """Record a new Payment record in PENDING status for a completed Government Procurement."""
    now = datetime.now(timezone.utc)

    for attempt in range(3):
        try:
            with mongo_client.start_session() as session:
                document = session.with_transaction(
                    lambda active_session: _create_payment_transaction(
                        active_session, procurement_id, payment, now
                    )
                )
            return _payment_response(document)
        except HTTPException:
            raise
        except DuplicateKeyError as error:
            existing = payments_collection().find_one({"procurementId": procurement_id})
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A payment record already exists for this Government Procurement.",
                ) from error
            if attempt == 2:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not safely record payment due to concurrent write conflict. Please retry.",
                ) from error
        except PyMongoError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not record payment safely. Please retry.",
            ) from error

    raise HTTPException(status_code=409, detail="Could not record payment.")


@router.get(
    "/procurements/{procurement_id}/payment",
    response_model=PaymentResponse,
)
def get_payment_for_procurement(
    procurement_id: ProcurementId,
) -> PaymentResponse:
    """Retrieve the payment record for a Government Procurement."""
    try:
        procurement = get_database()["governmentProcurements"].find_one(
            {"procurementId": procurement_id}
        )
        if procurement is None:
            procurement = get_database()["governmentProcurements"].find_one(
                {"_id": procurement_id}
            )
        if procurement is None:
            raise HTTPException(
                status_code=404, detail="Government procurement record not found."
            )

        document = payments_collection().find_one(
            {"procurementId": procurement["procurementId"]}
        )
        if document is None:
            raise HTTPException(
                status_code=404,
                detail="Payment record not found for this Government Procurement.",
            )
        return _payment_response(document)
    except HTTPException:
        raise
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while retrieving payment record.",
        ) from error


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentResponse,
)
def get_payment(
    payment_id: PaymentId,
) -> PaymentResponse:
    """Retrieve one Payment record by ID."""
    try:
        document = payments_collection().find_one({"paymentId": payment_id})
        if document is None:
            document = payments_collection().find_one({"_id": payment_id})
        if document is None:
            raise HTTPException(status_code=404, detail="Payment record not found.")
        return _payment_response(document)
    except HTTPException:
        raise
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while retrieving payment record.",
        ) from error


@router.patch(
    "/payments/{payment_id}/status",
    response_model=PaymentResponse,
)
def update_payment_status(
    payment_id: PaymentId,
    update: PaymentStatusUpdate,
) -> PaymentResponse:
    """Atomically update the payment status according to allowed transitions."""
    now = datetime.now(timezone.utc)

    # 1. Fetch existing payment
    payment = payments_collection().find_one({"paymentId": payment_id})
    if payment is None:
        payment = payments_collection().find_one({"_id": payment_id})
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment record not found.")

    current_status = payment.get("paymentStatus")
    target_status = update.payment_status

    # 2. Validate state transitions
    if current_status == PaymentStatus.PAID.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment has already been marked PAID and cannot transition to any other status.",
        )
    if current_status == PaymentStatus.FAILED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payment has already FAILED and cannot transition to any other status.",
        )

    # Valid transitions:
    # PENDING -> PROCESSING, FAILED
    # PROCESSING -> PAID, FAILED
    allowed_targets = {
        PaymentStatus.PENDING.value: [PaymentStatus.PROCESSING, PaymentStatus.FAILED],
        PaymentStatus.PROCESSING.value: [PaymentStatus.PAID, PaymentStatus.FAILED],
    }
    valid_targets = allowed_targets.get(current_status, [])
    if target_status not in valid_targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status transition from {current_status} to {target_status.value}.",
        )

    # 3. Validate employee
    _validate_employee(update.employee_id, payment["centreId"])

    # 4. Target status specific requirements
    update_doc = {
        "paymentStatus": target_status.value,
        "processedByEmployeeId": update.employee_id,
        "updatedAt": now,
    }

    if target_status == PaymentStatus.PAID:
        final_method = update.payment_method or payment.get("paymentMethod")
        if not final_method:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="paymentMethod is required when marking a payment as PAID.",
            )
        final_ref = update.payment_reference or payment.get("paymentReference")
        if not final_ref or not str(final_ref).strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="paymentReference is required when marking a payment as PAID.",
            )
        method_str = (
            final_method.value
            if isinstance(final_method, PaymentMethod)
            else str(final_method)
        )
        update_doc["paymentMethod"] = method_str
        update_doc["paymentReference"] = str(final_ref).strip()
        update_doc["completedAt"] = (
            update.completed_at if update.completed_at is not None else now
        )

    elif target_status == PaymentStatus.FAILED:
        if update.failure_reason is not None:
            update_doc["failureReason"] = update.failure_reason

    # 5. Atomic conditional update
    updated_payment = payments_collection().find_one_and_update(
        {"paymentId": payment["paymentId"], "paymentStatus": current_status},
        {"$set": update_doc},
        return_document=ReturnDocument.AFTER,
    )
    if updated_payment is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concurrent status update detected or payment status changed. Please retry.",
        )

    return _payment_response(updated_payment)
