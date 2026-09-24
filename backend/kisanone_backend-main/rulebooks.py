"""Rulebooks, A/B/C/F Quality Grading, and Prototype Grade-based Pricing for KisanOne."""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated, Any, Optional

from bson.decimal128 import Decimal128
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from database import get_database

router = APIRouter(tags=["Rulebooks & Quality Grading"])

RulebookId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Unique Rulebook identifier (e.g., RULEBOOK-WHEAT-V1).",
    ),
]
EvaluationId = Annotated[
    str,
    Field(
        min_length=1,
        max_length=50,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="Unique Quality Evaluation identifier (e.g., EVAL-000001).",
    ),
]


class QualityGrade(str, Enum):
    """Internal KisanOne prototype quality grades."""

    A = "A"
    B = "B"
    C = "C"
    F = "F"


class EvaluationDecision(str, Enum):
    """Procurement qualification decision."""

    PASS = "PASS"
    FAIL = "FAIL"


class RuleOperator(str, Enum):
    """Comparison operator for quality threshold evaluation."""

    LTE = "LTE"
    GTE = "GTE"
    BETWEEN = "BETWEEN"
    EQ = "EQ"


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


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class GradePricing(BaseModel):
    """Prototype price definition for a specific quality grade."""

    model_config = ConfigDict(populate_by_name=True)

    price_per_kg: Decimal = Field(alias="pricePerKg", ge=0)
    description: Optional[str] = None


class TestThreshold(BaseModel):
    """Single test evaluation threshold condition."""

    model_config = ConfigDict(populate_by_name=True)

    test_code: str = Field(alias="testCode")
    operator: RuleOperator
    threshold: Any  # Decimal, bool, or tuple/list [min, max]
    unit: Optional[str] = None
    description: Optional[str] = None


class RulebookResponse(BaseModel):
    """Rulebook configuration document returned by the API."""

    model_config = ConfigDict(populate_by_name=True)

    rulebook_id: RulebookId = Field(alias="rulebookId")
    crop_code: str = Field(alias="cropCode")
    crop_name: str = Field(alias="cropName")
    version: int = Field(ge=1)
    status: str
    environment: str = "PROTOTYPE"
    source: str = "RESEARCHED_DEMO_RULES"
    reference_standard: str = Field(alias="referenceStandard")
    notes: Optional[str] = None
    grades: list[QualityGrade]
    pricing: dict[str, GradePricing]
    rules: dict[str, list[TestThreshold]]
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class TestEvaluationResult(BaseModel):
    """Explanation breakdown for an individual quality test."""

    model_config = ConfigDict(populate_by_name=True)

    test_code: str = Field(alias="testCode")
    test_name: Optional[str] = Field(default=None, alias="testName")
    measured_value: Any = Field(alias="measuredValue")
    grade: QualityGrade
    result: EvaluationDecision
    operator: Optional[RuleOperator] = None
    threshold: Optional[Any] = None
    unit: Optional[str] = None
    explanation: str


class QualityEvaluationResponse(BaseModel):
    """Evaluation output record."""

    model_config = ConfigDict(populate_by_name=True)

    evaluation_id: EvaluationId = Field(alias="evaluationId")
    lot_id: str = Field(alias="lotId")
    qc_attempt_id: str = Field(alias="qcAttemptId")
    crop_code: str = Field(alias="cropCode")
    rulebook_id: RulebookId = Field(alias="rulebookId")
    rulebook_version: int = Field(alias="rulebookVersion")
    grade: QualityGrade
    decision: EvaluationDecision
    price_per_kg: Decimal = Field(alias="pricePerKg")
    results: list[TestEvaluationResult]
    evaluated_at: datetime = Field(alias="evaluatedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


# ---------------------------------------------------------------------------
# MongoDB Collections & Indexes
# ---------------------------------------------------------------------------


def rulebooks_collection():
    """Return the shared MongoDB rulebooks collection."""
    return get_database()["rulebooks"]


def quality_evaluations_collection():
    """Return the shared MongoDB qualityEvaluations collection."""
    return get_database()["qualityEvaluations"]


def counters_collection():
    """Return the shared MongoDB counters collection."""
    return get_database()["counters"]


def ensure_rulebook_indexes() -> None:
    """Create indexes required by the Rulebook module."""
    collection = rulebooks_collection()
    collection.create_index(
        "rulebookId", unique=True, name="rulebook_id_unique"
    )
    collection.create_index(
        [("cropCode", ASCENDING), ("version", ASCENDING)],
        unique=True,
        name="crop_code_version_unique",
    )
    collection.create_index(
        [("cropCode", ASCENDING), ("status", ASCENDING)],
        name="crop_code_status_index",
    )
    collection.create_index([("createdAt", DESCENDING)], name="rulebook_created_at_index")


def ensure_quality_evaluation_indexes() -> None:
    """Create indexes required by the Quality Evaluation module."""
    collection = quality_evaluations_collection()
    collection.create_index(
        "evaluationId", unique=True, name="evaluation_id_unique"
    )
    collection.create_index(
        [("qcAttemptId", ASCENDING), ("rulebookVersion", ASCENDING)],
        unique=True,
        name="qc_attempt_rulebook_version_unique",
    )
    collection.create_index([("lotId", ASCENDING)], name="eval_lot_id_index")
    collection.create_index([("qcAttemptId", ASCENDING)], name="eval_qc_attempt_id_index")
    collection.create_index([("cropCode", ASCENDING)], name="eval_crop_code_index")
    collection.create_index([("rulebookId", ASCENDING)], name="eval_rulebook_id_index")
    collection.create_index([("grade", ASCENDING)], name="eval_grade_index")
    collection.create_index([("decision", ASCENDING)], name="eval_decision_index")
    collection.create_index(
        [("evaluatedAt", DESCENDING)], name="eval_evaluated_at_index"
    )
    try:
        _initialize_evaluation_counter_if_needed()
    except PyMongoError:
        pass


# ---------------------------------------------------------------------------
# Normalized Crop Aliases
# ---------------------------------------------------------------------------

CROP_CODE_ALIASES: dict[str, str] = {
    "PADDY": "PADDY_RICE",
    "RICE": "PADDY_RICE",
    "PADDY_RICE": "PADDY_RICE",
    "WHEAT": "WHEAT",
    "MAIZE": "MAIZE",
    "SOYBEAN": "SOYBEAN",
    "GROUNDNUT": "GROUNDNUT",
    "COTTON": "COTTON",
    "TUR": "TUR_ARHAR",
    "ARHAR": "TUR_ARHAR",
    "TUR_ARHAR": "TUR_ARHAR",
    "GRAM": "GRAM_CHICKPEA",
    "CHICKPEA": "GRAM_CHICKPEA",
    "CHANA": "GRAM_CHICKPEA",
    "GRAM_CHICKPEA": "GRAM_CHICKPEA",
    "MUSTARD": "MUSTARD_RAPESEED",
    "RAPESEED": "MUSTARD_RAPESEED",
    "MUSTARD_RAPESEED": "MUSTARD_RAPESEED",
    "SUGARCANE": "SUGARCANE",
}


def normalize_crop_code(code: str) -> str:
    """Map crop code or common alias to canonical prototype crop code."""
    normalized = code.strip().upper().replace("-", "_")
    return CROP_CODE_ALIASES.get(normalized, normalized)


# ---------------------------------------------------------------------------
# 10 Prototype Rulebook Definitions (Researched Demo Rules)
# ---------------------------------------------------------------------------

PROTOTYPE_RULEBOOKS_SPEC = [
    {
        "cropCode": "PADDY_RICE",
        "cropName": "Paddy / Rice",
        "referenceStandard": "Derived as a tighter A/B/C abstraction around Indian paddy procurement quality parameters (Paddy Grade-A MSP 2026-27 = ₹24.61/kg).",
        "pricing": {
            "A": {"pricePerKg": Decimal("24.61"), "description": "MSP 2026-27 Grade-A rate"},
            "B": {"pricePerKg": Decimal("24.00"), "description": "Good/acceptable quality discount"},
            "C": {"pricePerKg": Decimal("23.40"), "description": "Lowest acceptable quality tier"},
            "F": {"pricePerKg": Decimal("0.00"), "description": "Rejection grade - procurement blocked"},
        },
        "rules": {
            "A": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("14.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_PERCENT", "operator": "LTE", "threshold": Decimal("0.50"), "unit": "%"},
                {"testCode": "DAMAGED_DISCOLOURED_PERCENT", "operator": "LTE", "threshold": Decimal("2.00"), "unit": "%"},
                {"testCode": "IMMATURE_SHRIVELLED_PERCENT", "operator": "LTE", "threshold": Decimal("1.50"), "unit": "%"},
            ],
            "B": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("15.5"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_PERCENT", "operator": "LTE", "threshold": Decimal("0.75"), "unit": "%"},
                {"testCode": "DAMAGED_DISCOLOURED_PERCENT", "operator": "LTE", "threshold": Decimal("3.50"), "unit": "%"},
                {"testCode": "IMMATURE_SHRIVELLED_PERCENT", "operator": "LTE", "threshold": Decimal("2.50"), "unit": "%"},
            ],
            "C": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("17.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_PERCENT", "operator": "LTE", "threshold": Decimal("1.00"), "unit": "%"},
                {"testCode": "DAMAGED_DISCOLOURED_PERCENT", "operator": "LTE", "threshold": Decimal("5.00"), "unit": "%"},
                {"testCode": "IMMATURE_SHRIVELLED_PERCENT", "operator": "LTE", "threshold": Decimal("3.00"), "unit": "%"},
            ],
        },
    },
    {
        "cropCode": "WHEAT",
        "cropName": "Wheat",
        "referenceStandard": "Researched wheat FAQ procurement specifications and Wheat MSP 2026-27 (₹25.85/kg).",
        "pricing": {
            "A": {"pricePerKg": Decimal("25.85"), "description": "Full MSP 2026-27 rate"},
            "B": {"pricePerKg": Decimal("25.20"), "description": "Acceptable FAQ discount"},
            "C": {"pricePerKg": Decimal("24.55"), "description": "Lowest acceptable quality tier"},
            "F": {"pricePerKg": Decimal("0.00"), "description": "Rejection grade - procurement blocked"},
        },
        "rules": {
            "A": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("12.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_PERCENT", "operator": "LTE", "threshold": Decimal("0.50"), "unit": "%"},
                {"testCode": "DAMAGED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("2.00"), "unit": "%"},
                {"testCode": "WEEVILLED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("2.00"), "unit": "%"},
            ],
            "B": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("13.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_PERCENT", "operator": "LTE", "threshold": Decimal("0.75"), "unit": "%"},
                {"testCode": "DAMAGED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("4.00"), "unit": "%"},
                {"testCode": "WEEVILLED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("5.00"), "unit": "%"},
            ],
            "C": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("14.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_PERCENT", "operator": "LTE", "threshold": Decimal("1.00"), "unit": "%"},
                {"testCode": "DAMAGED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("6.00"), "unit": "%"},
                {"testCode": "WEEVILLED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("10.00"), "unit": "%"},
            ],
        },
    },
    {
        "cropCode": "MAIZE",
        "cropName": "Maize",
        "referenceStandard": "AGMARK-inspired Grade I/II/III converted into KisanOne prototype A/B/C bands (Maize MSP 2026-27 = ₹24.10/kg).",
        "pricing": {
            "A": {"pricePerKg": Decimal("24.10"), "description": "Full MSP 2026-27 rate"},
            "B": {"pricePerKg": Decimal("23.50"), "description": "Acceptable quality discount"},
            "C": {"pricePerKg": Decimal("22.90"), "description": "Lowest acceptable quality tier"},
            "F": {"pricePerKg": Decimal("0.00"), "description": "Rejection grade - procurement blocked"},
        },
        "rules": {
            "A": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("12.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_ORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.10"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_INORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.00"), "unit": "%"},
                {"testCode": "OTHER_EDIBLE_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("0.50"), "unit": "%"},
                {"testCode": "DAMAGED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("1.00"), "unit": "%"},
                {"testCode": "IMMATURE_SHRIVELLED_PERCENT", "operator": "LTE", "threshold": Decimal("2.00"), "unit": "%"},
                {"testCode": "WEEVILLED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("2.00"), "unit": "%"},
            ],
            "B": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("12.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_ORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.25"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_INORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.10"), "unit": "%"},
                {"testCode": "OTHER_EDIBLE_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("1.00"), "unit": "%"},
                {"testCode": "DAMAGED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("2.00"), "unit": "%"},
                {"testCode": "IMMATURE_SHRIVELLED_PERCENT", "operator": "LTE", "threshold": Decimal("4.00"), "unit": "%"},
                {"testCode": "WEEVILLED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("4.00"), "unit": "%"},
            ],
            "C": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("14.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_ORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.50"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_INORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.25"), "unit": "%"},
                {"testCode": "OTHER_EDIBLE_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("2.00"), "unit": "%"},
                {"testCode": "DAMAGED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("3.00"), "unit": "%"},
                {"testCode": "IMMATURE_SHRIVELLED_PERCENT", "operator": "LTE", "threshold": Decimal("6.00"), "unit": "%"},
                {"testCode": "WEEVILLED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("6.00"), "unit": "%"},
            ],
        },
    },
    {
        "cropCode": "SOYBEAN",
        "cropName": "Soybean",
        "referenceStandard": "AGMARK Special / Standard / General specifications converted to prototype A/B/C model (Soybean MSP 2026-27 = ₹57.08/kg).",
        "pricing": {
            "A": {"pricePerKg": Decimal("57.08"), "description": "Full MSP 2026-27 rate"},
            "B": {"pricePerKg": Decimal("55.35"), "description": "Acceptable quality discount"},
            "C": {"pricePerKg": Decimal("53.65"), "description": "Lowest acceptable quality tier"},
            "F": {"pricePerKg": Decimal("0.00"), "description": "Rejection grade - procurement blocked"},
        },
        "rules": {
            "A": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("7.0"), "unit": "%"},
                {"testCode": "SPLIT_CRACKED_SEEDS_PERCENT", "operator": "LTE", "threshold": Decimal("2.0"), "unit": "%"},
                {"testCode": "IMMATURE_SHRIVELLED_GREEN_PERCENT", "operator": "LTE", "threshold": Decimal("2.0"), "unit": "%"},
                {"testCode": "DAMAGED_WEEVILLED_PERCENT", "operator": "LTE", "threshold": Decimal("2.0"), "unit": "%"},
                {"testCode": "OTHER_EDIBLE_SEEDS_PERCENT", "operator": "LTE", "threshold": Decimal("0.0"), "unit": "%"},
                {"testCode": "OIL_CONTENT_PERCENT", "operator": "GTE", "threshold": Decimal("20.0"), "unit": "%"},
            ],
            "B": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("9.0"), "unit": "%"},
                {"testCode": "SPLIT_CRACKED_SEEDS_PERCENT", "operator": "LTE", "threshold": Decimal("3.0"), "unit": "%"},
                {"testCode": "IMMATURE_SHRIVELLED_GREEN_PERCENT", "operator": "LTE", "threshold": Decimal("3.0"), "unit": "%"},
                {"testCode": "DAMAGED_WEEVILLED_PERCENT", "operator": "LTE", "threshold": Decimal("3.0"), "unit": "%"},
                {"testCode": "OTHER_EDIBLE_SEEDS_PERCENT", "operator": "LTE", "threshold": Decimal("0.5"), "unit": "%"},
                {"testCode": "OIL_CONTENT_PERCENT", "operator": "GTE", "threshold": Decimal("18.0"), "unit": "%"},
            ],
            "C": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("12.0"), "unit": "%"},
                {"testCode": "SPLIT_CRACKED_SEEDS_PERCENT", "operator": "LTE", "threshold": Decimal("4.0"), "unit": "%"},
                {"testCode": "IMMATURE_SHRIVELLED_GREEN_PERCENT", "operator": "LTE", "threshold": Decimal("4.0"), "unit": "%"},
                {"testCode": "DAMAGED_WEEVILLED_PERCENT", "operator": "LTE", "threshold": Decimal("7.0"), "unit": "%"},
                {"testCode": "OTHER_EDIBLE_SEEDS_PERCENT", "operator": "LTE", "threshold": Decimal("2.0"), "unit": "%"},
                {"testCode": "OIL_CONTENT_PERCENT", "operator": "GTE", "threshold": Decimal("15.0"), "unit": "%"},
            ],
        },
    },
    {
        "cropCode": "GROUNDNUT",
        "cropName": "Groundnut",
        "referenceStandard": "AGMARK grade structure for groundnut in shell (Groundnut-in-shell MSP 2026-27 = ₹75.17/kg).",
        "pricing": {
            "A": {"pricePerKg": Decimal("75.17"), "description": "Full MSP 2026-27 rate"},
            "B": {"pricePerKg": Decimal("72.90"), "description": "Acceptable quality discount"},
            "C": {"pricePerKg": Decimal("70.65"), "description": "Lowest acceptable quality tier"},
            "F": {"pricePerKg": Decimal("0.00"), "description": "Rejection grade - procurement blocked"},
        },
        "rules": {
            "A": [
                {"testCode": "FOREIGN_MATTER_PERCENT", "operator": "LTE", "threshold": Decimal("1.0"), "unit": "%"},
                {"testCode": "DAMAGED_PODS_PERCENT", "operator": "LTE", "threshold": Decimal("0.50"), "unit": "%"},
                {"testCode": "SHRIVELLED_IMMATURE_PODS_PERCENT", "operator": "LTE", "threshold": Decimal("2.0"), "unit": "%"},
                {"testCode": "OTHER_VARIETY_PODS_PERCENT", "operator": "LTE", "threshold": Decimal("1.0"), "unit": "%"},
                {"testCode": "SHELLING_PERCENT", "operator": "GTE", "threshold": Decimal("74.0"), "unit": "%"},
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("7.0"), "unit": "%"},
            ],
            "B": [
                {"testCode": "FOREIGN_MATTER_PERCENT", "operator": "LTE", "threshold": Decimal("2.0"), "unit": "%"},
                {"testCode": "DAMAGED_PODS_PERCENT", "operator": "LTE", "threshold": Decimal("1.00"), "unit": "%"},
                {"testCode": "SHRIVELLED_IMMATURE_PODS_PERCENT", "operator": "LTE", "threshold": Decimal("3.5"), "unit": "%"},
                {"testCode": "OTHER_VARIETY_PODS_PERCENT", "operator": "LTE", "threshold": Decimal("2.0"), "unit": "%"},
                {"testCode": "SHELLING_PERCENT", "operator": "GTE", "threshold": Decimal("70.0"), "unit": "%"},
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("8.0"), "unit": "%"},
            ],
            "C": [
                {"testCode": "FOREIGN_MATTER_PERCENT", "operator": "LTE", "threshold": Decimal("3.0"), "unit": "%"},
                {"testCode": "DAMAGED_PODS_PERCENT", "operator": "LTE", "threshold": Decimal("2.00"), "unit": "%"},
                {"testCode": "SHRIVELLED_IMMATURE_PODS_PERCENT", "operator": "LTE", "threshold": Decimal("5.0"), "unit": "%"},
                {"testCode": "OTHER_VARIETY_PODS_PERCENT", "operator": "LTE", "threshold": Decimal("5.0"), "unit": "%"},
                {"testCode": "SHELLING_PERCENT", "operator": "GTE", "threshold": Decimal("68.0"), "unit": "%"},
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("9.0"), "unit": "%"},
            ],
        },
    },
    {
        "cropCode": "COTTON",
        "cropName": "Cotton",
        "referenceStandard": "Researched fibre quality parameters: staple length, micronaire, trash, and fibre strength (Cotton Medium Staple MSP 2026-27 = ₹82.67/kg).",
        "pricing": {
            "A": {"pricePerKg": Decimal("82.67"), "description": "Full MSP 2026-27 rate for long staple / superior fibre"},
            "B": {"pricePerKg": Decimal("80.20"), "description": "Acceptable medium staple quality"},
            "C": {"pricePerKg": Decimal("77.70"), "description": "Lowest acceptable quality tier"},
            "F": {"pricePerKg": Decimal("0.00"), "description": "Rejection grade - procurement blocked"},
        },
        "rules": {
            "A": [
                {"testCode": "STAPLE_LENGTH_MM", "operator": "GTE", "threshold": Decimal("27.0"), "unit": "mm"},
                {"testCode": "MICRONAIRE", "operator": "BETWEEN", "threshold": [Decimal("3.5"), Decimal("5.0")], "unit": "value"},
                {"testCode": "TRASH_PERCENT", "operator": "LTE", "threshold": Decimal("4.0"), "unit": "%"},
                {"testCode": "FIBRE_STRENGTH_GPT", "operator": "GTE", "threshold": Decimal("25.0"), "unit": "GPT"},
            ],
            "B": [
                {"testCode": "STAPLE_LENGTH_MM", "operator": "GTE", "threshold": Decimal("24.0"), "unit": "mm"},
                {"testCode": "MICRONAIRE", "operator": "BETWEEN", "threshold": [Decimal("3.5"), Decimal("5.5")], "unit": "value"},
                {"testCode": "TRASH_PERCENT", "operator": "LTE", "threshold": Decimal("6.0"), "unit": "%"},
                {"testCode": "FIBRE_STRENGTH_GPT", "operator": "GTE", "threshold": Decimal("22.0"), "unit": "GPT"},
            ],
            "C": [
                {"testCode": "STAPLE_LENGTH_MM", "operator": "GTE", "threshold": Decimal("21.0"), "unit": "mm"},
                {"testCode": "MICRONAIRE", "operator": "BETWEEN", "threshold": [Decimal("3.0"), Decimal("6.0")], "unit": "value"},
                {"testCode": "TRASH_PERCENT", "operator": "LTE", "threshold": Decimal("10.0"), "unit": "%"},
                {"testCode": "FIBRE_STRENGTH_GPT", "operator": "GTE", "threshold": Decimal("20.0"), "unit": "GPT"},
            ],
        },
    },
    {
        "cropCode": "TUR_ARHAR",
        "cropName": "Tur / Arhar",
        "referenceStandard": "Researched AGMARK Special / Standard / General structure for Red Gram / Arhar (Tur MSP 2026-27 = ₹84.50/kg).",
        "pricing": {
            "A": {"pricePerKg": Decimal("84.50"), "description": "Full MSP 2026-27 rate"},
            "B": {"pricePerKg": Decimal("82.00"), "description": "Acceptable quality discount"},
            "C": {"pricePerKg": Decimal("79.50"), "description": "Lowest acceptable quality tier"},
            "F": {"pricePerKg": Decimal("0.00"), "description": "Rejection grade - procurement blocked"},
        },
        "rules": {
            "A": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("10.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_ORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.10"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_INORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.00"), "unit": "%"},
                {"testCode": "OTHER_EDIBLE_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("0.50"), "unit": "%"},
                {"testCode": "DAMAGED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("0.50"), "unit": "%"},
                {"testCode": "WEEVILLED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("3.0"), "unit": "%"},
            ],
            "B": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("12.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_ORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.50"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_INORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.10"), "unit": "%"},
                {"testCode": "OTHER_EDIBLE_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("2.00"), "unit": "%"},
                {"testCode": "DAMAGED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("2.00"), "unit": "%"},
                {"testCode": "WEEVILLED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("5.0"), "unit": "%"},
            ],
            "C": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("14.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_ORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.75"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_INORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.25"), "unit": "%"},
                {"testCode": "OTHER_EDIBLE_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("5.00"), "unit": "%"},
                {"testCode": "DAMAGED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("5.00"), "unit": "%"},
                {"testCode": "WEEVILLED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("10.0"), "unit": "%"},
            ],
        },
    },
    {
        "cropCode": "GRAM_CHICKPEA",
        "cropName": "Gram / Chickpea",
        "referenceStandard": "Researched Bengal gram / Chana grading specifications (Gram MSP 2026-27 = ₹58.75/kg).",
        "pricing": {
            "A": {"pricePerKg": Decimal("58.75"), "description": "Full MSP 2026-27 rate"},
            "B": {"pricePerKg": Decimal("57.00"), "description": "Acceptable quality discount"},
            "C": {"pricePerKg": Decimal("55.30"), "description": "Lowest acceptable quality tier"},
            "F": {"pricePerKg": Decimal("0.00"), "description": "Rejection grade - procurement blocked"},
        },
        "rules": {
            "A": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("11.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_ORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.10"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_INORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.05"), "unit": "%"},
                {"testCode": "OTHER_EDIBLE_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("0.20"), "unit": "%"},
                {"testCode": "DAMAGED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("0.50"), "unit": "%"},
                {"testCode": "WEEVILLED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("1.0"), "unit": "%"},
                {"testCode": "BROKEN_FRAGMENT_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("0.50"), "unit": "%"},
            ],
            "B": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("12.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_ORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.10"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_INORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.15"), "unit": "%"},
                {"testCode": "OTHER_EDIBLE_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("0.50"), "unit": "%"},
                {"testCode": "DAMAGED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("1.00"), "unit": "%"},
                {"testCode": "WEEVILLED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("2.0"), "unit": "%"},
                {"testCode": "BROKEN_FRAGMENT_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("2.00"), "unit": "%"},
            ],
            "C": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("16.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_ORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.75"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_INORGANIC_PERCENT", "operator": "LTE", "threshold": Decimal("0.25"), "unit": "%"},
                {"testCode": "OTHER_EDIBLE_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("2.00"), "unit": "%"},
                {"testCode": "DAMAGED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("5.00"), "unit": "%"},
                {"testCode": "WEEVILLED_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("3.0"), "unit": "%"},
                {"testCode": "BROKEN_FRAGMENT_GRAINS_PERCENT", "operator": "LTE", "threshold": Decimal("3.00"), "unit": "%"},
            ],
        },
    },
    {
        "cropCode": "MUSTARD_RAPESEED",
        "cropName": "Mustard / Rapeseed",
        "referenceStandard": "Researched AGMARK mustard/rapeseed quality factors and zero-tolerance Argemone safety check (Mustard MSP 2026-27 = ₹62.00/kg).",
        "pricing": {
            "A": {"pricePerKg": Decimal("62.00"), "description": "Full MSP 2026-27 rate"},
            "B": {"pricePerKg": Decimal("60.20"), "description": "Acceptable quality discount"},
            "C": {"pricePerKg": Decimal("58.30"), "description": "Lowest acceptable quality tier"},
            "F": {"pricePerKg": Decimal("0.00"), "description": "Rejection grade - procurement blocked"},
        },
        "rules": {
            "A": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("6.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_PERCENT", "operator": "LTE", "threshold": Decimal("1.0"), "unit": "%"},
                {"testCode": "DEAD_DISCOLOURED_DAMAGED_PERCENT", "operator": "LTE", "threshold": Decimal("1.0"), "unit": "%"},
                {"testCode": "UNRIPE_SHRIVELLED_SLIGHTLY_DAMAGED_PERCENT", "operator": "LTE", "threshold": Decimal("1.5"), "unit": "%"},
                {"testCode": "SMALL_ATROPHIED_SEEDS_PERCENT", "operator": "LTE", "threshold": Decimal("5.0"), "unit": "%"},
                {"testCode": "ADMIXTURE_OTHER_VARIETIES_PERCENT", "operator": "LTE", "threshold": Decimal("5.0"), "unit": "%"},
                {"testCode": "ARGEMONE_CONTAMINATION", "operator": "EQ", "threshold": False, "unit": "boolean"},
            ],
            "B": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("6.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_PERCENT", "operator": "LTE", "threshold": Decimal("2.0"), "unit": "%"},
                {"testCode": "DEAD_DISCOLOURED_DAMAGED_PERCENT", "operator": "LTE", "threshold": Decimal("1.5"), "unit": "%"},
                {"testCode": "UNRIPE_SHRIVELLED_SLIGHTLY_DAMAGED_PERCENT", "operator": "LTE", "threshold": Decimal("3.0"), "unit": "%"},
                {"testCode": "SMALL_ATROPHIED_SEEDS_PERCENT", "operator": "LTE", "threshold": Decimal("10.0"), "unit": "%"},
                {"testCode": "ADMIXTURE_OTHER_VARIETIES_PERCENT", "operator": "LTE", "threshold": Decimal("10.0"), "unit": "%"},
                {"testCode": "ARGEMONE_CONTAMINATION", "operator": "EQ", "threshold": False, "unit": "boolean"},
            ],
            "C": [
                {"testCode": "MOISTURE_PERCENT", "operator": "LTE", "threshold": Decimal("6.0"), "unit": "%"},
                {"testCode": "FOREIGN_MATTER_PERCENT", "operator": "LTE", "threshold": Decimal("3.0"), "unit": "%"},
                {"testCode": "DEAD_DISCOLOURED_DAMAGED_PERCENT", "operator": "LTE", "threshold": Decimal("2.0"), "unit": "%"},
                {"testCode": "UNRIPE_SHRIVELLED_SLIGHTLY_DAMAGED_PERCENT", "operator": "LTE", "threshold": Decimal("4.0"), "unit": "%"},
                {"testCode": "SMALL_ATROPHIED_SEEDS_PERCENT", "operator": "LTE", "threshold": Decimal("15.0"), "unit": "%"},
                {"testCode": "ADMIXTURE_OTHER_VARIETIES_PERCENT", "operator": "LTE", "threshold": Decimal("15.0"), "unit": "%"},
                {"testCode": "ARGEMONE_CONTAMINATION", "operator": "EQ", "threshold": False, "unit": "boolean"},
            ],
        },
    },
    {
        "cropCode": "SUGARCANE",
        "cropName": "Sugarcane",
        "referenceStandard": "Prototype recovery-based pricing inspired by Fair and Remunerative Price (FRP 2026-27 = ₹365/qtl at 10.25% basic recovery).",
        "pricing": {
            "A": {"pricePerKg": Decimal("3.65"), "description": "FRP 2026-27 benchmark rate (₹365/qtl at >= 10.25% recovery)"},
            "B": {"pricePerKg": Decimal("3.50"), "description": "Intermediate recovery rate (9.75% - 10.25%)"},
            "C": {"pricePerKg": Decimal("3.38"), "description": "Lowest acceptable recovery tier (9.50% - 9.75%)"},
            "F": {"pricePerKg": Decimal("0.00"), "description": "Rejection grade (< 9.50% recovery) - procurement blocked"},
        },
        "rules": {
            "A": [
                {"testCode": "SUGAR_RECOVERY_PERCENT", "operator": "GTE", "threshold": Decimal("10.25"), "unit": "%"},
            ],
            "B": [
                {"testCode": "SUGAR_RECOVERY_PERCENT", "operator": "GTE", "threshold": Decimal("9.75"), "unit": "%"},
            ],
            "C": [
                {"testCode": "SUGAR_RECOVERY_PERCENT", "operator": "GTE", "threshold": Decimal("9.50"), "unit": "%"},
            ],
        },
    },
]


def _build_rulebook_document(spec: dict) -> dict:
    """Transform in-memory rulebook spec to BSON-compatible database document."""
    now = datetime.now(timezone.utc)
    crop_code = spec["cropCode"]
    rulebook_id = f"RULEBOOK-{crop_code}-V1"

    pricing_doc = {}
    for grade, p in spec["pricing"].items():
        pricing_doc[grade] = {
            "pricePerKg": _as_decimal128(p["pricePerKg"]),
            "description": p.get("description", ""),
        }

    rules_doc = {}
    for grade in ("A", "B", "C"):
        rules_doc[grade] = []
        for r in spec["rules"].get(grade, []):
            thresh = r["threshold"]
            if isinstance(thresh, (list, tuple)):
                stored_thresh = [_as_decimal128(v) for v in thresh]
            elif isinstance(thresh, bool):
                stored_thresh = thresh
            else:
                stored_thresh = _as_decimal128(thresh)

            rules_doc[grade].append(
                {
                    "testCode": r["testCode"],
                    "operator": r["operator"],
                    "threshold": stored_thresh,
                    "unit": r.get("unit"),
                }
            )

    return {
        "_id": rulebook_id,
        "rulebookId": rulebook_id,
        "cropCode": crop_code,
        "cropName": spec["cropName"],
        "version": 1,
        "status": "ACTIVE",
        "environment": "PROTOTYPE",
        "source": "RESEARCHED_DEMO_RULES",
        "referenceStandard": spec["referenceStandard"],
        "notes": "Internal KisanOne prototype quality grade model. Not official universal GOI grading.",
        "grades": ["A", "B", "C", "F"],
        "pricing": pricing_doc,
        "rules": rules_doc,
        "createdAt": now,
        "updatedAt": now,
    }


def seed_prototype_rulebooks() -> None:
    """Idempotently seed the 10 prototype Rulebooks without modifying cropConfigurations."""
    try:
        rb_coll = rulebooks_collection()
    except PyMongoError:
        return

    for spec in PROTOTYPE_RULEBOOKS_SPEC:
        crop_code = spec["cropCode"]
        rulebook_id = f"RULEBOOK-{crop_code}-V1"

        # Seed Rulebook if absent; preserve cropConfigurations as authoritative source of truth
        if rb_coll.find_one({"rulebookId": rulebook_id}) is None:
            doc = _build_rulebook_document(spec)
            try:
                rb_coll.insert_one(doc)
            except DuplicateKeyError:
                pass


def _rulebook_response(document: dict) -> RulebookResponse:
    """Format MongoDB rulebook document into API response model."""
    resp = dict(document)
    pricing = {}
    for grade, p in document.get("pricing", {}).items():
        pricing[grade] = {
            "pricePerKg": _as_decimal(p["pricePerKg"]),
            "description": p.get("description"),
        }
    resp["pricing"] = pricing

    rules = {}
    for grade, r_list in document.get("rules", {}).items():
        rules[grade] = []
        for r in r_list:
            thresh = r["threshold"]
            if isinstance(thresh, list):
                val = [_as_decimal(v) for v in thresh]
            elif isinstance(thresh, bool):
                val = thresh
            else:
                val = _as_decimal(thresh)
            rules[grade].append(
                {
                    "testCode": r["testCode"],
                    "operator": r["operator"],
                    "threshold": val,
                    "unit": r.get("unit"),
                }
            )
    resp["rules"] = rules
    return RulebookResponse.model_validate(resp)


def _evaluation_response(document: dict) -> QualityEvaluationResponse:
    """Format MongoDB evaluation document into API response model."""
    resp = dict(document)
    resp["pricePerKg"] = _as_decimal(document["pricePerKg"])
    results = []
    for r in document.get("results", []):
        r_copy = dict(r)
        if isinstance(r_copy.get("measuredValue"), Decimal128):
            r_copy["measuredValue"] = _as_decimal(r_copy["measuredValue"])
        if isinstance(r_copy.get("threshold"), Decimal128):
            r_copy["threshold"] = _as_decimal(r_copy["threshold"])
        elif isinstance(r_copy.get("threshold"), list):
            r_copy["threshold"] = [
                _as_decimal(v) if isinstance(v, Decimal128) else v
                for v in r_copy["threshold"]
            ]
        results.append(TestEvaluationResult.model_validate(r_copy))
    resp["results"] = results
    return QualityEvaluationResponse.model_validate(resp)


# ---------------------------------------------------------------------------
# Grading and Evaluation Engine
# ---------------------------------------------------------------------------


def _check_condition(measured_value: Any, operator: str, threshold: Any) -> bool:
    """Evaluate one measurement against a threshold condition."""
    if isinstance(threshold, bool):
        return bool(measured_value) == threshold

    # Numeric comparisons
    val = _as_decimal(measured_value)

    if operator == "LTE":
        return val <= _as_decimal(threshold)
    elif operator == "GTE":
        return val >= _as_decimal(threshold)
    elif operator == "BETWEEN":
        low = _as_decimal(threshold[0])
        high = _as_decimal(threshold[1])
        return low <= val <= high
    elif operator == "EQ":
        return val == _as_decimal(threshold)
    return False


def _evaluate_individual_test(
    test_code: str,
    measured_value: Any,
    rulebook: dict,
) -> TestEvaluationResult:
    """Evaluate an individual test measurement and determine its achieved grade."""
    rules = rulebook.get("rules", {})

    # Evaluate A -> B -> C -> F
    for target_grade in ("A", "B", "C"):
        conditions = rules.get(target_grade, [])
        matching_cond = next((c for c in conditions if c["testCode"] == test_code), None)
        if matching_cond:
            op = matching_cond["operator"]
            thresh = matching_cond["threshold"]
            unit = matching_cond.get("unit") or ""
            if _check_condition(measured_value, op, thresh):
                explanation = f"{test_code} = {measured_value}{unit} satisfies Grade {target_grade} ({op} {thresh})"
                return TestEvaluationResult(
                    testCode=test_code,
                    testName=test_code.replace("_", " ").title(),
                    measuredValue=measured_value,
                    grade=QualityGrade(target_grade),
                    result=EvaluationDecision.PASS,
                    operator=RuleOperator(op),
                    threshold=_as_decimal(thresh) if not isinstance(thresh, (list, bool)) else thresh,
                    unit=unit,
                    explanation=explanation,
                )

    # If C threshold is violated or not satisfied -> F
    c_cond = next((c for c in rules.get("C", []) if c["testCode"] == test_code), None)
    op = c_cond["operator"] if c_cond else None
    thresh = c_cond["threshold"] if c_cond else None
    unit = c_cond.get("unit") if c_cond else ""
    explanation = f"{test_code} = {measured_value}{unit} violates minimum Grade C threshold ({op} {thresh})"
    return TestEvaluationResult(
        testCode=test_code,
        testName=test_code.replace("_", " ").title(),
        measuredValue=measured_value,
        grade=QualityGrade.F,
        result=EvaluationDecision.FAIL,
        operator=RuleOperator(op) if op else None,
        threshold=_as_decimal(thresh) if thresh and not isinstance(thresh, (list, bool)) else thresh,
        unit=unit,
        explanation=explanation,
    )


def evaluate_lot_qc(
    qc_record: dict,
    rulebook: dict,
) -> dict:
    """Perform deterministic A -> B -> C -> F evaluation on a QC attempt."""
    tests = qc_record.get("tests", {})
    results: list[TestEvaluationResult] = []

    # Check each test defined in the rulebook
    rulebook_tests = [r["testCode"] for r in rulebook.get("rules", {}).get("A", [])]

    for test_code in rulebook_tests:
        if test_code in tests:
            val = tests[test_code]
            test_res = _evaluate_individual_test(test_code, val, rulebook)
            results.append(test_res)

    # Calculate overall grade in order A -> B -> C -> F
    grade_order = {"A": 3, "B": 2, "C": 1, "F": 0}

    overall_grade = "A"
    if not results:
        overall_grade = "F"
    else:
        # Lot grade is the weakest grade achieved across all evaluated tests
        min_rank = min(grade_order[r.grade.value] for r in results)
        rank_to_grade = {3: "A", 2: "B", 1: "C", 0: "F"}
        overall_grade = rank_to_grade[min_rank]

    decision = "PASS" if overall_grade in ("A", "B", "C") else "FAIL"
    price_info = rulebook.get("pricing", {}).get(overall_grade, {})
    price_per_kg = _as_decimal(price_info.get("pricePerKg", 0))

    return {
        "grade": overall_grade,
        "decision": decision,
        "pricePerKg": price_per_kg,
        "results": results,
    }


def _initialize_evaluation_counter_if_needed(session=None) -> None:
    """Initialize the evaluationId counter from existing evaluations if not present."""
    counters = counters_collection()
    if counters.find_one({"_id": "evaluationId"}, session=session) is None:
        latest = quality_evaluations_collection().find_one(
            projection={"evaluationId": 1},
            sort=[("evaluationId", DESCENDING)],
            session=session,
        )
        current_seq = 0
        if latest and "evaluationId" in latest:
            try:
                current_seq = int(latest["evaluationId"].split("-")[-1])
            except (ValueError, IndexError):
                current_seq = 0
        counters.update_one(
            {"_id": "evaluationId"},
            {"$setOnInsert": {"seq": current_seq}},
            upsert=True,
            session=session,
        )


def _generate_evaluation_id(session=None) -> str:
    """Generate sequential Evaluation ID (EVAL-000001, EVAL-000002, ...)."""
    _initialize_evaluation_counter_if_needed(session=session)
    counters = counters_collection()
    counter = counters.find_one_and_update(
        {"_id": "evaluationId"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        session=session,
    )
    seq = counter["seq"]
    return f"EVAL-{seq:06d}"


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/rulebooks/{crop_code}",
    response_model=RulebookResponse,
)
def get_active_rulebook(crop_code: str) -> RulebookResponse:
    """Retrieve the currently ACTIVE Rulebook for a crop."""
    canonical = normalize_crop_code(crop_code)
    rb = rulebooks_collection().find_one({"cropCode": canonical, "status": "ACTIVE"})
    if rb is None:
        rb = rulebooks_collection().find_one({"cropCode": crop_code.upper(), "status": "ACTIVE"})
    if rb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active Rulebook not found for crop '{crop_code}'.",
        )
    return _rulebook_response(rb)


@router.get(
    "/rulebooks/{crop_code}/versions",
    response_model=list[RulebookResponse],
)
def get_rulebook_versions(crop_code: str) -> list[RulebookResponse]:
    """Retrieve all Rulebook versions for a crop ordered by version descending."""
    canonical = normalize_crop_code(crop_code)
    cursor = rulebooks_collection().find(
        {"cropCode": {"$in": [canonical, crop_code.upper()]}}
    ).sort("version", DESCENDING)
    rbs = list(cursor)
    if not rbs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No Rulebook versions found for crop '{crop_code}'.",
        )
    return [_rulebook_response(doc) for doc in rbs]


@router.get(
    "/rulebooks/{crop_code}/versions/{version}",
    response_model=RulebookResponse,
)
def get_rulebook_by_version(crop_code: str, version: int) -> RulebookResponse:
    """Retrieve a specific Rulebook version for a crop."""
    canonical = normalize_crop_code(crop_code)
    rb = rulebooks_collection().find_one(
        {"cropCode": {"$in": [canonical, crop_code.upper()]}, "version": version}
    )
    if rb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rulebook version {version} not found for crop '{crop_code}'.",
        )
    return _rulebook_response(rb)


@router.post(
    "/quality-checks/{qc_attempt_id}/evaluate",
    response_model=QualityEvaluationResponse,
    status_code=status.HTTP_201_CREATED,
)
def evaluate_quality_check(qc_attempt_id: str) -> QualityEvaluationResponse:
    """Evaluate a QC attempt against the active Rulebook, recording grade and price."""
    database = get_database()
    qc_coll = database["qualityChecks"]

    qc = qc_coll.find_one({"qcAttemptId": qc_attempt_id})
    if qc is None:
        qc = qc_coll.find_one({"_id": qc_attempt_id})
    if qc is None:
        raise HTTPException(status_code=404, detail="Quality Check attempt not found.")

    crop_code = qc["cropCode"]
    canonical = normalize_crop_code(crop_code)

    rulebook = rulebooks_collection().find_one({"cropCode": canonical, "status": "ACTIVE"})
    if rulebook is None:
        rulebook = rulebooks_collection().find_one({"cropCode": crop_code.upper(), "status": "ACTIVE"})
    if rulebook is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active Rulebook found for crop '{crop_code}'.",
        )

    # Check if this QC attempt was already evaluated against this Rulebook version
    eval_coll = quality_evaluations_collection()
    existing = eval_coll.find_one(
        {"qcAttemptId": qc["qcAttemptId"], "rulebookVersion": rulebook["version"]}
    )
    if existing:
        return _evaluation_response(existing)

    eval_result = evaluate_lot_qc(qc, rulebook)

    now = datetime.now(timezone.utc)
    evaluation_id = _generate_evaluation_id()

    # Store serialized results
    results_doc = []
    for r in eval_result["results"]:
        meas_val = r.measured_value
        thresh_val = r.threshold
        if isinstance(meas_val, (int, float, Decimal)) and not isinstance(meas_val, bool):
            meas_val = _as_decimal128(meas_val)
        if isinstance(thresh_val, (int, float, Decimal)) and not isinstance(thresh_val, bool):
            thresh_val = _as_decimal128(thresh_val)
        elif isinstance(thresh_val, (list, tuple)):
            thresh_val = [_as_decimal128(v) for v in thresh_val]

        results_doc.append(
            {
                "testCode": r.test_code,
                "testName": r.test_name,
                "measuredValue": meas_val,
                "grade": r.grade.value,
                "result": r.result.value,
                "operator": r.operator.value if r.operator else None,
                "threshold": thresh_val,
                "unit": r.unit,
                "explanation": r.explanation,
            }
        )

    document = {
        "_id": evaluation_id,
        "evaluationId": evaluation_id,
        "lotId": qc["lotId"],
        "qcAttemptId": qc["qcAttemptId"],
        "cropCode": qc["cropCode"],
        "rulebookId": rulebook["rulebookId"],
        "rulebookVersion": rulebook["version"],
        "grade": eval_result["grade"],
        "decision": eval_result["decision"],
        "pricePerKg": _as_decimal128(eval_result["pricePerKg"]),
        "results": results_doc,
        "evaluatedAt": now,
        "createdAt": now,
        "updatedAt": now,
    }

    try:
        eval_coll.insert_one(document)
    except DuplicateKeyError as exc:
        existing = eval_coll.find_one(
            {"qcAttemptId": qc["qcAttemptId"], "rulebookVersion": rulebook["version"]}
        )
        if existing:
            return _evaluation_response(existing)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Evaluation ID collision during recording. Please retry.",
        ) from exc

    return _evaluation_response(document)


@router.get(
    "/quality-checks/{qc_attempt_id}/evaluation",
    response_model=QualityEvaluationResponse,
)
def get_evaluation_for_qc(qc_attempt_id: str) -> QualityEvaluationResponse:
    """Retrieve the latest quality evaluation for a QC attempt."""
    qc = get_database()["qualityChecks"].find_one({"qcAttemptId": qc_attempt_id})
    if qc is None:
        qc = get_database()["qualityChecks"].find_one({"_id": qc_attempt_id})
    if qc is None:
        raise HTTPException(status_code=404, detail="Quality Check attempt not found.")

    doc = quality_evaluations_collection().find_one(
        {"qcAttemptId": qc["qcAttemptId"]},
        sort=[("evaluatedAt", DESCENDING)],
    )
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail="Quality evaluation not found for this QC attempt.",
        )
    return _evaluation_response(doc)
