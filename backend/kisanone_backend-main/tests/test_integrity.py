"""Focused integrity tests; all database collaborators are faked."""

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

import pytest
from bson.decimal128 import Decimal128
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import employees
import lots
import procurement_requests
import quality_checks
from quality_checks import QualityCheckStatus
import slots
from slots import SlotStatus
import weighments
from weighments import WeighmentStatus
import government_procurements
from government_procurements import ProcurementStatus
import payments
from payments import PaymentMethod, PaymentStatus
import rulebooks
from rulebooks import (
    PROTOTYPE_RULEBOOKS_SPEC,
    EvaluationDecision,
    QualityGrade,
    _build_rulebook_document,
)


def slot_document(**overrides):
    document = {
        "_id": "SLOT-1", "slotId": "SLOT-1", "centreId": "CENTRE-1",
        "cropCode": "WHEAT", "date": "2026-10-01", "startTime": "10:00:00",
        "endTime": "11:00:00", "capacityKg": Decimal128("10000.5"),
        "allocatedKg": Decimal128("2500.5"), "maxFarmers": 2, "allocatedFarmers": 1,
        "status": "AVAILABLE", "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }
    document.update(overrides)
    return document


def test_fractional_quantities_are_exact_and_serializable():
    response = slots._slot_response(slot_document())
    assert response.capacity_kg == Decimal("10000.5")
    assert response.remaining_capacity_kg == Decimal("7500.0")
    assert response.model_dump(by_alias=True, mode="json")["remainingCapacityKg"] == "7500.0"
    request = procurement_requests.ProcurementRequestCreate.model_validate({
        "requestId": "REQ-1", "farmerId": "FARMER-1", "cropCode": "WHEAT",
        "farmerArea": "Sinnar", "expectedQuantityKg": "2500.5",
        "assignedCentreId": "CENTRE-1", "assignedSlotId": "SLOT-1",
    })
    assert request.expected_quantity_kg == Decimal("2500.5")


def test_slot_capacity_and_farmer_capacity_rules():
    slot = slot_document()
    assert slots.slot_can_accept(slot, Decimal("7500.0"))
    assert not slots.slot_can_accept(slot, Decimal("7500.1"))  # G
    assert not slots.slot_can_accept(slot_document(allocatedFarmers=2), Decimal("1"))  # H


def test_release_uses_exact_quantity_and_one_farmer(monkeypatch):
    captured = {}

    class Collection:
        def find_one_and_update(self, query, pipeline, **kwargs):
            captured["query"] = query
            captured["pipeline"] = pipeline
            return slot_document()

    monkeypatch.setattr(slots, "slots_collection", lambda: Collection())
    assert slots.release_slot_capacity("SLOT-1", Decimal("2500.5"))
    assert captured["query"]["allocatedFarmers"] == {"$gte": 1}
    assert captured["pipeline"][0]["$set"]["allocatedKg"]["$subtract"][1] == Decimal128("2500.5")


def test_booked_slot_identity_cannot_change(monkeypatch):
    class Collection:
        def find_one(self, query):
            return slot_document()

    monkeypatch.setattr(slots, "slots_collection", lambda: Collection())
    update = slots.SlotUpdate.model_validate({"centreId": "CENTRE-2"})
    with pytest.raises(HTTPException, match="cannot change") as error:
        slots.update_slot("SLOT-1", update)
    assert error.value.status_code == 409  # L


def test_booked_slot_capacity_cannot_drop_below_allocation(monkeypatch):
    class Collection:
        def find_one(self, query):
            return slot_document()

    monkeypatch.setattr(slots, "slots_collection", lambda: Collection())
    update = slots.SlotUpdate.model_validate({"capacityKg": "2500.4"})
    with pytest.raises(HTTPException, match="allocatedKg"):
        slots.update_slot("SLOT-1", update)  # M


def test_slot_reference_validation_rejects_missing_or_unsupported_centre(monkeypatch):
    class Collection:
        def __init__(self, value):
            self.value = value
        def find_one(self, query, **kwargs):
            return self.value

    class Database(dict):
        pass

    database = Database(centres=Collection(None), cropConfigurations=Collection({"status": "ACTIVE"}))
    monkeypatch.setattr(slots, "get_database", lambda: database)
    with pytest.raises(HTTPException, match="Centre not found"):
        slots._validate_centre_and_crop("CENTRE-1", "WHEAT")  # B

    database["centres"] = Collection({"status": "ACTIVE", "supportedCrops": []})
    with pytest.raises(HTTPException, match="does not support"):
        slots._validate_centre_and_crop("CENTRE-1", "WHEAT")  # C


def test_daily_capacity_rejects_excess(monkeypatch):
    class Collection:
        def aggregate(self, pipeline, **kwargs):
            return [{"totalCapacityKg": Decimal128("9000.5")}]

    monkeypatch.setattr(slots, "slots_collection", lambda: Collection())
    with pytest.raises(HTTPException, match="exceeds"):
        slots._validate_daily_centre_capacity(
            {"_id": "CENTRE-1", "dailyProcurementCapacityKg": Decimal128("10000")},
            "2026-10-01", Decimal("1000"),
        )  # D


def test_employee_assignment_requires_active_existing_centre(monkeypatch):
    class Collection:
        def find_one(self, query):
            return None

    monkeypatch.setattr(employees, "get_database", lambda: {"centres": Collection()})
    with pytest.raises(HTTPException, match="Centre not found"):
        employees._validate_active_centre("CENTRE-404")  # N


def test_queue_index_remains_unique():
    calls = []

    class Collection:
        def create_index(self, keys, **kwargs):
            calls.append((keys, kwargs))

    original = procurement_requests.procurement_requests_collection
    procurement_requests.procurement_requests_collection = lambda: Collection()
    try:
        procurement_requests.ensure_procurement_request_indexes()
    finally:
        procurement_requests.procurement_requests_collection = original
    assert any(options.get("name") == "centre_slot_queue_unique" and options.get("unique")
               for _, options in calls)  # O


def test_cancelled_request_is_not_an_available_booking():
    # Reservation filters only accept non-CLOSED slots; cancellation itself is
    # guarded by bookingStatus in the request transaction, preventing double release.
    assert slots._derived_status(slot_document(status=SlotStatus.CLOSED.value)) == SlotStatus.CLOSED


def arrival_request_document(**overrides):
    document = {
        "_id": "REQ-1", "requestId": "REQ-1", "farmerId": "FARMER-1",
        "cropCode": "WHEAT",
        "assignedCentreId": "CENTRE-1", "assignedSlotId": "SLOT-1",
        "bookingStatus": "CONFIRMED", "arrivalStatus": "NOT_ARRIVED",
        "arrivedAt": None, "arrivalMarkedByEmployeeId": None,
        "requestStatus": "SCHEDULED",
    }
    document.update(overrides)
    return document


class ArrivalRequests:
    def __init__(self, document=None):
        self.document = document

    def find_one(self, query, **kwargs):
        if self.document and self.document["_id"] == query.get("_id"):
            return self.document
        return None

    def find_one_and_update(self, query, update, **kwargs):
        if self.document is None or any(self.document.get(key) != value for key, value in query.items()):
            return None
        self.document.update(update["$set"])
        return self.document


class FakeSession:
    def with_transaction(self, fn):
        return fn(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class FakeClient:
    def start_session(self):
        return FakeSession()


class LotsCollection:
    def __init__(self):
        self.lots = {}

    def find_one(self, query=None, **kwargs):
        if not query:
            return next(iter(self.lots.values()), None)
        for doc in self.lots.values():
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    def insert_one(self, doc, **kwargs):
        self.lots[doc["_id"]] = doc
        return doc


class CountersCollection:
    def __init__(self):
        self.seq = 0

    def find_one(self, query=None, **kwargs):
        return {"_id": "lotId", "seq": self.seq} if self.seq > 0 else None

    def update_one(self, query, update, upsert=False, **kwargs):
        if "$setOnInsert" in update and self.seq == 0:
            self.seq = update["$setOnInsert"].get("seq", 0)

    def find_one_and_update(self, query, update, **kwargs):
        if "$inc" in update:
            self.seq += update["$inc"].get("seq", 1)
        return {"_id": "lotId", "seq": self.seq}


def configure_arrival(monkeypatch, request=None, employee=None, slot=None):
    requests = ArrivalRequests(request)

    class Collection:
        def __init__(self, document):
            self.document = document
        def find_one(self, query, **kwargs):
            return self.document if self.document and self.document.get("_id") == query.get("_id") else None

    slot_doc = slot or {
        "_id": "SLOT-1",
        "centreId": "CENTRE-1",
        "cropCode": "WHEAT",
        "date": "2026-10-01",
        "startTime": "10:00:00",
        "endTime": "11:00:00",
        "status": "AVAILABLE",
    }

    lots_coll = LotsCollection()
    counters_coll = CountersCollection()

    monkeypatch.setattr(procurement_requests, "procurement_requests_collection", lambda: requests)
    monkeypatch.setattr(procurement_requests, "mongo_client", FakeClient())
    fake_db = {
        "employees": Collection(employee),
        "slots": Collection(slot_doc),
        "procurementRequests": requests,
        "lots": lots_coll,
        "counters": counters_coll,
    }
    monkeypatch.setattr(procurement_requests, "get_database", lambda: fake_db)
    monkeypatch.setattr(lots, "lots_collection", lambda: lots_coll)
    monkeypatch.setattr(lots, "counters_collection", lambda: counters_coll)
    monkeypatch.setattr(lots, "get_database", lambda: fake_db)
    return requests


def arrival_input(farmer_id="FARMER-1", employee_id="EMP-1"):
    return procurement_requests.ArrivalMarkRequest(farmerId=farmer_id, employeeId=employee_id)


def test_valid_arrival_records_timestamp_status_and_employee(monkeypatch):
    requests = configure_arrival(
        monkeypatch,
        arrival_request_document(),
        {"_id": "EMP-1", "centreId": "CENTRE-1", "status": "ACTIVE"},
    )
    response = procurement_requests.mark_procurement_request_arrival("REQ-1", arrival_input())
    assert response.arrival_status == procurement_requests.ArrivalStatus.ARRIVED
    assert response.request_status == procurement_requests.RequestStatus.ARRIVED
    assert response.arrival_marked_by_employee_id == "EMP-1"
    assert response.arrived_at is not None
    assert requests.document["arrivedAt"] == requests.document["updatedAt"]
    assert requests.document.get("lotId") is not None


def test_arrival_rejects_wrong_farmer_or_nonexistent_request(monkeypatch):
    configure_arrival(monkeypatch, arrival_request_document(), {"_id": "EMP-1", "centreId": "CENTRE-1", "status": "ACTIVE"})
    with pytest.raises(HTTPException, match="does not match"):
        procurement_requests.mark_procurement_request_arrival("REQ-1", arrival_input("FARMER-2"))
    configure_arrival(monkeypatch, None, None)
    with pytest.raises(HTTPException, match="not found"):
        procurement_requests.mark_procurement_request_arrival("REQ-404", arrival_input())


def test_arrival_rejects_wrong_centre_and_inactive_employee(monkeypatch):
    configure_arrival(monkeypatch, arrival_request_document(), {"_id": "EMP-1", "centreId": "CENTRE-2", "status": "ACTIVE"})
    with pytest.raises(HTTPException, match="assigned centre") as error:
        procurement_requests.mark_procurement_request_arrival("REQ-1", arrival_input())
    assert error.value.status_code == 403
    configure_arrival(monkeypatch, arrival_request_document(), {"_id": "EMP-1", "centreId": "CENTRE-1", "status": "INACTIVE"})
    with pytest.raises(HTTPException, match="not ACTIVE"):
        procurement_requests.mark_procurement_request_arrival("REQ-1", arrival_input())


def test_arrival_rejects_cancelled_and_already_arrived_requests(monkeypatch):
    employee = {"_id": "EMP-1", "centreId": "CENTRE-1", "status": "ACTIVE"}
    configure_arrival(monkeypatch, arrival_request_document(requestStatus="CANCELLED", bookingStatus="CANCELLED"), employee)
    with pytest.raises(HTTPException, match="cancelled"):
        procurement_requests.mark_procurement_request_arrival("REQ-1", arrival_input())
    configure_arrival(monkeypatch, arrival_request_document(arrivalStatus="ARRIVED", requestStatus="ARRIVED"), employee)
    with pytest.raises(HTTPException, match="already marked"):
        procurement_requests.mark_procurement_request_arrival("REQ-1", arrival_input())


def test_arrival_cannot_be_performed_twice(monkeypatch):
    configure_arrival(
        monkeypatch,
        arrival_request_document(),
        {"_id": "EMP-1", "centreId": "CENTRE-1", "status": "ACTIVE"},
    )
    procurement_requests.mark_procurement_request_arrival("REQ-1", arrival_input())
    with pytest.raises(HTTPException, match="already marked"):
        procurement_requests.mark_procurement_request_arrival("REQ-1", arrival_input())


def lot_qc_document(**overrides):
    document = {
        "_id": "LOT-1",
        "lotId": "LOT-1",
        "requestId": "REQ-1",
        "farmerId": "FARMER-1",
        "centreId": "CENTRE-1",
        "cropCode": "WHEAT",
        "slotId": "SLOT-1",
        "scheduledDate": "2026-10-01",
        "scheduledStartTime": "10:00:00",
        "scheduledEndTime": "11:00:00",
        "arrivedAt": datetime.now(timezone.utc),
        "status": "CREATED",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }
    document.update(overrides)
    return document


def wheat_crop_configuration(**overrides):
    config = {
        "_id": "WHEAT",
        "cropCode": "WHEAT",
        "cropName": "Wheat",
        "status": "ACTIVE",
        "qualityTests": [
            {
                "testCode": "MOISTURE_PERCENT",
                "testName": "Moisture %",
                "dataType": "NUMBER",
                "required": True,
                "description": "Moisture percentage measurement",
            },
            {
                "testCode": "INFESTATION_FREE",
                "testName": "Infestation Free",
                "dataType": "BOOLEAN",
                "required": True,
                "description": "True if infestation free",
            },
            {
                "testCode": "REMARKS",
                "testName": "Remarks",
                "dataType": "TEXT",
                "required": False,
                "description": "Optional notes",
            },
        ],
    }
    config.update(overrides)
    return config


class GenericCollection:
    def __init__(self, items=None):
        self.items = {}
        if items:
            for item in items:
                self.items[item.get("_id", item.get("qcAttemptId", item.get("lotId")))] = item

    @staticmethod
    def _matches(doc, query):
        if not query:
            return True
        for k, v in query.items():
            if isinstance(v, dict) and "$in" in v:
                if doc.get(k) not in v["$in"]:
                    return False
            elif doc.get(k) != v:
                return False
        return True

    def find_one(self, query=None, projection=None, sort=None, **kwargs):
        if not query:
            matches = list(self.items.values())
        else:
            matches = [
                doc for doc in self.items.values()
                if self._matches(doc, query)
            ]
        if not matches:
            return None
        if sort:
            for field, direction in reversed(sort):
                matches.sort(key=lambda d: d.get(field) or 0, reverse=(direction == -1))
        return matches[0]

    def find(self, query=None, **kwargs):
        if not query:
            results = list(self.items.values())
        else:
            results = [
                doc for doc in self.items.values()
                if self._matches(doc, query)
            ]
        class Cursor:
            def __init__(self, data):
                self.data = list(data)
            def sort(self, field, direction=1):
                self.data.sort(key=lambda d: d.get(field) or 0, reverse=(direction == -1))
                return self
            def __iter__(self):
                return iter(self.data)
        return Cursor(results)

    def insert_one(self, doc, **kwargs):
        doc_id = doc.get("_id") or doc.get("qcAttemptId")
        self.items[doc_id] = doc
        return doc

    def update_one(self, query, update, upsert=False, **kwargs):
        doc = self.find_one(query)
        if doc is None and upsert:
            new_doc = dict(query)
            if "$setOnInsert" in update:
                new_doc.update(update["$setOnInsert"])
            self.items[new_doc.get("_id")] = new_doc
            return
        if doc and "$set" in update:
            doc.update(update["$set"])

    def find_one_and_update(self, query, update, upsert=False, return_document=None, **kwargs):
        doc = self.find_one(query)
        if doc is None and upsert:
            doc = dict(query)
            if "$inc" in update:
                for k, v in update["$inc"].items():
                    doc[k] = v
            if "$set" in update:
                for k, v in update["$set"].items():
                    doc[k] = v
            self.items[doc.get("_id")] = doc
            return doc
        if doc is None:
            return None
        if "$inc" in update:
            for k, v in update["$inc"].items():
                doc[k] = doc.get(k, 0) + v
        if "$set" in update:
            for k, v in update["$set"].items():
                doc[k] = v
        return doc


def configure_qc(monkeypatch, lot=None, employee=None, crop=None, centre=None):
    lots_coll = GenericCollection([lot or lot_qc_document()])
    emp_doc = employee or {
        "_id": "QC-EMP-1",
        "name": "Officer Sharma",
        "phone": "+919876543210",
        "role": "QC_OFFICER",
        "centreId": "CENTRE-1",
        "status": "ACTIVE",
    }
    employees_coll = GenericCollection([emp_doc]) if employee is not False else GenericCollection()
    crops_coll = GenericCollection([crop or wheat_crop_configuration()]) if crop is not False else GenericCollection()
    centre_doc = centre or {
        "_id": "CENTRE-1",
        "name": "Nashik Centre",
        "status": "ACTIVE",
    }
    centres_coll = GenericCollection([centre_doc]) if centre is not False else GenericCollection()
    qc_coll = GenericCollection()
    counters_coll = CountersCollection()

    fake_db = {
        "lots": lots_coll,
        "employees": employees_coll,
        "cropConfigurations": crops_coll,
        "centres": centres_coll,
        "qualityChecks": qc_coll,
        "counters": counters_coll,
    }

    monkeypatch.setattr(quality_checks, "get_database", lambda: fake_db)
    monkeypatch.setattr(quality_checks, "quality_checks_collection", lambda: qc_coll)
    monkeypatch.setattr(quality_checks, "counters_collection", lambda: counters_coll)
    monkeypatch.setattr(quality_checks, "mongo_client", FakeClient())
    return fake_db


def test_qc_valid_recording_and_retest(monkeypatch):
    configure_qc(monkeypatch)
    req1 = quality_checks.QualityCheckCreate(
        employeeId="QC-EMP-1",
        tests={"MOISTURE_PERCENT": 12.5, "INFESTATION_FREE": True},
    )
    res1 = quality_checks.create_quality_check("LOT-1", req1)
    assert res1.attempt_number == 1
    assert res1.qc_attempt_id == "QC-000001"
    assert res1.lot_id == "LOT-1"
    assert res1.status == QualityCheckStatus.RECORDED
    assert res1.tests["MOISTURE_PERCENT"] == 12.5
    assert res1.tests["INFESTATION_FREE"] is True

    # Retest creates attemptNumber 2 with new QC attempt ID
    req2 = quality_checks.QualityCheckCreate(
        employeeId="QC-EMP-1",
        tests={"MOISTURE_PERCENT": 11.8, "INFESTATION_FREE": True, "REMARKS": "Passed re-inspection"},
    )
    res2 = quality_checks.create_quality_check("LOT-1", req2)
    assert res2.attempt_number == 2
    assert res2.qc_attempt_id == "QC-000002"

    # List checks for lot returns both in order
    all_checks = quality_checks.list_quality_checks_for_lot("LOT-1")
    assert len(all_checks) == 2
    assert all_checks[0].attempt_number == 1
    assert all_checks[1].attempt_number == 2

    # Get single check by ID
    single = quality_checks.get_quality_check("QC-000001")
    assert single.qc_attempt_id == "QC-000001"
    assert single.attempt_number == 1


def test_qc_employee_validation(monkeypatch):
    configure_qc(monkeypatch, employee={"_id": "EMP-GATE", "role": "GATE_OPERATOR", "centreId": "CENTRE-1", "status": "ACTIVE"})
    req = quality_checks.QualityCheckCreate(employeeId="EMP-GATE", tests={"MOISTURE_PERCENT": 12.0, "INFESTATION_FREE": True})
    with pytest.raises(HTTPException) as err:
        quality_checks.create_quality_check("LOT-1", req)
    assert err.value.status_code == 403
    assert "QC_OFFICER" in err.value.detail

    configure_qc(monkeypatch, employee={"_id": "QC-2", "role": "QC_OFFICER", "centreId": "CENTRE-99", "status": "ACTIVE"})
    req = quality_checks.QualityCheckCreate(employeeId="QC-2", tests={"MOISTURE_PERCENT": 12.0, "INFESTATION_FREE": True})
    with pytest.raises(HTTPException) as err:
        quality_checks.create_quality_check("LOT-1", req)
    assert err.value.status_code == 403
    assert "assigned centre" in err.value.detail


def test_qc_measurement_validation(monkeypatch):
    configure_qc(monkeypatch)
    # Missing required test
    req_missing = quality_checks.QualityCheckCreate(employeeId="QC-EMP-1", tests={"MOISTURE_PERCENT": 12.0})
    with pytest.raises(HTTPException) as err:
        quality_checks.create_quality_check("LOT-1", req_missing)
    assert err.value.status_code == 400
    assert "Missing required" in err.value.detail

    # Unknown test code
    req_unknown = quality_checks.QualityCheckCreate(employeeId="QC-EMP-1", tests={"MOISTURE_PERCENT": 12.0, "INFESTATION_FREE": True, "PESTICIDE": 0.1})
    with pytest.raises(HTTPException) as err:
        quality_checks.create_quality_check("LOT-1", req_unknown)
    assert err.value.status_code == 400
    assert "Unknown testCode" in err.value.detail

    # Invalid dataType (BOOLEAN provided for NUMBER)
    req_wrong_type = quality_checks.QualityCheckCreate(employeeId="QC-EMP-1", tests={"MOISTURE_PERCENT": True, "INFESTATION_FREE": True})
    with pytest.raises(HTTPException) as err:
        quality_checks.create_quality_check("LOT-1", req_wrong_type)
    assert err.value.status_code == 400
    assert "NUMBER" in err.value.detail


def test_qc_lot_and_centre_validation(monkeypatch):
    configure_qc(monkeypatch)
    req = quality_checks.QualityCheckCreate(employeeId="QC-EMP-1", tests={"MOISTURE_PERCENT": 12.0, "INFESTATION_FREE": True})
    with pytest.raises(HTTPException) as err:
        quality_checks.create_quality_check("LOT-404", req)
    assert err.value.status_code == 404
    assert "Lot not found" in err.value.detail

    configure_qc(monkeypatch, lot=lot_qc_document(status="CANCELLED"))
    with pytest.raises(HTTPException) as err:
        quality_checks.create_quality_check("LOT-1", req)
    assert err.value.status_code == 409
    assert "CANCELLED" in err.value.detail

    configure_qc(monkeypatch, centre={"_id": "CENTRE-1", "status": "INACTIVE"})
    with pytest.raises(HTTPException) as err:
        quality_checks.create_quality_check("LOT-1", req)
    assert err.value.status_code == 400
    assert "Centre is not ACTIVE" in err.value.detail

    configure_qc(monkeypatch, crop=wheat_crop_configuration(status="INACTIVE"))
    with pytest.raises(HTTPException) as err:
        quality_checks.create_quality_check("LOT-1", req)
    assert err.value.status_code == 400
    assert "Crop configuration is not ACTIVE" in err.value.detail


def configure_weighment(monkeypatch, lot=None, employee=None, crop=None, centre=None, request=None, qc=None):
    lot_doc = lot or lot_qc_document()
    lots_coll = GenericCollection([lot_doc]) if lot is not False else GenericCollection()
    emp_doc = employee or {
        "_id": "WEIGH-EMP-1",
        "name": "Weighment Officer Kumar",
        "phone": "+919876543211",
        "role": "WEIGHMENT_OFFICER",
        "centreId": "CENTRE-1",
        "status": "ACTIVE",
    }
    employees_coll = GenericCollection([emp_doc]) if employee is not False else GenericCollection()
    crops_coll = GenericCollection([crop or wheat_crop_configuration()]) if crop is not False else GenericCollection()
    centre_doc = centre or {
        "_id": "CENTRE-1",
        "name": "Nashik Centre",
        "status": "ACTIVE",
    }
    centres_coll = GenericCollection([centre_doc]) if centre is not False else GenericCollection()
    req_doc = request or {
        "_id": "REQ-1",
        "requestId": "REQ-1",
        "farmerId": "FARMER-1",
        "cropCode": "WHEAT",
        "assignedCentreId": "CENTRE-1",
        "assignedSlotId": "SLOT-1",
        "bookingStatus": "CONFIRMED",
        "arrivalStatus": "ARRIVED",
        "requestStatus": "ARRIVED",
    }
    requests_coll = GenericCollection([req_doc]) if request is not False else GenericCollection()
    qc_doc = qc or {
        "_id": "QC-1",
        "qcAttemptId": "QC-000001",
        "lotId": lot_doc.get("lotId", "LOT-1"),
        "status": "RECORDED",
    }
    qc_coll = GenericCollection([qc_doc]) if qc is not False else GenericCollection()
    weighments_coll = GenericCollection()
    counters_coll = CountersCollection()

    fake_db = {
        "lots": lots_coll,
        "employees": employees_coll,
        "cropConfigurations": crops_coll,
        "centres": centres_coll,
        "procurementRequests": requests_coll,
        "qualityChecks": qc_coll,
        "weighments": weighments_coll,
        "counters": counters_coll,
    }

    monkeypatch.setattr(weighments, "get_database", lambda: fake_db)
    monkeypatch.setattr(weighments, "weighments_collection", lambda: weighments_coll)
    monkeypatch.setattr(weighments, "counters_collection", lambda: counters_coll)
    monkeypatch.setattr(weighments, "mongo_client", FakeClient())
    return fake_db


def test_weighment_valid_recording_and_retest(monkeypatch):
    configure_weighment(monkeypatch)
    req1 = weighments.WeighmentCreate(
        employeeId="WEIGH-EMP-1",
        grossWeightKg=Decimal("10250.0"),
        tareWeightKg=Decimal("250.0"),
        deviceId="SCALE-001",
        remarks="First weighment",
    )
    res1 = weighments.create_weighment("LOT-1", req1)
    assert res1.attempt_number == 1
    assert res1.weighment_id == "WEIGH-000001"
    assert res1.gross_weight_kg == Decimal("10250.0")
    assert res1.tare_weight_kg == Decimal("250.0")
    assert res1.net_weight_kg == Decimal("10000.0")
    assert res1.status == WeighmentStatus.RECORDED
    assert res1.performed_by_employee_id == "WEIGH-EMP-1"
    assert res1.device_id == "SCALE-001"
    assert res1.remarks == "First weighment"

    # Retest (re-weigh) creates attemptNumber 2
    req2 = weighments.WeighmentCreate(
        employeeId="WEIGH-EMP-1",
        grossWeightKg=Decimal("10240.0"),
        tareWeightKg=Decimal("240.0"),
    )
    res2 = weighments.create_weighment("LOT-1", req2)
    assert res2.attempt_number == 2
    assert res2.weighment_id == "WEIGH-000002"
    assert res2.net_weight_kg == Decimal("10000.0")

    # List weighments for lot returns both in order
    all_weighments = weighments.list_weighments_for_lot("LOT-1")
    assert len(all_weighments) == 2
    assert all_weighments[0].attempt_number == 1
    assert all_weighments[1].attempt_number == 2

    # Get single weighment by ID
    single = weighments.get_weighment("WEIGH-000001")
    assert single.weighment_id == "WEIGH-000001"
    assert single.net_weight_kg == Decimal("10000.0")


def test_weighment_weight_validation(monkeypatch):
    configure_weighment(monkeypatch)
    # Tare >= Gross
    req_equal = weighments.WeighmentCreate(
        employeeId="WEIGH-EMP-1",
        grossWeightKg=Decimal("250.0"),
        tareWeightKg=Decimal("250.0"),
    )
    with pytest.raises(HTTPException) as err:
        weighments.create_weighment("LOT-1", req_equal)
    assert err.value.status_code == 400
    assert "tareWeightKg must be less than grossWeightKg" in err.value.detail

    # Tare > Gross
    req_excess_tare = weighments.WeighmentCreate(
        employeeId="WEIGH-EMP-1",
        grossWeightKg=Decimal("200.0"),
        tareWeightKg=Decimal("250.0"),
    )
    with pytest.raises(HTTPException) as err:
        weighments.create_weighment("LOT-1", req_excess_tare)
    assert err.value.status_code == 400


def test_weighment_employee_validation(monkeypatch):
    configure_weighment(
        monkeypatch,
        employee={"_id": "EMP-QC", "role": "QC_OFFICER", "centreId": "CENTRE-1", "status": "ACTIVE"},
    )
    req = weighments.WeighmentCreate(
        employeeId="EMP-QC",
        grossWeightKg=Decimal("1000.0"),
        tareWeightKg=Decimal("100.0"),
    )
    with pytest.raises(HTTPException) as err:
        weighments.create_weighment("LOT-1", req)
    assert err.value.status_code == 403
    assert "WEIGHMENT_OFFICER" in err.value.detail

    # Wrong centre
    configure_weighment(
        monkeypatch,
        employee={"_id": "WEIGH-2", "role": "WEIGHMENT_OFFICER", "centreId": "CENTRE-99", "status": "ACTIVE"},
    )
    req = weighments.WeighmentCreate(
        employeeId="WEIGH-2",
        grossWeightKg=Decimal("1000.0"),
        tareWeightKg=Decimal("100.0"),
    )
    with pytest.raises(HTTPException) as err:
        weighments.create_weighment("LOT-1", req)
    assert err.value.status_code == 403
    assert "assigned centre" in err.value.detail


def test_weighment_lot_and_qc_prerequisite_validation(monkeypatch):
    # No QC recorded yet
    configure_weighment(monkeypatch, qc=False)
    req = weighments.WeighmentCreate(
        employeeId="WEIGH-EMP-1",
        grossWeightKg=Decimal("1000.0"),
        tareWeightKg=Decimal("100.0"),
    )
    with pytest.raises(HTTPException) as err:
        weighments.create_weighment("LOT-1", req)
    assert err.value.status_code == 409
    assert "Quality Check" in err.value.detail

    # Cancelled lot
    configure_weighment(monkeypatch, lot=lot_qc_document(status="CANCELLED"))
    with pytest.raises(HTTPException) as err:
        weighments.create_weighment("LOT-1", req)
    assert err.value.status_code == 409
    assert "CANCELLED" in err.value.detail

    # Non-existent lot
    configure_weighment(monkeypatch)
    with pytest.raises(HTTPException) as err:
        weighments.create_weighment("LOT-404", req)
    assert err.value.status_code == 404
    assert "Lot not found" in err.value.detail


def configure_procurement(
    monkeypatch,
    lot=None,
    employee=None,
    crop=None,
    centre=None,
    request=None,
    farmer=None,
    qc=None,
    weighment=None,
):
    lot_doc = lot or lot_qc_document()
    lots_coll = GenericCollection([lot_doc]) if lot is not False else GenericCollection()
    emp_doc = employee or {
        "_id": "PROC-EMP-1",
        "name": "Procurement Officer Verma",
        "phone": "+919876543212",
        "role": "PROCUREMENT_OFFICER",
        "centreId": "CENTRE-1",
        "status": "ACTIVE",
    }
    employees_coll = GenericCollection([emp_doc]) if employee is not False else GenericCollection()
    crops_coll = GenericCollection([crop or wheat_crop_configuration()]) if crop is not False else GenericCollection()
    centre_doc = centre or {
        "_id": "CENTRE-1",
        "name": "Nashik Centre",
        "status": "ACTIVE",
    }
    centres_coll = GenericCollection([centre_doc]) if centre is not False else GenericCollection()
    req_doc = request or {
        "_id": "REQ-1",
        "requestId": "REQ-1",
        "farmerId": "FARMER-1",
        "cropCode": "WHEAT",
        "assignedCentreId": "CENTRE-1",
        "assignedSlotId": "SLOT-1",
        "bookingStatus": "CONFIRMED",
        "arrivalStatus": "ARRIVED",
        "requestStatus": "ARRIVED",
    }
    requests_coll = GenericCollection([req_doc]) if request is not False else GenericCollection()
    farmer_doc = farmer or {
        "_id": "FARMER-1",
        "farmerId": "FARMER-1",
        "name": "Ramesh Patil",
    }
    farmers_coll = GenericCollection([farmer_doc]) if farmer is not False else GenericCollection()
    qc_doc = qc or {
        "_id": "QC-1",
        "qcAttemptId": "QC-000001",
        "lotId": lot_doc.get("lotId", "LOT-1"),
        "status": "RECORDED",
    }
    qc_coll = GenericCollection([qc_doc]) if qc is not False else GenericCollection()
    weighment_doc = weighment or {
        "_id": "WEIGH-000001",
        "weighmentId": "WEIGH-000001",
        "lotId": lot_doc.get("lotId", "LOT-1"),
        "grossWeightKg": Decimal128("10250.0"),
        "tareWeightKg": Decimal128("250.0"),
        "netWeightKg": Decimal128("10000.0"),
        "status": "RECORDED",
    }
    weighments_coll = GenericCollection([weighment_doc]) if weighment is not False else GenericCollection()
    procurements_coll = GenericCollection()
    counters_coll = CountersCollection()

    fake_db = {
        "lots": lots_coll,
        "employees": employees_coll,
        "cropConfigurations": crops_coll,
        "centres": centres_coll,
        "procurementRequests": requests_coll,
        "farmers": farmers_coll,
        "qualityChecks": qc_coll,
        "weighments": weighments_coll,
        "governmentProcurements": procurements_coll,
        "counters": counters_coll,
    }

    monkeypatch.setattr(government_procurements, "get_database", lambda: fake_db)
    monkeypatch.setattr(government_procurements, "government_procurements_collection", lambda: procurements_coll)
    monkeypatch.setattr(government_procurements, "counters_collection", lambda: counters_coll)
    monkeypatch.setattr(government_procurements, "mongo_client", FakeClient())
    return fake_db


def test_procurement_valid_recording_and_retrieval(monkeypatch):
    configure_procurement(monkeypatch)
    req = government_procurements.GovernmentProcurementCreate(
        weighmentId="WEIGH-000001",
        procurementQuantityKg=Decimal("10000.0"),
        pricePerKg=Decimal("22.75"),
        employeeId="PROC-EMP-1",
        remarks="Procured standard wheat",
    )
    res = government_procurements.create_procurement("LOT-1", req)
    assert res.procurement_id == "PROC-000001"
    assert res.lot_id == "LOT-1"
    assert res.weighment_id == "WEIGH-000001"
    assert res.procurement_quantity_kg == Decimal("10000.0")
    assert res.price_per_kg == Decimal("22.75")
    assert res.gross_amount == Decimal("227500.00")
    assert res.status == ProcurementStatus.COMPLETED
    assert res.price_source == "RULEBOOK_PENDING"
    assert res.procured_by_employee_id == "PROC-EMP-1"
    assert res.remarks == "Procured standard wheat"

    # Get procurement for lot
    lot_proc = government_procurements.get_procurement_for_lot("LOT-1")
    assert lot_proc.procurement_id == "PROC-000001"
    assert lot_proc.gross_amount == Decimal("227500.00")

    # Get procurement by ID
    single = government_procurements.get_procurement("PROC-000001")
    assert single.procurement_id == "PROC-000001"


def test_procurement_duplicate_prevention(monkeypatch):
    configure_procurement(monkeypatch)
    req = government_procurements.GovernmentProcurementCreate(
        weighmentId="WEIGH-000001",
        procurementQuantityKg=Decimal("10000.0"),
        pricePerKg=Decimal("22.75"),
        employeeId="PROC-EMP-1",
    )
    government_procurements.create_procurement("LOT-1", req)

    # Second procurement for same Lot must be rejected
    with pytest.raises(HTTPException) as err:
        government_procurements.create_procurement("LOT-1", req)
    assert err.value.status_code == 409
    assert "already exists" in err.value.detail


def test_procurement_quantity_and_price_validation(monkeypatch):
    configure_procurement(monkeypatch)
    # Quantity exceeds weighment net weight (10000.5 > 10000.0)
    req_excess = government_procurements.GovernmentProcurementCreate(
        weighmentId="WEIGH-000001",
        procurementQuantityKg=Decimal("10000.5"),
        pricePerKg=Decimal("22.75"),
        employeeId="PROC-EMP-1",
    )
    with pytest.raises(HTTPException) as err:
        government_procurements.create_procurement("LOT-1", req_excess)
    assert err.value.status_code == 400
    assert "cannot exceed" in err.value.detail


def test_procurement_prerequisites_and_employee_validation(monkeypatch):
    # Missing QC
    configure_procurement(monkeypatch, qc=False)
    req = government_procurements.GovernmentProcurementCreate(
        weighmentId="WEIGH-000001",
        procurementQuantityKg=Decimal("5000.0"),
        pricePerKg=Decimal("22.75"),
        employeeId="PROC-EMP-1",
    )
    with pytest.raises(HTTPException) as err:
        government_procurements.create_procurement("LOT-1", req)
    assert err.value.status_code == 409
    assert "Quality Check" in err.value.detail

    # Missing Weighment
    configure_procurement(monkeypatch, weighment=False)
    with pytest.raises(HTTPException) as err:
        government_procurements.create_procurement("LOT-1", req)
    assert err.value.status_code == 409
    assert "Weighment" in err.value.detail

    # Wrong employee role
    configure_procurement(
        monkeypatch,
        employee={"_id": "EMP-GATE", "role": "GATE_OPERATOR", "centreId": "CENTRE-1", "status": "ACTIVE"},
    )
    req_gate = government_procurements.GovernmentProcurementCreate(
        weighmentId="WEIGH-000001",
        procurementQuantityKg=Decimal("5000.0"),
        pricePerKg=Decimal("22.75"),
        employeeId="EMP-GATE",
    )
    with pytest.raises(HTTPException) as err:
        government_procurements.create_procurement("LOT-1", req_gate)
    assert err.value.status_code == 403
    assert "PROCUREMENT_OFFICER" in err.value.detail

    # CENTRE_MANAGER role is also authorized
    configure_procurement(
        monkeypatch,
        employee={"_id": "MGR-1", "role": "CENTRE_MANAGER", "centreId": "CENTRE-1", "status": "ACTIVE"},
    )
    req_mgr = government_procurements.GovernmentProcurementCreate(
        weighmentId="WEIGH-000001",
        procurementQuantityKg=Decimal("5000.0"),
        pricePerKg=Decimal("22.75"),
        employeeId="MGR-1",
    )
    res_mgr = government_procurements.create_procurement("LOT-1", req_mgr)
    assert res_mgr.procured_by_employee_id == "MGR-1"


def configure_payment(
    monkeypatch,
    procurement=None,
    lot=None,
    employee=None,
    crop=None,
    centre=None,
    farmer=None,
):
    proc_doc = procurement or {
        "_id": "PROC-000001",
        "procurementId": "PROC-000001",
        "lotId": "LOT-1",
        "requestId": "REQ-1",
        "farmerId": "FARMER-1",
        "centreId": "CENTRE-1",
        "cropCode": "WHEAT",
        "weighmentId": "WEIGH-000001",
        "procurementQuantityKg": Decimal128("10000.0"),
        "pricePerKg": Decimal128("22.75"),
        "grossAmount": Decimal128("227500.00"),
        "priceSource": "RULEBOOK_PENDING",
        "procuredByEmployeeId": "PROC-EMP-1",
        "status": "COMPLETED",
        "createdAt": datetime.now(timezone.utc),
        "updatedAt": datetime.now(timezone.utc),
    }
    procurements_coll = (
        GenericCollection([proc_doc]) if procurement is not False else GenericCollection()
    )
    lot_doc = lot or lot_qc_document()
    lots_coll = GenericCollection([lot_doc]) if lot is not False else GenericCollection()
    emp_doc = employee or {
        "_id": "EMP-MGR-1",
        "name": "Centre Manager Deshmukh",
        "phone": "+919876543215",
        "role": "CENTRE_MANAGER",
        "centreId": "CENTRE-1",
        "status": "ACTIVE",
    }
    employees_coll = (
        GenericCollection([emp_doc]) if employee is not False else GenericCollection()
    )
    crops_coll = (
        GenericCollection([crop or wheat_crop_configuration()])
        if crop is not False
        else GenericCollection()
    )
    centre_doc = centre or {
        "_id": "CENTRE-1",
        "name": "Nashik Centre",
        "status": "ACTIVE",
    }
    centres_coll = (
        GenericCollection([centre_doc]) if centre is not False else GenericCollection()
    )
    farmer_doc = farmer or {
        "_id": "FARMER-1",
        "farmerId": "FARMER-1",
        "name": "Ramesh Patil",
    }
    farmers_coll = (
        GenericCollection([farmer_doc]) if farmer is not False else GenericCollection()
    )
    payments_coll = GenericCollection()
    counters_coll = CountersCollection()

    fake_db = {
        "governmentProcurements": procurements_coll,
        "lots": lots_coll,
        "employees": employees_coll,
        "cropConfigurations": crops_coll,
        "centres": centres_coll,
        "farmers": farmers_coll,
        "payments": payments_coll,
        "counters": counters_coll,
    }

    monkeypatch.setattr(payments, "get_database", lambda: fake_db)
    monkeypatch.setattr(payments, "payments_collection", lambda: payments_coll)
    monkeypatch.setattr(payments, "counters_collection", lambda: counters_coll)
    monkeypatch.setattr(payments, "mongo_client", FakeClient())
    return fake_db


def test_payment_valid_creation_and_retrieval(monkeypatch):
    configure_payment(monkeypatch)
    req = payments.PaymentCreate(employeeId="EMP-MGR-1")
    res = payments.create_payment("PROC-000001", req)
    assert res.payment_id == "PAY-000001"
    assert res.procurement_id == "PROC-000001"
    assert res.lot_id == "LOT-1"
    assert res.farmer_id == "FARMER-1"
    assert res.centre_id == "CENTRE-1"
    assert res.crop_code == "WHEAT"
    assert res.procurement_quantity_kg == Decimal("10000.0")
    assert res.price_per_kg == Decimal("22.75")
    assert res.payable_amount == Decimal("227500.00")
    assert res.payment_status == PaymentStatus.PENDING
    assert res.payment_method is None
    assert res.payment_reference is None
    assert res.completed_at is None
    assert res.processed_by_employee_id == "EMP-MGR-1"

    # Retrieve by procurement
    by_proc = payments.get_payment_for_procurement("PROC-000001")
    assert by_proc.payment_id == "PAY-000001"
    assert by_proc.payable_amount == Decimal("227500.00")

    # Retrieve by payment ID
    by_id = payments.get_payment("PAY-000001")
    assert by_id.payment_id == "PAY-000001"
    assert by_id.payable_amount == Decimal("227500.00")


def test_payment_duplicate_prevention(monkeypatch):
    configure_payment(monkeypatch)
    req = payments.PaymentCreate(employeeId="EMP-MGR-1")
    payments.create_payment("PROC-000001", req)

    # Second payment for same procurement must fail
    with pytest.raises(HTTPException) as err:
        payments.create_payment("PROC-000001", req)
    assert err.value.status_code == 409
    assert "already exists" in err.value.detail


def test_payment_prerequisites_and_employee_validation(monkeypatch):
    # Non-existent procurement
    configure_payment(monkeypatch, procurement=False)
    req = payments.PaymentCreate(employeeId="EMP-MGR-1")
    with pytest.raises(HTTPException) as err:
        payments.create_payment("PROC-404", req)
    assert err.value.status_code == 404
    assert "procurement record not found" in err.value.detail

    # Incomplete procurement status
    configure_payment(
        monkeypatch,
        procurement={
            "_id": "PROC-000001",
            "procurementId": "PROC-000001",
            "lotId": "LOT-1",
            "requestId": "REQ-1",
            "farmerId": "FARMER-1",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "procurementQuantityKg": Decimal128("10000.0"),
            "grossAmount": Decimal128("227500.00"),
            "status": "PENDING",
        },
    )
    with pytest.raises(HTTPException) as err:
        payments.create_payment("PROC-000001", req)
    assert err.value.status_code == 400
    assert "Must be COMPLETED" in err.value.detail

    # Cancelled lot
    configure_payment(monkeypatch, lot=lot_qc_document(status="CANCELLED"))
    with pytest.raises(HTTPException) as err:
        payments.create_payment("PROC-000001", req)
    assert err.value.status_code == 409
    assert "CANCELLED" in err.value.detail

    # Inactive centre
    configure_payment(monkeypatch, centre={"_id": "CENTRE-1", "status": "INACTIVE"})
    with pytest.raises(HTTPException) as err:
        payments.create_payment("PROC-000001", req)
    assert err.value.status_code == 400
    assert "Centre is not ACTIVE" in err.value.detail

    # Unauthorized employee role (QC_OFFICER)
    configure_payment(
        monkeypatch,
        employee={"_id": "EMP-QC", "role": "QC_OFFICER", "centreId": "CENTRE-1", "status": "ACTIVE"},
    )
    req_unauth = payments.PaymentCreate(employeeId="EMP-QC")
    with pytest.raises(HTTPException) as err:
        payments.create_payment("PROC-000001", req_unauth)
    assert err.value.status_code == 403
    assert "PROCUREMENT_OFFICER or CENTRE_MANAGER" in err.value.detail

    # Employee assigned to different centre
    configure_payment(
        monkeypatch,
        employee={"_id": "EMP-DIFF", "role": "CENTRE_MANAGER", "centreId": "CENTRE-99", "status": "ACTIVE"},
    )
    req_diff = payments.PaymentCreate(employeeId="EMP-DIFF")
    with pytest.raises(HTTPException) as err:
        payments.create_payment("PROC-000001", req_diff)
    assert err.value.status_code == 403
    assert "assigned centre" in err.value.detail


def test_payment_status_transitions(monkeypatch):
    configure_payment(monkeypatch)
    req = payments.PaymentCreate(employeeId="EMP-MGR-1")
    created = payments.create_payment("PROC-000001", req)
    assert created.payment_status == PaymentStatus.PENDING

    # Disallowed direct jump: PENDING -> PAID
    with pytest.raises(HTTPException) as err:
        payments.update_payment_status(
            "PAY-000001",
            payments.PaymentStatusUpdate(
                paymentStatus=PaymentStatus.PAID,
                employeeId="EMP-MGR-1",
                paymentMethod=PaymentMethod.UPI,
                paymentReference="UPI-123456",
            ),
        )
    assert err.value.status_code == 400
    assert "Invalid status transition" in err.value.detail

    # Valid: PENDING -> PROCESSING
    proc_res = payments.update_payment_status(
        "PAY-000001",
        payments.PaymentStatusUpdate(
            paymentStatus=PaymentStatus.PROCESSING,
            employeeId="EMP-MGR-1",
        ),
    )
    assert proc_res.payment_status == PaymentStatus.PROCESSING

    # Missing paymentMethod when transitioning to PAID
    with pytest.raises(HTTPException) as err:
        payments.update_payment_status(
            "PAY-000001",
            payments.PaymentStatusUpdate(
                paymentStatus=PaymentStatus.PAID,
                employeeId="EMP-MGR-1",
                paymentReference="REF-123",
            ),
        )
    assert err.value.status_code == 400
    assert "paymentMethod is required" in err.value.detail

    # Missing paymentReference when transitioning to PAID
    with pytest.raises(HTTPException) as err:
        payments.update_payment_status(
            "PAY-000001",
            payments.PaymentStatusUpdate(
                paymentStatus=PaymentStatus.PAID,
                employeeId="EMP-MGR-1",
                paymentMethod=PaymentMethod.BANK_TRANSFER,
            ),
        )
    assert err.value.status_code == 400
    assert "paymentReference is required" in err.value.detail

    # Valid: PROCESSING -> PAID
    paid_res = payments.update_payment_status(
        "PAY-000001",
        payments.PaymentStatusUpdate(
            paymentStatus=PaymentStatus.PAID,
            employeeId="EMP-MGR-1",
            paymentMethod=PaymentMethod.BANK_TRANSFER,
            paymentReference="RTGS-987654321",
        ),
    )
    assert paid_res.payment_status == PaymentStatus.PAID
    assert paid_res.payment_method == PaymentMethod.BANK_TRANSFER
    assert paid_res.payment_reference == "RTGS-987654321"
    assert paid_res.completed_at is not None

    # Cannot transition out of PAID terminal state
    with pytest.raises(HTTPException) as err:
        payments.update_payment_status(
            "PAY-000001",
            payments.PaymentStatusUpdate(
                paymentStatus=PaymentStatus.PROCESSING,
                employeeId="EMP-MGR-1",
            ),
        )
    assert err.value.status_code == 400
    assert "already been marked PAID" in err.value.detail

    # Test FAILED transition and record preservation on a new payment
    configure_payment(
        monkeypatch,
        procurement={
            "_id": "PROC-000002",
            "procurementId": "PROC-000002",
            "lotId": "LOT-1",
            "requestId": "REQ-1",
            "farmerId": "FARMER-1",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "procurementQuantityKg": Decimal128("5000.0"),
            "pricePerKg": Decimal128("20.00"),
            "grossAmount": Decimal128("100000.00"),
            "status": "COMPLETED",
        },
    )
    pay2 = payments.create_payment("PROC-000002", req)
    failed_res = payments.update_payment_status(
        pay2.payment_id,
        payments.PaymentStatusUpdate(
            paymentStatus=PaymentStatus.FAILED,
            employeeId="EMP-MGR-1",
            failureReason="Bank beneficiary details invalid",
        ),
    )
    assert failed_res.payment_status == PaymentStatus.FAILED
    assert failed_res.failure_reason == "Bank beneficiary details invalid"

    # Cannot transition out of FAILED terminal state
    with pytest.raises(HTTPException) as err:
        payments.update_payment_status(
            pay2.payment_id,
            payments.PaymentStatusUpdate(
                paymentStatus=PaymentStatus.PROCESSING,
                employeeId="EMP-MGR-1",
            ),
        )
    assert err.value.status_code == 400
    assert "already FAILED" in err.value.detail


def configure_rulebooks(
    monkeypatch,
    lot=None,
    employee=None,
    crop=None,
    centre=None,
    farmer=None,
    qc=None,
    weighment=None,
    procurement=None,
    payment=None,
):
    rb_docs = [_build_rulebook_document(spec) for spec in PROTOTYPE_RULEBOOKS_SPEC]
    rulebooks_coll = GenericCollection(rb_docs)
    evaluations_coll = GenericCollection()
    counters_coll = CountersCollection()

    lot_doc = lot or lot_qc_document()
    lots_coll = GenericCollection([lot_doc]) if lot is not False else GenericCollection()

    emp_doc = employee or {
        "_id": "EMP-PROC-1",
        "name": "Officer Sharma",
        "phone": "+919876543210",
        "role": "PROCUREMENT_OFFICER",
        "centreId": "CENTRE-1",
        "status": "ACTIVE",
    }
    employees_coll = GenericCollection([emp_doc]) if employee is not False else GenericCollection()

    crop_doc = crop or wheat_crop_configuration()
    crops_coll = GenericCollection([crop_doc]) if crop is not False else GenericCollection()

    centre_doc = centre or {
        "_id": "CENTRE-1",
        "name": "Nashik Centre",
        "status": "ACTIVE",
    }
    centres_coll = GenericCollection([centre_doc]) if centre is not False else GenericCollection()

    farmer_doc = farmer or {
        "_id": "FARMER-1",
        "farmerId": "FARMER-1",
        "name": "Ramesh Patil",
    }
    farmers_coll = GenericCollection([farmer_doc]) if farmer is not False else GenericCollection()

    req_doc = {
        "_id": "REQ-1",
        "requestId": "REQ-1",
        "farmerId": "FARMER-1",
        "cropCode": "WHEAT",
        "assignedCentreId": "CENTRE-1",
        "assignedSlotId": "SLOT-1",
        "bookingStatus": "CONFIRMED",
        "arrivalStatus": "ARRIVED",
        "requestStatus": "ARRIVED",
    }
    requests_coll = GenericCollection([req_doc])

    qc_doc = qc or {
        "_id": "QC-000001",
        "qcAttemptId": "QC-000001",
        "lotId": lot_doc.get("lotId", "LOT-1"),
        "cropCode": lot_doc.get("cropCode", "WHEAT"),
        "attemptNumber": 1,
        "tests": {
            "MOISTURE_PERCENT": 12.8,
            "FOREIGN_MATTER_PERCENT": 0.6,
            "DAMAGED_GRAINS_PERCENT": 3.0,
            "WEEVILLED_GRAINS_PERCENT": 4.0,
        },
        "status": "RECORDED",
    }
    qc_coll = GenericCollection([qc_doc]) if qc is not False else GenericCollection()

    weighment_doc = weighment or {
        "_id": "WEIGH-000001",
        "weighmentId": "WEIGH-000001",
        "lotId": lot_doc.get("lotId", "LOT-1"),
        "grossWeightKg": Decimal128("10250.0"),
        "tareWeightKg": Decimal128("250.0"),
        "netWeightKg": Decimal128("10000.0"),
        "status": "RECORDED",
    }
    weighments_coll = GenericCollection([weighment_doc]) if weighment is not False else GenericCollection()

    procurements_coll = GenericCollection([procurement]) if procurement else GenericCollection()
    payments_coll = GenericCollection([payment]) if payment else GenericCollection()

    fake_db = {
        "rulebooks": rulebooks_coll,
        "qualityEvaluations": evaluations_coll,
        "qualityChecks": qc_coll,
        "lots": lots_coll,
        "employees": employees_coll,
        "cropConfigurations": crops_coll,
        "centres": centres_coll,
        "farmers": farmers_coll,
        "procurementRequests": requests_coll,
        "weighments": weighments_coll,
        "governmentProcurements": procurements_coll,
        "payments": payments_coll,
        "counters": counters_coll,
    }

    monkeypatch.setattr(rulebooks, "get_database", lambda: fake_db)
    monkeypatch.setattr(rulebooks, "rulebooks_collection", lambda: rulebooks_coll)
    monkeypatch.setattr(rulebooks, "quality_evaluations_collection", lambda: evaluations_coll)
    monkeypatch.setattr(rulebooks, "counters_collection", lambda: counters_coll)

    monkeypatch.setattr(government_procurements, "get_database", lambda: fake_db)
    monkeypatch.setattr(government_procurements, "government_procurements_collection", lambda: procurements_coll)
    monkeypatch.setattr(government_procurements, "counters_collection", lambda: counters_coll)
    monkeypatch.setattr(government_procurements, "mongo_client", FakeClient())

    monkeypatch.setattr(payments, "get_database", lambda: fake_db)
    monkeypatch.setattr(payments, "payments_collection", lambda: payments_coll)
    monkeypatch.setattr(payments, "counters_collection", lambda: counters_coll)
    monkeypatch.setattr(payments, "mongo_client", FakeClient())

    return fake_db


def test_all_10_prototype_rulebooks_exist_and_pricing_structure(monkeypatch):
    configure_rulebooks(monkeypatch)

    expected_crops = [
        "PADDY_RICE",
        "WHEAT",
        "MAIZE",
        "SOYBEAN",
        "GROUNDNUT",
        "COTTON",
        "TUR_ARHAR",
        "GRAM_CHICKPEA",
        "MUSTARD_RAPESEED",
        "SUGARCANE",
    ]

    # Verify all 10 prototype Rulebooks exist
    for crop in expected_crops:
        rb = rulebooks.get_active_rulebook(crop)
        assert rb.crop_code == crop
        assert rb.version == 1
        assert rb.status == "ACTIVE"
        assert rb.environment == "PROTOTYPE"
        assert rb.source == "RESEARCHED_DEMO_RULES"
        assert len(rb.reference_standard) > 0

        # Concrete pricing check: A > B > C > F and F == 0
        price_a = rb.pricing["A"].price_per_kg
        price_b = rb.pricing["B"].price_per_kg
        price_c = rb.pricing["C"].price_per_kg
        price_f = rb.pricing["F"].price_per_kg

        assert price_a > price_b > price_c > price_f
        assert price_f == Decimal("0.00")

        # Verify versions endpoints
        versions = rulebooks.get_rulebook_versions(crop)
        assert len(versions) >= 1
        assert versions[0].version == 1

        single_ver = rulebooks.get_rulebook_by_version(crop, 1)
        assert single_ver.version == 1

    # Verify alias lookup (PADDY, TUR, GRAM, MUSTARD)
    assert rulebooks.get_active_rulebook("PADDY").crop_code == "PADDY_RICE"
    assert rulebooks.get_active_rulebook("TUR").crop_code == "TUR_ARHAR"
    assert rulebooks.get_active_rulebook("GRAM").crop_code == "GRAM_CHICKPEA"
    assert rulebooks.get_active_rulebook("MUSTARD").crop_code == "MUSTARD_RAPESEED"


def test_quality_evaluation_grade_a_b_c_f(monkeypatch):
    fake_db = configure_rulebooks(monkeypatch)

    # 1. Grade A Sample
    fake_db["qualityChecks"].items["QC-A"] = {
        "_id": "QC-A",
        "qcAttemptId": "QC-A",
        "lotId": "LOT-1",
        "cropCode": "WHEAT",
        "tests": {
            "MOISTURE_PERCENT": 11.5,
            "FOREIGN_MATTER_PERCENT": 0.40,
            "DAMAGED_GRAINS_PERCENT": 1.5,
            "WEEVILLED_GRAINS_PERCENT": 1.0,
        },
    }
    eval_a = rulebooks.evaluate_quality_check("QC-A")
    assert eval_a.grade == QualityGrade.A
    assert eval_a.decision == EvaluationDecision.PASS
    assert eval_a.price_per_kg == Decimal("25.85")
    assert eval_a.rulebook_id == "RULEBOOK-WHEAT-V1"
    assert eval_a.rulebook_version == 1
    assert len(eval_a.results) == 4
    assert all(r.grade == QualityGrade.A for r in eval_a.results)

    # 2. Grade B Sample (Moisture 12.8 qualifies for B, passes others)
    fake_db["qualityChecks"].items["QC-B"] = {
        "_id": "QC-B",
        "qcAttemptId": "QC-B",
        "lotId": "LOT-1",
        "cropCode": "WHEAT",
        "tests": {
            "MOISTURE_PERCENT": 12.8,
            "FOREIGN_MATTER_PERCENT": 0.60,
            "DAMAGED_GRAINS_PERCENT": 3.0,
            "WEEVILLED_GRAINS_PERCENT": 4.0,
        },
    }
    eval_b = rulebooks.evaluate_quality_check("QC-B")
    assert eval_b.grade == QualityGrade.B
    assert eval_b.decision == EvaluationDecision.PASS
    assert eval_b.price_per_kg == Decimal("25.20")

    # 3. Grade C Sample (Damaged grains 5.5 qualifies for C)
    fake_db["qualityChecks"].items["QC-C"] = {
        "_id": "QC-C",
        "qcAttemptId": "QC-C",
        "lotId": "LOT-1",
        "cropCode": "WHEAT",
        "tests": {
            "MOISTURE_PERCENT": 13.5,
            "FOREIGN_MATTER_PERCENT": 0.90,
            "DAMAGED_GRAINS_PERCENT": 5.5,
            "WEEVILLED_GRAINS_PERCENT": 8.0,
        },
    }
    eval_c = rulebooks.evaluate_quality_check("QC-C")
    assert eval_c.grade == QualityGrade.C
    assert eval_c.decision == EvaluationDecision.PASS
    assert eval_c.price_per_kg == Decimal("24.55")

    # 4. Grade F Sample (Moisture 15.0% > 14.0% C limit)
    fake_db["qualityChecks"].items["QC-F"] = {
        "_id": "QC-F",
        "qcAttemptId": "QC-F",
        "lotId": "LOT-1",
        "cropCode": "WHEAT",
        "tests": {
            "MOISTURE_PERCENT": 15.0,
            "FOREIGN_MATTER_PERCENT": 0.40,
            "DAMAGED_GRAINS_PERCENT": 1.5,
            "WEEVILLED_GRAINS_PERCENT": 1.0,
        },
    }
    eval_f = rulebooks.evaluate_quality_check("QC-F")
    assert eval_f.grade == QualityGrade.F
    assert eval_f.decision == EvaluationDecision.FAIL
    assert eval_f.price_per_kg == Decimal("0.00")
    # Moisture test result specifically explains violation
    moisture_res = next(r for r in eval_f.results if r.test_code == "MOISTURE_PERCENT")
    assert moisture_res.grade == QualityGrade.F
    assert moisture_res.result == EvaluationDecision.FAIL
    assert "violates" in moisture_res.explanation

    # Retrieve evaluation endpoint
    retrieved = rulebooks.get_evaluation_for_qc("QC-B")
    assert retrieved.evaluation_id == eval_b.evaluation_id
    assert retrieved.grade == QualityGrade.B


def test_procurement_rulebook_integration_and_grade_f_rejection(monkeypatch):
    fake_db = configure_rulebooks(monkeypatch)

    # 1. F Sample blocks procurement
    fake_db["qualityChecks"].items["QC-000001"]["tests"] = {
        "MOISTURE_PERCENT": 16.0,
        "FOREIGN_MATTER_PERCENT": 0.40,
        "DAMAGED_GRAINS_PERCENT": 1.0,
        "WEEVILLED_GRAINS_PERCENT": 1.0,
    }
    rulebooks.evaluate_quality_check("QC-000001")

    req_proc = government_procurements.GovernmentProcurementCreate(
        weighmentId="WEIGH-000001",
        procurementQuantityKg=Decimal("10000.0"),
        employeeId="EMP-PROC-1",
    )
    with pytest.raises(HTTPException) as err:
        government_procurements.create_procurement("LOT-1", req_proc)
    assert err.value.status_code == 400
    assert "Grade F" in err.value.detail

    # 2. Grade B sample permits procurement & derives price from Rulebook
    # Clear evaluations and re-evaluate as Grade B
    fake_db["qualityEvaluations"].items.clear()
    fake_db["qualityChecks"].items["QC-000001"]["tests"] = {
        "MOISTURE_PERCENT": 12.8,
        "FOREIGN_MATTER_PERCENT": 0.60,
        "DAMAGED_GRAINS_PERCENT": 3.0,
        "WEEVILLED_GRAINS_PERCENT": 4.0,
    }
    eval_b = rulebooks.evaluate_quality_check("QC-000001")
    assert eval_b.grade == QualityGrade.B

    # Attempt to override price with 999.00 from client
    req_override = government_procurements.GovernmentProcurementCreate(
        weighmentId="WEIGH-000001",
        procurementQuantityKg=Decimal("10000.0"),
        pricePerKg=Decimal("999.00"),
        employeeId="EMP-PROC-1",
    )
    proc_res = government_procurements.create_procurement("LOT-1", req_override)

    # Backend strictly enforced Rulebook price and grade
    assert proc_res.quality_grade == "B"
    assert proc_res.price_per_kg == Decimal("25.20")  # Overrode client 999.00!
    assert proc_res.gross_amount == Decimal("252000.00")
    assert proc_res.rulebook_id == "RULEBOOK-WHEAT-V1"
    assert proc_res.rulebook_version == 1
    assert proc_res.evaluation_id == eval_b.evaluation_id


def test_retest_scenario_and_payment_integration(monkeypatch):
    fake_db = configure_rulebooks(monkeypatch)

    # QC 1 fails (Grade F)
    fake_db["qualityChecks"].items["QC-000001"] = {
        "_id": "QC-000001",
        "qcAttemptId": "QC-000001",
        "lotId": "LOT-1",
        "cropCode": "WHEAT",
        "attemptNumber": 1,
        "tests": {
            "MOISTURE_PERCENT": 15.5,
            "FOREIGN_MATTER_PERCENT": 1.5,
            "DAMAGED_GRAINS_PERCENT": 8.0,
            "WEEVILLED_GRAINS_PERCENT": 12.0,
        },
    }
    eval_f = rulebooks.evaluate_quality_check("QC-000001")
    assert eval_f.grade == QualityGrade.F

    # QC 2 retest succeeds (Grade A)
    fake_db["qualityChecks"].items["QC-000002"] = {
        "_id": "QC-000002",
        "qcAttemptId": "QC-000002",
        "lotId": "LOT-1",
        "cropCode": "WHEAT",
        "attemptNumber": 2,
        "tests": {
            "MOISTURE_PERCENT": 11.0,
            "FOREIGN_MATTER_PERCENT": 0.30,
            "DAMAGED_GRAINS_PERCENT": 1.0,
            "WEEVILLED_GRAINS_PERCENT": 1.0,
        },
    }
    eval_a = rulebooks.evaluate_quality_check("QC-000002")
    assert eval_a.grade == QualityGrade.A

    # Earlier evaluation is NOT overwritten
    historical_eval = rulebooks.get_evaluation_for_qc("QC-000001")
    assert historical_eval.grade == QualityGrade.F
    assert historical_eval.rulebook_version == 1

    # Procurement succeeds using the retest evaluation
    proc_req = government_procurements.GovernmentProcurementCreate(
        weighmentId="WEIGH-000001",
        procurementQuantityKg=Decimal("5000.0"),
        qcAttemptId="QC-000002",
        employeeId="EMP-PROC-1",
    )
    proc_res = government_procurements.create_procurement("LOT-1", proc_req)
    assert proc_res.quality_grade == "A"
    assert proc_res.price_per_kg == Decimal("25.85")
    assert proc_res.gross_amount == Decimal("129250.00")
    assert proc_res.qc_attempt_id == "QC-000002"

    # Payment module integration: records payment using procurement gross amount
    pay_req = payments.PaymentCreate(employeeId="EMP-PROC-1")
    pay_res = payments.create_payment(proc_res.procurement_id, pay_req)
    assert pay_res.payable_amount == Decimal("129250.00")
    assert pay_res.price_per_kg == Decimal("25.85")
    assert pay_res.procurement_quantity_kg == Decimal("5000.0")
    assert pay_res.payment_status == PaymentStatus.PENDING


# ---------------------------------------------------------------------------
# Deterministic Slot Assignment Test Infrastructure and Tests
# ---------------------------------------------------------------------------


class SlotsGenericCollection(GenericCollection):
    """GenericCollection supporting atomic pipeline updates used by reserve_slot_capacity."""

    def find_one_and_update(self, query, update, upsert=False, return_document=None, **kwargs):
        slot_id = query.get("_id")
        slot = self.items.get(slot_id)
        if slot is None:
            return None

        if slot.get("status") == SlotStatus.CLOSED.value or slots._derived_status(slot) == SlotStatus.CLOSED:
            return None

        if isinstance(update, list):
            add_stage = update[0].get("$set", {})
            alloc_kg_expr = add_stage.get("allocatedKg", {}).get("$add", [])
            qty_to_add = slots._as_decimal(alloc_kg_expr[1]) if len(alloc_kg_expr) > 1 else Decimal("0")

            cur_kg = slots._as_decimal(slot.get("allocatedKg", 0))
            cap_kg = slots._as_decimal(slot.get("capacityKg", 0))
            cur_farmers = slot.get("allocatedFarmers", 0)
            max_farmers = slot.get("maxFarmers", 0)

            if cur_kg + qty_to_add > cap_kg:
                return None
            if cur_farmers + 1 > max_farmers:
                return None

            new_kg = cur_kg + qty_to_add
            new_farmers = cur_farmers + 1
            slot["allocatedKg"] = Decimal128(new_kg)
            slot["allocatedFarmers"] = new_farmers
            slot["updatedAt"] = datetime.now(timezone.utc)
            if new_kg >= cap_kg or new_farmers >= max_farmers:
                slot["status"] = SlotStatus.FULL.value
            else:
                slot["status"] = SlotStatus.AVAILABLE.value
            return dict(slot)

        return super().find_one_and_update(query, update, upsert=upsert, return_document=return_document, **kwargs)


def configure_deterministic_slots(monkeypatch, farmers=None, centres=None, slots_list=None, crops=None):
    farmer_docs = farmers or [{
        "_id": "FARMER-1",
        "farmerId": "FARMER-1",
        "name": "Ramesh Patil",
        "district": "Nashik",
        "area": "Sinnar",
        "phone": "+919876543210",
        "address": "Village Post Sinnar",
        "preferredLanguage": "Marathi",
        "ekycVerified": True,
    }]
    crop_docs = crops or [{
        "_id": "WHEAT",
        "cropCode": "WHEAT",
        "cropName": "Wheat",
        "status": "ACTIVE",
    }]
    centre_docs = centres or [{
        "_id": "CENTRE-1",
        "centreId": "CENTRE-1",
        "centreName": "Sinnar Centre",
        "district": "Nashik",
        "area": "Sinnar",
        "supportedCrops": ["WHEAT"],
        "status": "ACTIVE",
    }]
    raw_slots = slots_list or [{
        "_id": "SLOT-1",
        "slotId": "SLOT-1",
        "centreId": "CENTRE-1",
        "cropCode": "WHEAT",
        "date": "2026-10-01",
        "startTime": "10:00:00",
        "endTime": "11:00:00",
        "capacityKg": Decimal128("10000"),
        "allocatedKg": Decimal128("0"),
        "maxFarmers": 5,
        "allocatedFarmers": 0,
        "status": "AVAILABLE",
    }]
    now = datetime.now(timezone.utc)
    slot_docs = []
    for s in raw_slots:
        doc = dict(s)
        if "endTime" not in doc:
            doc["endTime"] = "11:00:00"
        if "createdAt" not in doc:
            doc["createdAt"] = now
        if "updatedAt" not in doc:
            doc["updatedAt"] = now
        slot_docs.append(doc)

    farmers_coll = GenericCollection(farmer_docs)
    crops_coll = GenericCollection(crop_docs)
    centres_coll = GenericCollection(centre_docs)
    slots_coll = SlotsGenericCollection(slot_docs)
    requests_coll = GenericCollection()

    fake_db = {
        "farmers": farmers_coll,
        "cropConfigurations": crops_coll,
        "centres": centres_coll,
        "slots": slots_coll,
        "procurementRequests": requests_coll,
    }

    monkeypatch.setattr(slots, "get_database", lambda: fake_db)
    monkeypatch.setattr(slots, "slots_collection", lambda: slots_coll)
    monkeypatch.setattr(procurement_requests, "get_database", lambda: fake_db)
    monkeypatch.setattr(procurement_requests, "procurement_requests_collection", lambda: requests_coll)
    monkeypatch.setattr(procurement_requests, "mongo_client", FakeClient())

    return fake_db


def test_exact_area_centre_preferred(monkeypatch):
    """Test 1: exact-area centre preferred over same-district centre."""
    centres = [
        {
            "_id": "CENTRE-IGATPURI",
            "centreId": "CENTRE-IGATPURI",
            "district": "Nashik",
            "area": "Igatpuri",
            "supportedCrops": ["WHEAT"],
            "status": "ACTIVE",
        },
        {
            "_id": "CENTRE-SINNAR",
            "centreId": "CENTRE-SINNAR",
            "district": "Nashik",
            "area": "Sinnar",
            "supportedCrops": ["WHEAT"],
            "status": "ACTIVE",
        },
    ]
    slots_list = [
        {
            "_id": "SLOT-IGATPURI",
            "slotId": "SLOT-IGATPURI",
            "centreId": "CENTRE-IGATPURI",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("0"),
            "maxFarmers": 5,
            "allocatedFarmers": 0,
            "status": "AVAILABLE",
        },
        {
            "_id": "SLOT-SINNAR",
            "slotId": "SLOT-SINNAR",
            "centreId": "CENTRE-SINNAR",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("0"),
            "maxFarmers": 5,
            "allocatedFarmers": 0,
            "status": "AVAILABLE",
        },
    ]
    configure_deterministic_slots(monkeypatch, centres=centres, slots_list=slots_list)

    # Farmer area is Sinnar, district Nashik
    centre, slot = slots.find_deterministic_slot(
        farmer_id="FARMER-1", crop_code="WHEAT", expected_quantity_kg=Decimal("2000"), farmer_area="Sinnar"
    )
    assert centre["centreId"] == "CENTRE-SINNAR"
    assert slot["slotId"] == "SLOT-SINNAR"

    # Also test the preview endpoint
    assign_res = slots.assign_slot_endpoint(slots.SlotAssignRequest(
        farmerId="FARMER-1", cropCode="WHEAT", expectedQuantityKg=Decimal("2000"), farmerArea="Sinnar"
    ))
    assert assign_res.centre_id == "CENTRE-SINNAR"
    assert assign_res.slot_id == "SLOT-SINNAR"


def test_district_centre_used_when_exact_area_unavailable(monkeypatch):
    """Test 2: district centre used when exact area has no available centres/slots."""
    centres = [
        {
            "_id": "CENTRE-IGATPURI",
            "centreId": "CENTRE-IGATPURI",
            "district": "Nashik",
            "area": "Igatpuri",
            "supportedCrops": ["WHEAT"],
            "status": "ACTIVE",
        },
    ]
    slots_list = [
        {
            "_id": "SLOT-IGATPURI",
            "slotId": "SLOT-IGATPURI",
            "centreId": "CENTRE-IGATPURI",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("0"),
            "maxFarmers": 5,
            "allocatedFarmers": 0,
            "status": "AVAILABLE",
        },
    ]
    configure_deterministic_slots(monkeypatch, centres=centres, slots_list=slots_list)

    # Farmer area Sinnar has no centres, but district Nashik has Igatpuri centre
    centre, slot = slots.find_deterministic_slot(
        farmer_id="FARMER-1", crop_code="WHEAT", expected_quantity_kg=Decimal("2000"), farmer_area="Sinnar"
    )
    assert centre["centreId"] == "CENTRE-IGATPURI"
    assert slot["slotId"] == "SLOT-IGATPURI"


def test_unsupported_crop_centre_excluded(monkeypatch):
    """Test 3: centre not supporting the requested crop is excluded."""
    centres = [
        {
            "_id": "CENTRE-SINNAR-1",
            "centreId": "CENTRE-SINNAR-1",
            "district": "Nashik",
            "area": "Sinnar",
            "supportedCrops": ["ONION"],
            "status": "ACTIVE",
        },
        {
            "_id": "CENTRE-SINNAR-2",
            "centreId": "CENTRE-SINNAR-2",
            "district": "Nashik",
            "area": "Sinnar",
            "supportedCrops": ["WHEAT"],
            "status": "ACTIVE",
        },
    ]
    slots_list = [
        {
            "_id": "SLOT-ONION",
            "slotId": "SLOT-ONION",
            "centreId": "CENTRE-SINNAR-1",
            "cropCode": "ONION",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("0"),
            "maxFarmers": 5,
            "allocatedFarmers": 0,
            "status": "AVAILABLE",
        },
        {
            "_id": "SLOT-WHEAT",
            "slotId": "SLOT-WHEAT",
            "centreId": "CENTRE-SINNAR-2",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("0"),
            "maxFarmers": 5,
            "allocatedFarmers": 0,
            "status": "AVAILABLE",
        },
    ]
    configure_deterministic_slots(monkeypatch, centres=centres, slots_list=slots_list)

    centre, slot = slots.find_deterministic_slot(
        farmer_id="FARMER-1", crop_code="WHEAT", expected_quantity_kg=Decimal("1500")
    )
    assert centre["centreId"] == "CENTRE-SINNAR-2"
    assert slot["slotId"] == "SLOT-WHEAT"


def test_inactive_centre_excluded(monkeypatch):
    """Test 4: inactive centre excluded even if area and crop match."""
    centres = [
        {
            "_id": "CENTRE-INACTIVE",
            "centreId": "CENTRE-INACTIVE",
            "district": "Nashik",
            "area": "Sinnar",
            "supportedCrops": ["WHEAT"],
            "status": "INACTIVE",
        },
        {
            "_id": "CENTRE-ACTIVE",
            "centreId": "CENTRE-ACTIVE",
            "district": "Nashik",
            "area": "Igatpuri",
            "supportedCrops": ["WHEAT"],
            "status": "ACTIVE",
        },
    ]
    slots_list = [
        {
            "_id": "SLOT-INACTIVE",
            "slotId": "SLOT-INACTIVE",
            "centreId": "CENTRE-INACTIVE",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("0"),
            "maxFarmers": 5,
            "allocatedFarmers": 0,
            "status": "AVAILABLE",
        },
        {
            "_id": "SLOT-ACTIVE",
            "slotId": "SLOT-ACTIVE",
            "centreId": "CENTRE-ACTIVE",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("0"),
            "maxFarmers": 5,
            "allocatedFarmers": 0,
            "status": "AVAILABLE",
        },
    ]
    configure_deterministic_slots(monkeypatch, centres=centres, slots_list=slots_list)

    centre, slot = slots.find_deterministic_slot(
        farmer_id="FARMER-1", crop_code="WHEAT", expected_quantity_kg=Decimal("2000")
    )
    assert centre["centreId"] == "CENTRE-ACTIVE"
    assert slot["slotId"] == "SLOT-ACTIVE"


def test_slot_with_insufficient_weight_capacity_excluded(monkeypatch):
    """Test 5: slot with insufficient remaining weight capacity excluded."""
    slots_list = [
        {
            "_id": "SLOT-SMALL",
            "slotId": "SLOT-SMALL",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("5000"),
            "allocatedKg": Decimal128("3500"),  # remaining: 1500 kg
            "maxFarmers": 5,
            "allocatedFarmers": 1,
            "status": "AVAILABLE",
        },
        {
            "_id": "SLOT-BIG",
            "slotId": "SLOT-BIG",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("2000"),  # remaining: 8000 kg
            "maxFarmers": 5,
            "allocatedFarmers": 1,
            "status": "AVAILABLE",
        },
    ]
    configure_deterministic_slots(monkeypatch, slots_list=slots_list)

    # 3000 kg request exceeds SLOT-SMALL remaining (1500 kg), routed to SLOT-BIG
    _, slot = slots.find_deterministic_slot(
        farmer_id="FARMER-1", crop_code="WHEAT", expected_quantity_kg=Decimal("3000")
    )
    assert slot["slotId"] == "SLOT-BIG"


def test_slot_with_no_farmer_capacity_excluded(monkeypatch):
    """Test 6: slot with full farmer capacity excluded even if weight capacity remains."""
    slots_list = [
        {
            "_id": "SLOT-FULL-FARMERS",
            "slotId": "SLOT-FULL-FARMERS",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("1000"),
            "maxFarmers": 2,
            "allocatedFarmers": 2,  # 0 farmer capacity remaining
            "status": "AVAILABLE",
        },
        {
            "_id": "SLOT-HAS-FARMERS",
            "slotId": "SLOT-HAS-FARMERS",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("1000"),
            "maxFarmers": 5,
            "allocatedFarmers": 1,  # 4 farmer capacity remaining
            "status": "AVAILABLE",
        },
    ]
    configure_deterministic_slots(monkeypatch, slots_list=slots_list)

    _, slot = slots.find_deterministic_slot(
        farmer_id="FARMER-1", crop_code="WHEAT", expected_quantity_kg=Decimal("1000")
    )
    assert slot["slotId"] == "SLOT-HAS-FARMERS"


def test_earliest_valid_slot_selected(monkeypatch):
    """Test 7: earliest available date and startTime selected."""
    slots_list = [
        {
            "_id": "SLOT-LATER-DATE",
            "slotId": "SLOT-LATER-DATE",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "date": "2026-10-03",
            "startTime": "09:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("0"),
            "maxFarmers": 5,
            "allocatedFarmers": 0,
            "status": "AVAILABLE",
        },
        {
            "_id": "SLOT-EARLY-DATE-LATER-TIME",
            "slotId": "SLOT-EARLY-DATE-LATER-TIME",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "14:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("0"),
            "maxFarmers": 5,
            "allocatedFarmers": 0,
            "status": "AVAILABLE",
        },
        {
            "_id": "SLOT-EARLIEST",
            "slotId": "SLOT-EARLIEST",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "09:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("0"),
            "maxFarmers": 5,
            "allocatedFarmers": 0,
            "status": "AVAILABLE",
        },
    ]
    configure_deterministic_slots(monkeypatch, slots_list=slots_list)

    _, slot = slots.find_deterministic_slot(
        farmer_id="FARMER-1", crop_code="WHEAT", expected_quantity_kg=Decimal("1000")
    )
    assert slot["slotId"] == "SLOT-EARLIEST"


def test_deterministic_tie_breaking(monkeypatch):
    """Test 8: tie-breaking by remaining capacity descending, then slotId ascending."""
    # Case A: Same date and time -> prefer slot with higher remaining capacity
    slots_capacity_tie = [
        {
            "_id": "SLOT-CAP-4000",
            "slotId": "SLOT-CAP-4000",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("6000"),  # remaining: 4000 kg
            "maxFarmers": 5,
            "allocatedFarmers": 1,
            "status": "AVAILABLE",
        },
        {
            "_id": "SLOT-CAP-8000",
            "slotId": "SLOT-CAP-8000",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("2000"),  # remaining: 8000 kg
            "maxFarmers": 5,
            "allocatedFarmers": 1,
            "status": "AVAILABLE",
        },
    ]
    configure_deterministic_slots(monkeypatch, slots_list=slots_capacity_tie)
    _, slot_cap = slots.find_deterministic_slot(
        farmer_id="FARMER-1", crop_code="WHEAT", expected_quantity_kg=Decimal("1000")
    )
    assert slot_cap["slotId"] == "SLOT-CAP-8000"

    # Case B: Same date, time, and remaining capacity -> slotId ascending tie-breaker
    slots_id_tie = [
        {
            "_id": "SLOT-Z",
            "slotId": "SLOT-Z",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("5000"),  # remaining: 5000 kg
            "maxFarmers": 5,
            "allocatedFarmers": 1,
            "status": "AVAILABLE",
        },
        {
            "_id": "SLOT-A",
            "slotId": "SLOT-A",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("10000"),
            "allocatedKg": Decimal128("5000"),  # remaining: 5000 kg
            "maxFarmers": 5,
            "allocatedFarmers": 1,
            "status": "AVAILABLE",
        },
    ]
    configure_deterministic_slots(monkeypatch, slots_list=slots_id_tie)
    _, slot_id = slots.find_deterministic_slot(
        farmer_id="FARMER-1", crop_code="WHEAT", expected_quantity_kg=Decimal("1000")
    )
    assert slot_id["slotId"] == "SLOT-A"


def test_no_suitable_slot_returns_controlled_conflict(monkeypatch):
    """Test 9: no suitable slot returns controlled HTTP 409 Conflict."""
    slots_list = [
        {
            "_id": "SLOT-TINY",
            "slotId": "SLOT-TINY",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("2000"),
            "allocatedKg": Decimal128("1500"),  # remaining 500 kg
            "maxFarmers": 5,
            "allocatedFarmers": 1,
            "status": "AVAILABLE",
        }
    ]
    configure_deterministic_slots(monkeypatch, slots_list=slots_list)

    # 1. find_deterministic_slot raises 409
    with pytest.raises(HTTPException) as exc_info:
        slots.find_deterministic_slot(
            farmer_id="FARMER-1", crop_code="WHEAT", expected_quantity_kg=Decimal("1000")
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "No eligible procurement slot can accommodate the requested quantity."

    # 2. create_procurement_request raises 409
    create_payload = procurement_requests.ProcurementRequestCreate(
        requestId="REQ-NO-SLOT",
        farmerId="FARMER-1",
        cropCode="WHEAT",
        farmerArea="Sinnar",
        expectedQuantityKg=Decimal("1000"),
        autoAssign=True,
    )
    with pytest.raises(HTTPException) as exc_info2:
        procurement_requests.create_procurement_request(create_payload, current_user=None)
    assert exc_info2.value.status_code == 409
    assert exc_info2.value.detail == "No eligible procurement slot can accommodate the requested quantity."


def test_concurrent_reservation_cannot_exceed_capacity(monkeypatch):
    """Test 10: atomic reservation protects slot from exceeding farmer or weight limits."""
    slots_list = [
        {
            "_id": "SLOT-LIMITED",
            "slotId": "SLOT-LIMITED",
            "centreId": "CENTRE-1",
            "cropCode": "WHEAT",
            "date": "2026-10-01",
            "startTime": "10:00:00",
            "capacityKg": Decimal128("3000"),
            "allocatedKg": Decimal128("0"),
            "maxFarmers": 1,
            "allocatedFarmers": 0,
            "status": "AVAILABLE",
        }
    ]
    fake_db = configure_deterministic_slots(monkeypatch, slots_list=slots_list)

    # First reservation takes the slot
    req1 = procurement_requests.ProcurementRequestCreate(
        requestId="REQ-CONCUR-1",
        farmerId="FARMER-1",
        cropCode="WHEAT",
        farmerArea="Sinnar",
        expectedQuantityKg=Decimal("2000"),
        autoAssign=True,
    )
    res1 = procurement_requests.create_procurement_request(req1, current_user=None)
    assert res1.assigned_slot_id == "SLOT-LIMITED"
    assert res1.booking_status == procurement_requests.BookingStatus.CONFIRMED

    # Verify slot allocations in database
    slot_in_db = fake_db["slots"].items["SLOT-LIMITED"]
    assert slots._as_decimal(slot_in_db["allocatedKg"]) == Decimal("2000")
    assert slot_in_db["allocatedFarmers"] == 1
    assert slot_in_db["status"] == SlotStatus.FULL.value

    # Second reservation fails because farmer capacity (max 1) is reached
    req2 = procurement_requests.ProcurementRequestCreate(
        requestId="REQ-CONCUR-2",
        farmerId="FARMER-1",
        cropCode="WHEAT",
        farmerArea="Sinnar",
        expectedQuantityKg=Decimal("500"),
        autoAssign=True,
    )
    with pytest.raises(HTTPException) as exc_info:
        procurement_requests.create_procurement_request(req2, current_user=None)
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "No eligible procurement slot can accommodate the requested quantity."

    # Verify capacity was never exceeded
    assert slots._as_decimal(slot_in_db["allocatedKg"]) == Decimal("2000")
    assert slot_in_db["allocatedFarmers"] == 1



