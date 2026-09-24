"""Reusable MongoDB connection utilities for the KisanOne API."""

import os

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

# Load variables from the project's .env file before reading them below.
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME")

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI is missing from the .env file.")

if not DATABASE_NAME:
    raise RuntimeError("DATABASE_NAME is missing from the .env file.")

# MongoClient manages a connection pool internally.  Keeping this one instance at
# module level means every request reuses that pool instead of opening a new client.
mongo_client = MongoClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=5000,
    tlsCAFile=certifi.where(),
)
db: Database = mongo_client[DATABASE_NAME]


def get_database() -> Database:
    """Return the shared KisanOne MongoDB database instance."""
    return db


def close_mongo_connection() -> None:
    """Close the shared MongoDB client during application shutdown."""
    mongo_client.close()
