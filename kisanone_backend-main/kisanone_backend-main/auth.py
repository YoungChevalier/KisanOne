"""Authentication and authorization for KisanOne.

Provides:
- Password-based login for farmers and employees
- OTP-based login (prototype: OTP returned in response)
- Farmer signup with password
- JWT token issuance and validation
- Demo credential seeding at startup
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, status
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, Field

from database import get_database

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ─── Configuration ───────────────────────────────────────────────────────────────

JWT_SECRET = os.getenv("JWT_SECRET", "dev-fallback-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

OTP_EXPIRE_SECONDS = 300  # 5 minutes
OTP_MAX_ATTEMPTS = 5


# ─── Collections ─────────────────────────────────────────────────────────────────

def auth_credentials_collection():
    return get_database()["auth_credentials"]


def ensure_auth_indexes() -> None:
    coll = auth_credentials_collection()
    coll.create_index("userType", name="auth_user_type_index")


# ─── Pydantic Models ────────────────────────────────────────────────────────────

class FarmerLoginRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    farmer_id: str = Field(alias="farmerId", min_length=1)
    password: str = Field(min_length=1)


class EmployeeLoginRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    employee_id: str = Field(alias="employeeId", min_length=1)
    password: str = Field(min_length=1)


class FarmerSignupRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=7, max_length=20, pattern=r"^[0-9+() -]+$")
    address: str = Field(min_length=1, max_length=300)
    district: str = Field(min_length=1, max_length=100)
    area: str = Field(min_length=1, max_length=100)
    preferred_language: str = Field(
        alias="preferredLanguage", default="Hindi", min_length=1, max_length=50
    )
    password: str = Field(min_length=6, max_length=100)


class OtpRequestBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_id: str = Field(alias="userId", min_length=1)


class OtpVerifyBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    user_id: str = Field(alias="userId", min_length=1)
    otp: str = Field(min_length=6, max_length=6)


class AuthTokenResponse(BaseModel):
    access_token: str = Field(alias="accessToken")
    token_type: str = Field(default="bearer", alias="tokenType")
    user: dict

    model_config = ConfigDict(populate_by_name=True)


class OtpRequestResponse(BaseModel):
    message: str
    otp_prototype: Optional[str] = Field(
        default=None,
        alias="otpPrototype",
        description="Prototype only: OTP returned for demo. In production, sent via SMS.",
    )
    expires_in_seconds: int = Field(alias="expiresInSeconds")

    model_config = ConfigDict(populate_by_name=True)


# ─── JWT Utilities ───────────────────────────────────────────────────────────────

def _create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token.")


def get_current_user(
    authorization: Annotated[Optional[str], Header()] = None,
) -> Optional[dict]:
    """Extract and validate the current user from the Authorization header.

    Returns None if no Authorization header is present (allows unauthenticated
    access to endpoints that support both modes).
    """
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization header format.")
    return _decode_token(parts[1])


def require_auth(
    authorization: Annotated[Optional[str], Header()] = None,
) -> dict:
    """Strict version: requires a valid JWT. Raises 401 if missing."""
    user = get_current_user(authorization)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


# ─── Farmer Endpoints ────────────────────────────────────────────────────────────

@router.post("/farmer/login", response_model=AuthTokenResponse)
def farmer_login(body: FarmerLoginRequest) -> AuthTokenResponse:
    """Authenticate a farmer with Farmer ID + password."""
    farmer = get_database()["farmers"].find_one({"_id": body.farmer_id})
    if farmer is None:
        raise HTTPException(status_code=401, detail="Invalid Farmer ID or password.")

    cred = auth_credentials_collection().find_one({"_id": body.farmer_id})
    if cred is None or not pwd_context.verify(body.password, cred.get("passwordHash", "")):
        raise HTTPException(status_code=401, detail="Invalid Farmer ID or password.")

    user_data = {
        "sub": farmer["farmerId"],
        "userType": "farmer",
        "role": "farmer",
        "farmerId": farmer["farmerId"],
        "farmerName": farmer.get("name", ""),
    }
    token = _create_access_token(user_data)
    return AuthTokenResponse(accessToken=token, tokenType="bearer", user=user_data)


@router.post("/farmer/signup", response_model=AuthTokenResponse, status_code=201)
def farmer_signup(body: FarmerSignupRequest) -> AuthTokenResponse:
    """Register a new farmer and return an auth token."""
    # Generate a unique farmer ID
    counter = get_database()["counters"].find_one_and_update(
        {"_id": "farmerId"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    farmer_id = f"FMR-{counter['seq']:03d}"

    # Check if farmer ID somehow already exists
    if get_database()["farmers"].find_one({"_id": farmer_id}):
        raise HTTPException(status_code=409, detail="Farmer ID conflict. Please try again.")

    # Create farmer document
    farmer_doc = {
        "_id": farmer_id,
        "farmerId": farmer_id,
        "name": body.name,
        "phone": body.phone,
        "address": body.address,
        "district": body.district,
        "area": body.area,
        "preferredLanguage": body.preferred_language,
        "ekycVerified": False,
    }
    get_database()["farmers"].insert_one(farmer_doc)

    # Create auth credentials
    auth_doc = {
        "_id": farmer_id,
        "userType": "farmer",
        "passwordHash": pwd_context.hash(body.password),
        "createdAt": datetime.now(timezone.utc),
    }
    auth_credentials_collection().insert_one(auth_doc)

    user_data = {
        "sub": farmer_id,
        "userType": "farmer",
        "role": "farmer",
        "farmerId": farmer_id,
        "farmerName": body.name,
    }
    token = _create_access_token(user_data)
    return AuthTokenResponse(accessToken=token, tokenType="bearer", user=user_data)


# ─── Employee Endpoints ──────────────────────────────────────────────────────────

@router.post("/employee/login", response_model=AuthTokenResponse)
def employee_login(body: EmployeeLoginRequest) -> AuthTokenResponse:
    """Authenticate an employee with Employee ID + password."""
    employee = get_database()["employees"].find_one({"_id": body.employee_id})
    if employee is None:
        raise HTTPException(status_code=401, detail="Invalid Employee ID or password.")

    cred = auth_credentials_collection().find_one({"_id": body.employee_id})
    if cred is None or not pwd_context.verify(body.password, cred.get("passwordHash", "")):
        raise HTTPException(status_code=401, detail="Invalid Employee ID or password.")

    if employee.get("status") != "ACTIVE":
        raise HTTPException(status_code=403, detail="Employee account is inactive.")

    user_data = {
        "sub": employee["employeeId"],
        "userType": "employee",
        "role": employee["role"],
        "employeeId": employee["employeeId"],
        "centreId": employee.get("centreId", ""),
        "employeeName": employee.get("name", ""),
    }
    token = _create_access_token(user_data)
    return AuthTokenResponse(accessToken=token, tokenType="bearer", user=user_data)


# ─── OTP Endpoints ───────────────────────────────────────────────────────────────

@router.post("/farmer/otp/request", response_model=OtpRequestResponse)
def request_farmer_otp(body: OtpRequestBody) -> OtpRequestResponse:
    """Generate an OTP for farmer login. Prototype: OTP returned in response."""
    farmer = get_database()["farmers"].find_one({"_id": body.user_id})
    if farmer is None:
        raise HTTPException(status_code=404, detail="Farmer not found.")

    otp = f"{secrets.randbelow(900000) + 100000}"
    otp_hash = pwd_context.hash(otp)
    expires = datetime.now(timezone.utc) + timedelta(seconds=OTP_EXPIRE_SECONDS)

    auth_credentials_collection().update_one(
        {"_id": body.user_id},
        {
            "$set": {
                "otpHash": otp_hash,
                "otpExpiresAt": expires,
                "otpAttempts": 0,
            },
            "$setOnInsert": {
                "userType": "farmer",
                "createdAt": datetime.now(timezone.utc),
            },
        },
        upsert=True,
    )

    return OtpRequestResponse(
        message="OTP generated. In production, this would be sent via SMS.",
        otpPrototype=otp,
        expiresInSeconds=OTP_EXPIRE_SECONDS,
    )


@router.post("/farmer/otp/verify", response_model=AuthTokenResponse)
def verify_farmer_otp(body: OtpVerifyBody) -> AuthTokenResponse:
    """Verify a farmer OTP and return an auth token."""
    farmer = get_database()["farmers"].find_one({"_id": body.user_id})
    if farmer is None:
        raise HTTPException(status_code=401, detail="Invalid Farmer ID.")

    cred = auth_credentials_collection().find_one({"_id": body.user_id})
    if cred is None:
        raise HTTPException(status_code=401, detail="No OTP requested for this account.")

    # Check attempts
    if cred.get("otpAttempts", 0) >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many OTP attempts. Request a new OTP.")

    # Increment attempts
    auth_credentials_collection().update_one(
        {"_id": body.user_id}, {"$inc": {"otpAttempts": 1}}
    )

    # Check expiry
    expires_at = cred.get("otpExpiresAt")
    if expires_at is None or datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=401, detail="OTP has expired. Request a new one.")

    # Verify OTP
    if not cred.get("otpHash") or not pwd_context.verify(body.otp, cred["otpHash"]):
        raise HTTPException(status_code=401, detail="Invalid OTP.")

    # Invalidate OTP (one-time use)
    auth_credentials_collection().update_one(
        {"_id": body.user_id},
        {"$set": {"otpHash": None, "otpExpiresAt": None, "otpAttempts": 0}},
    )

    user_data = {
        "sub": farmer["farmerId"],
        "userType": "farmer",
        "role": "farmer",
        "farmerId": farmer["farmerId"],
        "farmerName": farmer.get("name", ""),
    }
    token = _create_access_token(user_data)
    return AuthTokenResponse(accessToken=token, tokenType="bearer", user=user_data)


@router.post("/employee/otp/request", response_model=OtpRequestResponse)
def request_employee_otp(body: OtpRequestBody) -> OtpRequestResponse:
    """Generate an OTP for employee login. Prototype: OTP returned in response."""
    employee = get_database()["employees"].find_one({"_id": body.user_id})
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee not found.")

    otp = f"{secrets.randbelow(900000) + 100000}"
    otp_hash = pwd_context.hash(otp)
    expires = datetime.now(timezone.utc) + timedelta(seconds=OTP_EXPIRE_SECONDS)

    auth_credentials_collection().update_one(
        {"_id": body.user_id},
        {
            "$set": {
                "otpHash": otp_hash,
                "otpExpiresAt": expires,
                "otpAttempts": 0,
            },
            "$setOnInsert": {
                "userType": "employee",
                "createdAt": datetime.now(timezone.utc),
            },
        },
        upsert=True,
    )

    return OtpRequestResponse(
        message="OTP generated. In production, this would be sent via SMS.",
        otpPrototype=otp,
        expiresInSeconds=OTP_EXPIRE_SECONDS,
    )


@router.post("/employee/otp/verify", response_model=AuthTokenResponse)
def verify_employee_otp(body: OtpVerifyBody) -> AuthTokenResponse:
    """Verify an employee OTP and return an auth token."""
    employee = get_database()["employees"].find_one({"_id": body.user_id})
    if employee is None:
        raise HTTPException(status_code=401, detail="Invalid Employee ID.")

    if employee.get("status") != "ACTIVE":
        raise HTTPException(status_code=403, detail="Employee account is inactive.")

    cred = auth_credentials_collection().find_one({"_id": body.user_id})
    if cred is None:
        raise HTTPException(status_code=401, detail="No OTP requested for this account.")

    if cred.get("otpAttempts", 0) >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many OTP attempts. Request a new OTP.")

    auth_credentials_collection().update_one(
        {"_id": body.user_id}, {"$inc": {"otpAttempts": 1}}
    )

    expires_at = cred.get("otpExpiresAt")
    if expires_at is None or datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=401, detail="OTP has expired. Request a new one.")

    if not cred.get("otpHash") or not pwd_context.verify(body.otp, cred["otpHash"]):
        raise HTTPException(status_code=401, detail="Invalid OTP.")

    auth_credentials_collection().update_one(
        {"_id": body.user_id},
        {"$set": {"otpHash": None, "otpExpiresAt": None, "otpAttempts": 0}},
    )

    user_data = {
        "sub": employee["employeeId"],
        "userType": "employee",
        "role": employee["role"],
        "employeeId": employee["employeeId"],
        "centreId": employee.get("centreId", ""),
        "employeeName": employee.get("name", ""),
    }
    token = _create_access_token(user_data)
    return AuthTokenResponse(accessToken=token, tokenType="bearer", user=user_data)


# ─── Current User Endpoint ───────────────────────────────────────────────────────

@router.get("/me")
def get_me(user: dict = Depends(require_auth)) -> dict:
    """Return the current authenticated user's identity from the JWT."""
    return {
        "sub": user.get("sub"),
        "userType": user.get("userType"),
        "role": user.get("role"),
        "farmerId": user.get("farmerId"),
        "farmerName": user.get("farmerName"),
        "employeeId": user.get("employeeId"),
        "centreId": user.get("centreId"),
        "employeeName": user.get("employeeName"),
    }


# ─── Demo Seed ───────────────────────────────────────────────────────────────────

def seed_demo_auth_credentials() -> None:
    """Seed auth credentials for existing demo farmers and employees.

    Only inserts credentials that do not already exist.
    Also creates the GOV-01 government officer demo account if needed.
    """
    coll = auth_credentials_collection()
    db = get_database()
    now = datetime.now(timezone.utc)

    # Seed farmer credentials
    farmers = list(db["farmers"].find())
    for farmer in farmers:
        fid = farmer["farmerId"]
        if coll.find_one({"_id": fid}) is None:
            coll.insert_one({
                "_id": fid,
                "userType": "farmer",
                "passwordHash": pwd_context.hash("kisan123"),
                "createdAt": now,
            })

    # Seed employee credentials
    employees = list(db["employees"].find())
    for emp in employees:
        eid = emp["employeeId"]
        if coll.find_one({"_id": eid}) is None:
            pw = "gov123" if emp.get("role") == "GOVERNMENT_OFFICER" else "officer123"
            coll.insert_one({
                "_id": eid,
                "userType": "employee",
                "passwordHash": pwd_context.hash(pw),
                "createdAt": now,
            })

    # Create GOV-01 government officer if not exists
    if db["employees"].find_one({"_id": "GOV-01"}) is None:
        # Create a minimal GOV-HQ centre if needed
        if db["centres"].find_one({"_id": "GOV-HQ"}) is None:
            db["centres"].insert_one({
                "_id": "GOV-HQ",
                "centreId": "GOV-HQ",
                "centreName": "Government Head Office",
                "state": "Madhya Pradesh",
                "district": "Bhopal",
                "area": "Government HQ",
                "address": "State Secretariat, Bhopal",
                "location": {"type": "Point", "coordinates": [77.4126, 23.2599]},
                "supportedCrops": [],
                "operatingDays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                "operatingHours": "09:00-17:00",
                "dailyProcurementCapacityKg": 0,
                "dailyQcCapacity": 0,
                "dailyWeighmentCapacity": 0,
                "status": "ACTIVE",
            })

        db["employees"].insert_one({
            "_id": "GOV-01",
            "employeeId": "GOV-01",
            "name": "District Collector Office",
            "phone": "+919999000001",
            "role": "GOVERNMENT_OFFICER",
            "centreId": "GOV-HQ",
            "status": "ACTIVE",
            "createdAt": now,
            "updatedAt": now,
        })

    # Ensure GOV-01 has auth credentials
    if coll.find_one({"_id": "GOV-01"}) is None:
        coll.insert_one({
            "_id": "GOV-01",
            "userType": "employee",
            "passwordHash": pwd_context.hash("gov123"),
            "createdAt": now,
        })

    # Ensure farmerId counter exists for signup
    if db["counters"].find_one({"_id": "farmerId"}) is None:
        # Set counter to a value above existing farmer IDs
        max_num = 0
        for f in farmers:
            try:
                num = int(f["farmerId"].split("-")[1])
                if num > max_num:
                    max_num = num
            except (IndexError, ValueError):
                pass
        db["counters"].insert_one({"_id": "farmerId", "seq": max(max_num, 200)})
