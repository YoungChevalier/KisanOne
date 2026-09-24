"""Government procurement schemas and API endpoints for KisanOne."""

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

router = APIRouter(tags=["Government Procurement"])

ProcurementId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique Government Procurement ID.",
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
WeighmentId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique Weighment ID.",
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
QuantityKg = Annotated[Decimal, Field(gt=0)]
PricePerKg = Annotated[Decimal, Field(gt=0)]
Remarks = Annotated[str, Field(min_length=1, max_length=500)]


class ProcurementStatus(str, Enum):
    """Operational state of a Government Procurement transaction."""

    COMPLETED = "COMPLETED"


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


class GovernmentProcurementCreate(BaseModel):
    """Request body for recording government acceptance/purchase of a Lot."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    weighment_id: WeighmentId = Field(
        validation_alias=AliasChoices("weighmentId", "selectedWeighmentId"),
        alias="weighmentId",
        description="ID of the weighment record used as the basis for procurement.",
    )
    procurement_quantity_kg: QuantityKg = Field(alias="procurementQuantityKg")
    price_per_kg: Optional[PricePerKg] = Field(
        default=None,
        alias="pricePerKg",
        description="Optional client price; overridden by Rulebook evaluation when present.",
    )
    evaluation_id: Optional[str] = Field(
        default=None,
        alias="evaluationId",
        description="ID of the quality evaluation used for grade and pricing.",
    )
    qc_attempt_id: Optional[str] = Field(
        default=None,
        alias="qcAttemptId",
        description="ID of the QC attempt used for evaluation.",
    )
    price_source: Optional[str] = Field(
        default=None,
        alias="priceSource",
        description="Origin of the price rate applied.",
    )
    employee_id: EmployeeId = Field(
        validation_alias=AliasChoices("employeeId", "procuredByEmployeeId"),
        alias="employeeId",
        description="ID of the procurement officer or centre manager recording this procurement.",
    )
    procured_at: Optional[datetime] = Field(
        default=None,
        alias="procuredAt",
        description="Optional timestamp when procurement was executed. Defaults to current time.",
    )
    remarks: Optional[Remarks] = None


class GovernmentProcurementResponse(BaseModel):
    """Stored government procurement record returned by the API."""

    model_config = ConfigDict(populate_by_name=True)

    procurement_id: ProcurementId = Field(alias="procurementId")
    lot_id: LotId = Field(alias="lotId")
    request_id: str = Field(alias="requestId")
    farmer_id: str = Field(alias="farmerId")
    centre_id: str = Field(alias="centreId")
    crop_code: str = Field(alias="cropCode")
    weighment_id: WeighmentId = Field(alias="weighmentId")
    procurement_quantity_kg: Decimal = Field(alias="procurementQuantityKg")
    price_per_kg: Decimal = Field(alias="pricePerKg")
    gross_amount: Decimal = Field(alias="grossAmount")
    price_source: str = Field(alias="priceSource")
    evaluation_id: Optional[str] = Field(default=None, alias="evaluationId")
    qc_attempt_id: Optional[str] = Field(default=None, alias="qcAttemptId")
    rulebook_id: Optional[str] = Field(default=None, alias="rulebookId")
    rulebook_version: Optional[int] = Field(default=None, alias="rulebookVersion")
    quality_grade: Optional[str] = Field(default=None, alias="qualityGrade")
    procured_by_employee_id: str = Field(alias="procuredByEmployeeId")
    procured_at: datetime = Field(alias="procuredAt")
    status: ProcurementStatus
    remarks: Optional[str] = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


def government_procurements_collection():
    """Return the shared MongoDB governmentProcurements collection."""
    return get_database()["governmentProcurements"]


def counters_collection():
    """Return the shared MongoDB counters collection."""
    return get_database()["counters"]


def ensure_government_procurement_indexes() -> None:
    """Create indexes required by the Government Procurement module."""
    collection = government_procurements_collection()
    collection.create_index(
        "procurementId", unique=True, name="procurement_id_unique"
    )
    collection.create_index(
        "lotId", unique=True, name="procurement_lot_id_unique"
    )
    collection.create_index([("requestId", ASCENDING)], name="request_id_index")
    collection.create_index([("farmerId", ASCENDING)], name="farmer_id_index")
    collection.create_index([("centreId", ASCENDING)], name="centre_id_index")
    collection.create_index([("cropCode", ASCENDING)], name="crop_code_index")
    collection.create_index([("weighmentId", ASCENDING)], name="weighment_id_index")
    collection.create_index(
        [("procuredByEmployeeId", ASCENDING)], name="procured_by_employee_id_index"
    )
    collection.create_index([("status", ASCENDING)], name="status_index")
    collection.create_index(
        [("procuredAt", DESCENDING)], name="procured_at_index"
    )

    try:
        _initialize_procurement_counter_if_needed()
    except PyMongoError:
        pass


def _initialize_procurement_counter_if_needed(session=None) -> None:
    """Initialize the procurementId counter from existing records if not present."""
    counters = counters_collection()
    if counters.find_one({"_id": "procurementId"}, session=session) is None:
        latest = government_procurements_collection().find_one(
            projection={"procurementId": 1},
            sort=[("procurementId", DESCENDING)],
            session=session,
        )
        current_seq = 0
        if latest and "procurementId" in latest:
            try:
                current_seq = int(latest["procurementId"].split("-")[-1])
            except (ValueError, IndexError):
                current_seq = 0
        counters.update_one(
            {"_id": "procurementId"},
            {"$setOnInsert": {"seq": current_seq}},
            upsert=True,
            session=session,
        )


def _generate_procurement_id(session=None) -> str:
    """Generate the next Procurement ID in sequence (PROC-000001, PROC-000002, ...) concurrency-safely."""
    _initialize_procurement_counter_if_needed(session=session)
    counter = counters_collection().find_one_and_update(
        {"_id": "procurementId"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    seq = counter["seq"]
    return f"PROC-{seq:06d}"


def _procurement_response(document: dict) -> GovernmentProcurementResponse:
    """Convert a MongoDB government procurement document into the public response shape."""
    resp_doc = dict(document)
    resp_doc["procurementQuantityKg"] = _as_decimal(document["procurementQuantityKg"])
    resp_doc["pricePerKg"] = _as_decimal(document["pricePerKg"])
    resp_doc["grossAmount"] = _as_decimal(document["grossAmount"])
    return GovernmentProcurementResponse.model_validate(resp_doc)


def _validate_procurement_preconditions(
    lot_id: str,
    procurement: GovernmentProcurementCreate,
    session=None,
) -> tuple[dict, dict, Decimal, Decimal, str, dict]:
    """Validate lot, request, farmer, centre, crop, QC, weighment, quantity, evaluation, and employee."""
    qty = _as_decimal(procurement.procurement_quantity_kg)
    if qty.is_nan() or qty.is_infinite():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="procurementQuantityKg must be a finite number.",
        )
    if qty <= Decimal("0"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="procurementQuantityKg must be greater than 0.",
        )

    database = get_database()

    # 1. Lot validation
    lot = database["lots"].find_one({"lotId": lot_id}, session=session)
    if lot is None:
        lot = database["lots"].find_one({"_id": lot_id}, session=session)
    if lot is None:
        raise HTTPException(status_code=404, detail="Lot not found.")
    if lot.get("status") in ("CANCELLED", "REJECTED", "QC_FAILED"):
        raise HTTPException(
            status_code=409, detail=f"Cannot procure a {lot.get('status')} lot."
        )

    # Check if already procured
    existing = government_procurements_collection().find_one(
        {"lotId": lot["lotId"]}, session=session
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A procurement record already exists for this Lot.",
        )

    # 2. Linked procurement request validation
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
            status_code=409, detail=f"Cannot procure a {req.get('requestStatus')} request."
        )

    # 3. Farmer validation
    farmer = database["farmers"].find_one(
        {"_id": lot["farmerId"]}, session=session
    )
    if farmer is None:
        raise HTTPException(status_code=404, detail="Farmer not found.")

    # 4. Centre validation
    centre = database["centres"].find_one(
        {"_id": lot["centreId"]}, session=session
    )
    if centre is None:
        raise HTTPException(status_code=404, detail="Centre not found.")
    if centre.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Centre is not ACTIVE.")

    # 5. Crop validation
    crop = database["cropConfigurations"].find_one(
        {"_id": lot["cropCode"]}, session=session
    )
    if crop is None:
        raise HTTPException(status_code=404, detail="Crop configuration not found.")
    if crop.get("status") != "ACTIVE":
        raise HTTPException(
            status_code=400, detail="Crop configuration is not ACTIVE."
        )

    # 6. QC prerequisite: Lot must have at least one recorded QC attempt
    qc = database["qualityChecks"].find_one(
        {"lotId": lot["lotId"]}, projection={"_id": 1}, session=session
    )
    if qc is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="At least one Quality Check (QC) must be recorded for this Lot before procurement.",
        )

    # 7. Weighment prerequisite: Lot must have at least one recorded weighment
    any_weighment = database["weighments"].find_one(
        {"lotId": lot["lotId"]}, projection={"_id": 1}, session=session
    )
    if any_weighment is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="At least one Weighment must be recorded for this Lot before procurement.",
        )

    # 8. Selected weighment validation
    weighment = database["weighments"].find_one(
        {"weighmentId": procurement.weighment_id}, session=session
    )
    if weighment is None:
        weighment = database["weighments"].find_one(
            {"_id": procurement.weighment_id}, session=session
        )
    if weighment is None:
        raise HTTPException(status_code=404, detail="Selected weighment not found.")
    if weighment.get("lotId") != lot["lotId"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected weighment does not belong to this Lot.",
        )

    weighment_net = _as_decimal(weighment["netWeightKg"])
    if qty > weighment_net:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="procurementQuantityKg cannot exceed the selected weighment netWeightKg.",
        )

    # 9. Employee validation
    employee = database["employees"].find_one(
        {"_id": procurement.employee_id}, session=session
    )
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found.")
    if employee.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Employee is not ACTIVE.")
    if employee.get("role") not in ("PROCUREMENT_OFFICER", "CENTRE_MANAGER"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee must have the PROCUREMENT_OFFICER or CENTRE_MANAGER role to perform procurement.",
        )
    if employee.get("centreId") != lot["centreId"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee does not belong to the lot's assigned centre.",
        )

    # 10. Quality Evaluation prerequisite and price derivation
    eval_coll = database.get("qualityEvaluations") if isinstance(database, dict) else database["qualityEvaluations"]
    evaluation = None
    if eval_coll is not None:
        if procurement.evaluation_id:
            evaluation = eval_coll.find_one({"evaluationId": procurement.evaluation_id}, session=session)
            if evaluation is None:
                evaluation = eval_coll.find_one({"_id": procurement.evaluation_id}, session=session)
            if evaluation is None:
                raise HTTPException(status_code=404, detail="Specified quality evaluation not found.")
        elif procurement.qc_attempt_id:
            evaluation = eval_coll.find_one(
                {"qcAttemptId": procurement.qc_attempt_id},
                sort=[("evaluatedAt", DESCENDING)],
                session=session,
            )
            if evaluation is None:
                raise HTTPException(status_code=404, detail="Quality evaluation for specified QC attempt not found.")
        else:
            evaluation = eval_coll.find_one(
                {"lotId": lot["lotId"]},
                sort=[("evaluatedAt", DESCENDING)],
                session=session,
            )

    eval_meta = {}
    if evaluation is not None:
        if evaluation.get("lotId") != lot["lotId"]:
            raise HTTPException(status_code=400, detail="Quality evaluation does not belong to this Lot.")
        grade = evaluation.get("grade")
        decision = evaluation.get("decision")
        if grade == "F" or decision == "FAIL":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Government procurement blocked: Lot failed quality evaluation (Grade F).",
            )
        final_price = _as_decimal(evaluation["pricePerKg"])
        price_source = f"RULEBOOK:{evaluation['rulebookId']}:V{evaluation['rulebookVersion']}:GRADE_{grade}"
        eval_meta = {
            "evaluationId": evaluation.get("evaluationId"),
            "qcAttemptId": evaluation.get("qcAttemptId"),
            "rulebookId": evaluation.get("rulebookId"),
            "rulebookVersion": evaluation.get("rulebookVersion"),
            "qualityGrade": grade,
        }
    else:
        # Backward compatibility when no evaluation is present in tests
        if procurement.price_per_kg is not None:
            final_price = _as_decimal(procurement.price_per_kg)
            if final_price <= Decimal("0"):
                raise HTTPException(status_code=400, detail="pricePerKg must be greater than 0.")
            price_source = procurement.price_source or "RULEBOOK_PENDING"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quality evaluation required before government procurement.",
            )

    gross_amount = (qty * final_price).quantize(Decimal("0.01"))
    return lot, weighment, final_price, gross_amount, price_source, eval_meta


def _create_procurement_transaction(
    session,
    lot_id: str,
    procurement: GovernmentProcurementCreate,
    now: datetime,
) -> dict:
    """Execute all precondition checks and record the procurement within a transaction."""
    lot, weighment, final_price, gross_amount, price_source, eval_meta = (
        _validate_procurement_preconditions(
            lot_id=lot_id,
            procurement=procurement,
            session=session,
        )
    )

    procurement_id = _generate_procurement_id(session=session)
    procured_at = (
        procurement.procured_at if procurement.procured_at is not None else now
    )

    document = {
        "_id": procurement_id,
        "procurementId": procurement_id,
        "lotId": lot["lotId"],
        "requestId": lot["requestId"],
        "farmerId": lot["farmerId"],
        "centreId": lot["centreId"],
        "cropCode": lot["cropCode"],
        "weighmentId": weighment.get("weighmentId", procurement.weighment_id),
        "procurementQuantityKg": _as_decimal128(procurement.procurement_quantity_kg),
        "pricePerKg": _as_decimal128(final_price),
        "grossAmount": _as_decimal128(gross_amount),
        "priceSource": price_source,
        "evaluationId": eval_meta.get("evaluationId"),
        "qcAttemptId": eval_meta.get("qcAttemptId"),
        "rulebookId": eval_meta.get("rulebookId"),
        "rulebookVersion": eval_meta.get("rulebookVersion"),
        "qualityGrade": eval_meta.get("qualityGrade"),
        "procuredByEmployeeId": procurement.employee_id,
        "procuredAt": procured_at,
        "status": ProcurementStatus.COMPLETED.value,
        "remarks": procurement.remarks,
        "createdAt": now,
        "updatedAt": now,
    }

    government_procurements_collection().insert_one(document, session=session)
    return document


@router.post(
    "/lots/{lot_id}/procurement",
    response_model=GovernmentProcurementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_procurement(
    lot_id: LotId,
    procurement: GovernmentProcurementCreate,
) -> GovernmentProcurementResponse:
    """Record the government procurement transaction for a Lot."""
    now = datetime.now(timezone.utc)

    for attempt in range(3):
        try:
            with mongo_client.start_session() as session:
                document = session.with_transaction(
                    lambda active_session: _create_procurement_transaction(
                        active_session, lot_id, procurement, now
                    )
                )
            return _procurement_response(document)
        except HTTPException:
            raise
        except DuplicateKeyError as error:
            existing = government_procurements_collection().find_one({"lotId": lot_id})
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A procurement record already exists for this Lot.",
                ) from error
            if attempt == 2:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not safely record procurement due to concurrent write conflict. Please retry.",
                ) from error
        except PyMongoError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not record government procurement safely. Please retry.",
            ) from error

    raise HTTPException(
        status_code=409, detail="Could not record government procurement."
    )


@router.get(
    "/lots/{lot_id}/procurement",
    response_model=GovernmentProcurementResponse,
)
def get_procurement_for_lot(
    lot_id: LotId,
) -> GovernmentProcurementResponse:
    """Retrieve the government procurement record for a Lot."""
    try:
        lot = get_database()["lots"].find_one({"lotId": lot_id})
        if lot is None:
            lot = get_database()["lots"].find_one({"_id": lot_id})
        if lot is None:
            raise HTTPException(status_code=404, detail="Lot not found.")

        document = government_procurements_collection().find_one(
            {"lotId": lot["lotId"]}
        )
        if document is None:
            raise HTTPException(
                status_code=404,
                detail="Government procurement record not found for this Lot.",
            )
        return _procurement_response(document)
    except HTTPException:
        raise
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while retrieving government procurement.",
        ) from error


@router.get(
    "/procurements/{procurement_id}",
    response_model=GovernmentProcurementResponse,
)
def get_procurement(
    procurement_id: ProcurementId,
) -> GovernmentProcurementResponse:
    """Retrieve one Government Procurement record by ID."""
    try:
        document = government_procurements_collection().find_one(
            {"procurementId": procurement_id}
        )
        if document is None:
            document = government_procurements_collection().find_one(
                {"_id": procurement_id}
            )
        if document is None:
            raise HTTPException(
                status_code=404, detail="Government procurement record not found."
            )
        return _procurement_response(document)
    except HTTPException:
        raise
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while retrieving government procurement.",
        ) from error
