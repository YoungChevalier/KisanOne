"""Government procurement centre employee schemas and API endpoints."""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

from database import get_database

router = APIRouter(prefix="/employees", tags=["Employees"])

EmployeeId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique employee ID.",
    ),
]
CentreId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="ID of the procurement centre to which the worker is assigned.",
    ),
]
PhoneNumber = Annotated[
    str,
    Field(
        min_length=7,
        max_length=20,
        pattern=r"^[0-9+() -]+$",
        description="Employee contact phone number.",
    ),
]


class EmployeeRole(str, Enum):
    """Operational roles supported at government procurement centres."""

    GATE_OPERATOR = "GATE_OPERATOR"
    QC_OFFICER = "QC_OFFICER"
    WEIGHMENT_OFFICER = "WEIGHMENT_OFFICER"
    PROCUREMENT_OFFICER = "PROCUREMENT_OFFICER"
    CENTRE_MANAGER = "CENTRE_MANAGER"
    GOVERNMENT_OFFICER = "GOVERNMENT_OFFICER"


class EmployeeStatus(str, Enum):
    """Employment assignment status."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class EmployeeProfile(BaseModel):
    """Current operational assignment and contact data for an employee."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=100)]
    phone: PhoneNumber
    role: EmployeeRole
    centre_id: CentreId = Field(alias="centreId")
    status: EmployeeStatus


class EmployeeCreate(EmployeeProfile):
    """Request body for registering a procurement-centre employee."""

    employee_id: EmployeeId = Field(alias="employeeId")

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "employeeId": "EMP-001",
                "name": "Ravi Kumar",
                "phone": "+919876543210",
                "role": "QC_OFFICER",
                "centreId": "CENTRE-001",
                "status": "ACTIVE",
            }
        },
    )


class EmployeeUpdate(BaseModel):
    """Fields that may be changed without changing the employee ID."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    name: Annotated[Optional[str], Field(min_length=1, max_length=100)] = None
    phone: Optional[PhoneNumber] = None
    role: Optional[EmployeeRole] = None
    centre_id: Optional[CentreId] = Field(default=None, alias="centreId")
    status: Optional[EmployeeStatus] = None


class EmployeeResponse(EmployeeProfile):
    """Employee record returned by the API."""

    employee_id: EmployeeId = Field(alias="employeeId")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


def employees_collection():
    """Return the shared MongoDB employees collection."""
    return get_database()["employees"]


def ensure_employee_indexes() -> None:
    """Create indexes required by the Employee module if they do not exist."""
    collection = employees_collection()
    collection.create_index("employeeId", unique=True, name="employee_id_unique")
    collection.create_index([("centreId", ASCENDING)], name="centre_id_index")
    collection.create_index([("role", ASCENDING)], name="role_index")


def _employee_response(document: dict) -> EmployeeResponse:
    """Convert a MongoDB employee document into the public response shape."""
    return EmployeeResponse.model_validate(document)


def _validate_active_centre(centre_id: str) -> None:
    """Ensure each employee assignment points to an active real centre."""
    centre = get_database()["centres"].find_one({"_id": centre_id})
    if centre is None:
        raise HTTPException(status_code=404, detail="Centre not found.")
    if centre.get("status") != "ACTIVE":
        raise HTTPException(status_code=400, detail="Employees can only be assigned to an ACTIVE centre.")


@router.post("", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
def create_employee(employee: EmployeeCreate) -> EmployeeResponse:
    """Register an employee assigned to one procurement centre."""
    _validate_active_centre(employee.centre_id)
    document = employee.model_dump(by_alias=True)
    now = datetime.now(timezone.utc)
    document["_id"] = document["employeeId"]
    document["createdAt"] = now
    document["updatedAt"] = now

    try:
        employees_collection().insert_one(document)
    except DuplicateKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An employee with this employeeId already exists.",
        ) from error

    return _employee_response(document)


@router.get("", response_model=list[EmployeeResponse])
def list_employees(skip: int = 0, limit: int = 100) -> list[EmployeeResponse]:
    """List employees for development and testing."""
    if skip < 0:
        raise HTTPException(status_code=400, detail="skip must be zero or greater.")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100.")

    documents = employees_collection().find().skip(skip).limit(limit)
    return [_employee_response(document) for document in documents]


@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(employee_id: EmployeeId) -> EmployeeResponse:
    """Get one employee by employee ID."""
    document = employees_collection().find_one({"_id": employee_id})
    if document is None:
        raise HTTPException(status_code=404, detail="Employee not found.")

    return _employee_response(document)


@router.patch("/{employee_id}", response_model=EmployeeResponse)
def update_employee(
    employee_id: EmployeeId,
    employee: EmployeeUpdate,
) -> EmployeeResponse:
    """Update an employee's profile or single-centre assignment."""
    updates = employee.model_dump(by_alias=True, exclude_unset=True, exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="Provide at least one employee field to update.")
    if "centreId" in updates:
        _validate_active_centre(updates["centreId"])

    updates["updatedAt"] = datetime.now(timezone.utc)
    document = employees_collection().find_one_and_update(
        {"_id": employee_id},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Employee not found.")

    return _employee_response(document)
