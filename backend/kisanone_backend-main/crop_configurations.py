"""Crop quality-test configuration schemas and API endpoints."""

from enum import Enum
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from database import get_database

router = APIRouter(prefix="/crop-configurations", tags=["Crop Configurations"])

CropCode = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Application-owned unique crop code.",
    ),
]
TestCode = Annotated[
    str,
    Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Unique test code within this crop configuration.",
    ),
]


class CropConfigurationStatus(str, Enum):
    """Availability of a crop configuration for future procurement workflows."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class QualityTestDataType(str, Enum):
    """The type of value a future quality-test workflow will collect."""

    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    TEXT = "TEXT"


class QualityTest(BaseModel):
    """One quality test or measurement defined for a crop."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    test_code: TestCode = Field(alias="testCode")
    test_name: Annotated[str, Field(alias="testName", min_length=1, max_length=150)]
    unit: Optional[Annotated[str, Field(min_length=1, max_length=30)]] = None
    data_type: QualityTestDataType = Field(alias="dataType")
    required: bool
    description: Annotated[str, Field(min_length=1, max_length=500)]


class CropConfigurationCreate(BaseModel):
    """Request body for creating a crop quality-test configuration."""

    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "cropCode": "PADDY_RICE",
                "cropName": "Paddy / Rice",
                "status": "ACTIVE",
                "qualityTests": [
                    {
                        "testCode": "MOISTURE_PERCENT",
                        "testName": "Moisture %",
                        "unit": "%",
                        "dataType": "NUMBER",
                        "required": True,
                        "description": "Moisture percentage measurement.",
                    }
                ],
            }
        },
    )

    crop_code: CropCode = Field(alias="cropCode")
    crop_name: Annotated[str, Field(alias="cropName", min_length=1, max_length=100)]
    status: CropConfigurationStatus
    quality_tests: Annotated[
        list[QualityTest], Field(alias="qualityTests", min_length=1, max_length=50)
    ]


class CropConfigurationUpdate(BaseModel):
    """Fields that may be changed without changing the crop code."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    crop_name: Annotated[
        Optional[str], Field(alias="cropName", min_length=1, max_length=100)
    ] = None
    status: Optional[CropConfigurationStatus] = None
    quality_tests: Annotated[
        Optional[list[QualityTest]], Field(alias="qualityTests", min_length=1, max_length=50)
    ] = None


class CropConfigurationResponse(CropConfigurationCreate):
    """Crop quality-test configuration returned by the API."""


def crop_configurations_collection():
    """Return the shared MongoDB cropConfigurations collection."""
    return get_database()["cropConfigurations"]


def ensure_crop_configuration_indexes() -> None:
    """Create the crop code index if it does not already exist."""
    crop_configurations_collection().create_index(
        "cropCode", unique=True, name="crop_code_unique"
    )


def _crop_configuration_response(document: dict) -> CropConfigurationResponse:
    """Convert a MongoDB crop configuration into the public response shape."""
    return CropConfigurationResponse.model_validate(document)


@router.post(
    "", response_model=CropConfigurationResponse, status_code=status.HTTP_201_CREATED
)
def create_crop_configuration(
    configuration: CropConfigurationCreate,
) -> CropConfigurationResponse:
    """Create a crop's quality-test configuration without any decision rules."""
    document = configuration.model_dump(by_alias=True)
    document["_id"] = document["cropCode"]

    try:
        crop_configurations_collection().insert_one(document)
    except DuplicateKeyError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A crop configuration with this cropCode already exists.",
        ) from error

    return _crop_configuration_response(document)


@router.get("", response_model=list[CropConfigurationResponse])
def list_crop_configurations(
    skip: int = 0, limit: int = 100
) -> list[CropConfigurationResponse]:
    """List crop quality-test configurations for development and testing."""
    if skip < 0:
        raise HTTPException(status_code=400, detail="skip must be zero or greater.")
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 100.")

    documents = crop_configurations_collection().find().skip(skip).limit(limit)
    return [_crop_configuration_response(document) for document in documents]


@router.get("/{crop_code}", response_model=CropConfigurationResponse)
def get_crop_configuration(crop_code: CropCode) -> CropConfigurationResponse:
    """Get one crop configuration by crop code."""
    document = crop_configurations_collection().find_one({"_id": crop_code})
    if document is None:
        raise HTTPException(status_code=404, detail="Crop configuration not found.")

    return _crop_configuration_response(document)


@router.patch("/{crop_code}", response_model=CropConfigurationResponse)
def update_crop_configuration(
    crop_code: CropCode,
    configuration: CropConfigurationUpdate,
) -> CropConfigurationResponse:
    """Update configuration metadata and tests without changing the crop code."""
    updates = configuration.model_dump(
        by_alias=True, exclude_unset=True, exclude_none=True
    )
    if not updates:
        raise HTTPException(
            status_code=400,
            detail="Provide cropName, status, or qualityTests to update.",
        )

    document = crop_configurations_collection().find_one_and_update(
        {"_id": crop_code},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Crop configuration not found.")

    return _crop_configuration_response(document)
