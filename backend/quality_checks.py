"""Quality check schemas and API endpoints for government procurement."""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import math
from typing import Annotated, Any, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from database import get_database, mongo_client

router = APIRouter(tags=["Quality Checks"])

QcAttemptId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique QC Attempt ID.",
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


class QualityCheckStatus(str, Enum):
    """Operational state of a Quality Check attempt."""

    RECORDED = "RECORDED"


class QualityCheckCreate(BaseModel):
    """Request body for recording a Quality Check attempt on a Lot."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    employee_id: EmployeeId = Field(
        validation_alias=AliasChoices("employeeId", "performedByEmployeeId"),
        alias="employeeId",
        description="ID of the QC officer conducting the quality check.",
    )
    tests: dict[str, Any] = Field(
        description="Measured quality test values keyed by testCode."
    )
    performed_at: Optional[datetime] = Field(
        default=None,
        alias="performedAt",
        description="Optional timestamp when the check was performed. Defaults to current time.",
    )


class QualityCheckResponse(BaseModel):
    """Stored QC attempt record returned by the API."""

    model_config = ConfigDict(populate_by_name=True)

    qc_attempt_id: QcAttemptId = Field(alias="qcAttemptId")
    lot_id: LotId = Field(alias="lotId")
    request_id: str = Field(alias="requestId")
    farmer_id: str = Field(alias="farmerId")
    centre_id: str = Field(alias="centreId")
    crop_code: str = Field(alias="cropCode")
    attempt_number: Annotated[int, Field(alias="attemptNumber", gt=0)]
    tests: dict[str, Any]
    performed_by_employee_id: str = Field(alias="performedByEmployeeId")
    performed_at: datetime = Field(alias="performedAt")
    status: QualityCheckStatus
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


def quality_checks_collection():
    """Return the shared MongoDB qualityChecks collection."""
    return get_database()["qualityChecks"]


def counters_collection():
    """Return the shared MongoDB counters collection."""
    return get_database()["counters"]


def ensure_quality_check_indexes() -> None:
    """Create indexes required by the Quality Check module."""
    collection = quality_checks_collection()
    collection.create_index(
        "qcAttemptId", unique=True, name="qc_attempt_id_unique"
    )
    collection.create_index(
        [("lotId", ASCENDING), ("attemptNumber", ASCENDING)],
        unique=True,
        name="lot_attempt_unique",
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
        _initialize_qc_counter_if_needed()
    except PyMongoError:
        pass


def _initialize_qc_counter_if_needed(session=None) -> None:
    """Initialize the qcAttemptId counter from existing QC attempts if not present."""
    counters = counters_collection()
    if counters.find_one({"_id": "qcAttemptId"}, session=session) is None:
        latest = quality_checks_collection().find_one(
            projection={"qcAttemptId": 1},
            sort=[("qcAttemptId", DESCENDING)],
            session=session,
        )
        current_seq = 0
        if latest and "qcAttemptId" in latest:
            try:
                current_seq = int(latest["qcAttemptId"].split("-")[-1])
            except (ValueError, IndexError):
                current_seq = 0
        counters.update_one(
            {"_id": "qcAttemptId"},
            {"$setOnInsert": {"seq": current_seq}},
            upsert=True,
            session=session,
        )


def _generate_qc_attempt_id(session=None) -> str:
    """Generate the next QC Attempt ID in sequence (QC-000001, QC-000002, ...) concurrency-safely."""
    _initialize_qc_counter_if_needed(session=session)
    counter = counters_collection().find_one_and_update(
        {"_id": "qcAttemptId"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    seq = counter["seq"]
    return f"QC-{seq:06d}"


def _next_attempt_number(lot_id: str, session=None) -> int:
    """Get the next attempt number for a Lot within a transaction."""
    latest = quality_checks_collection().find_one(
        {"lotId": lot_id},
        projection={"attemptNumber": 1},
        sort=[("attemptNumber", DESCENDING)],
        session=session,
    )
    return (latest["attemptNumber"] if latest and "attemptNumber" in latest else 0) + 1


def _qc_response(document: dict) -> QualityCheckResponse:
    """Convert a MongoDB QC document into the public response shape."""
    return QualityCheckResponse.model_validate(document)


def _validate_qc_preconditions(
    lot_id: str,
    employee_id: str,
    submitted_tests: dict[str, Any],
    session=None,
) -> tuple[dict, dict, dict]:
    """Validate lot, employee, crop configuration, and submitted tests."""
    database = get_database()

    # 1. Lot validation
    lot = database["lots"].find_one({"lotId": lot_id}, session=session)
    if lot is None:
        lot = database["lots"].find_one({"_id": lot_id}, session=session)
    if lot is None:
        raise HTTPException(status_code=404, detail="Lot not found.")
    if lot.get("status") == "CANCELLED":
        raise HTTPException(
            status_code=409, detail="Cannot record QC for a CANCELLED lot."
        )

    # 2. Centre validation
    centre = database["centres"].find_one({"_id": lot["centreId"]}, session=session)
    if centre is None:
        raise HTTPException(status_code=404, detail="Centre not found.")
    if centre.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Centre is not ACTIVE.")

    # 3. Employee validation
    employee = database["employees"].find_one(
        {"_id": employee_id}, session=session
    )
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found.")
    if employee.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Employee is not ACTIVE.")
    if employee.get("role") != "QC_OFFICER":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee must have the QC_OFFICER role to perform QC.",
        )
    if employee.get("centreId") != lot["centreId"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee does not belong to the lot's assigned centre.",
        )

    # 4. Crop configuration validation
    crop = database["cropConfigurations"].find_one(
        {"_id": lot["cropCode"]}, session=session
    )
    if crop is None:
        raise HTTPException(status_code=404, detail="Crop configuration not found.")
    if crop.get("status") != "ACTIVE":
        raise HTTPException(
            status_code=400, detail="Crop configuration is not ACTIVE."
        )

    # 5. Validate submitted tests against crop's qualityTests
    quality_tests = crop.get("qualityTests", [])
    configured_tests = {t["testCode"]: t for t in quality_tests}

    # Reject unknown testCodes
    for test_code in submitted_tests:
        if test_code not in configured_tests:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown testCode '{test_code}' for crop '{lot['cropCode']}'.",
            )

    # Validate required tests
    for test_code, test_def in configured_tests.items():
        if test_def.get("required"):
            if test_code not in submitted_tests or submitted_tests[test_code] is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required quality test '{test_code}'.",
                )

    # Validate data types
    for test_code, value in submitted_tests.items():
        test_def = configured_tests[test_code]
        expected_type = test_def.get("dataType")
        if expected_type == "NUMBER":
            if isinstance(value, bool) or not isinstance(
                value, (int, float, Decimal)
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Test '{test_code}' requires a NUMBER value.",
                )
            if isinstance(value, float) and (
                math.isnan(value) or math.isinf(value)
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Test '{test_code}' must be a finite numeric value.",
                )
        elif expected_type == "BOOLEAN":
            if not isinstance(value, bool):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Test '{test_code}' requires a BOOLEAN value.",
                )
        elif expected_type == "TEXT":
            if not isinstance(value, str):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Test '{test_code}' requires a TEXT value.",
                )

    return lot, employee, crop


def _create_quality_check_transaction(
    session,
    lot_id: str,
    check: QualityCheckCreate,
    now: datetime,
) -> dict:
    """Execute all precondition checks and create the QC attempt document within a transaction."""
    lot, employee, crop = _validate_qc_preconditions(
        lot_id=lot_id,
        employee_id=check.employee_id,
        submitted_tests=check.tests,
        session=session,
    )

    qc_attempt_id = _generate_qc_attempt_id(session=session)
    attempt_number = _next_attempt_number(lot["lotId"], session=session)
    performed_at = check.performed_at if check.performed_at is not None else now

    qc_document = {
        "_id": qc_attempt_id,
        "qcAttemptId": qc_attempt_id,
        "lotId": lot["lotId"],
        "requestId": lot["requestId"],
        "farmerId": lot["farmerId"],
        "centreId": lot["centreId"],
        "cropCode": lot["cropCode"],
        "attemptNumber": attempt_number,
        "tests": check.tests,
        "performedByEmployeeId": check.employee_id,
        "performedAt": performed_at,
        "status": QualityCheckStatus.RECORDED.value,
        "createdAt": now,
        "updatedAt": now,
    }

    quality_checks_collection().insert_one(qc_document, session=session)
    return qc_document


@router.post(
    "/lots/{lot_id}/quality-checks",
    response_model=QualityCheckResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_quality_check(
    lot_id: LotId,
    check: QualityCheckCreate,
) -> QualityCheckResponse:
    """Record a Quality Check attempt on a Lot."""
    now = datetime.now(timezone.utc)

    for attempt in range(3):
        try:
            with mongo_client.start_session() as session:
                document = session.with_transaction(
                    lambda active_session: _create_quality_check_transaction(
                        active_session, lot_id, check, now
                    )
                )
            return _qc_response(document)
        except HTTPException:
            raise
        except DuplicateKeyError as error:
            if attempt == 2:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not safely record QC attempt due to concurrent write conflict. Please retry.",
                ) from error
        except PyMongoError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Could not record quality check safely. Please retry.",
            ) from error

    raise HTTPException(
        status_code=409, detail="Could not record quality check."
    )


@router.get(
    "/lots/{lot_id}/quality-checks",
    response_model=list[QualityCheckResponse],
)
def list_quality_checks_for_lot(
    lot_id: LotId,
) -> list[QualityCheckResponse]:
    """Retrieve all QC attempts for a Lot ordered by attemptNumber ascending."""
    try:
        lot = get_database()["lots"].find_one({"lotId": lot_id})
        if lot is None:
            lot = get_database()["lots"].find_one({"_id": lot_id})
        if lot is None:
            raise HTTPException(status_code=404, detail="Lot not found.")

        documents = (
            quality_checks_collection()
            .find({"lotId": lot["lotId"]})
            .sort("attemptNumber", ASCENDING)
        )
        return [_qc_response(doc) for doc in documents]
    except HTTPException:
        raise
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while retrieving quality checks.",
        ) from error


@router.get(
    "/quality-checks/{qc_attempt_id}",
    response_model=QualityCheckResponse,
)
def get_quality_check(
    qc_attempt_id: QcAttemptId,
) -> QualityCheckResponse:
    """Retrieve one Quality Check attempt by ID."""
    try:
        document = quality_checks_collection().find_one(
            {"qcAttemptId": qc_attempt_id}
        )
        if document is None:
            document = quality_checks_collection().find_one(
                {"_id": qc_attempt_id}
            )
        if document is None:
            raise HTTPException(
                status_code=404, detail="Quality check not found."
            )
        return _qc_response(document)
    except HTTPException:
        raise
    except PyMongoError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database error while retrieving quality check.",
        ) from error
