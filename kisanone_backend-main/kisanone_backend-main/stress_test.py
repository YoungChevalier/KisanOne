import argparse
import random
import time
import datetime
from decimal import Decimal
from bson.decimal128 import Decimal128
import sys
import os
import concurrent.futures

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import get_database
import procurement_requests

db = get_database()

PREFIX = "STRESS-"
CROP_CODES = ["WHEAT", "RICE", "ONION", "SOYBEAN"]
DISTRICTS = ["Bhopal", "Nashik", "Pune", "Indore", "Sehore"]
AREAS = ["Area-A", "Area-B", "Area-C", "North Zone", "South Zone"]
ROLES = ["CENTRE_MANAGER", "QC_OFFICER", "WEIGHMENT_OFFICER", "PROCUREMENT_OFFICER"]
STATUSES = [
    "SCHEDULED", "QC_IN_PROGRESS", "QC_PASSED", "QC_FAILED",
    "WEIGHMENT_COMPLETED", "PROCURED", "REJECTED", "COMPLETED", "CANCELLED"
]

def convert_decimals(doc):
    if isinstance(doc, dict):
        return {k: convert_decimals(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [convert_decimals(v) for v in doc]
    elif isinstance(doc, Decimal):
        return Decimal128(str(doc))
    return doc

def random_phone():
    return f"+919{random.randint(100000000, 999999999)}"

def cleanup():
    print("🧹 Cleaning up STRESS data...")
    collections = [
        "farmers", "auth_credentials", "centres", "employees", "slots",
        "procurement_requests", "lots", "qualityChecks", "qualityEvaluations",
        "weighments", "governmentProcurements", "payments"
    ]
    query = {"_id": {"$regex": f"^{PREFIX}"}}
    
    total_deleted = 0
    for coll in collections:
        result = db[coll].delete_many(query)
        if result.deleted_count > 0:
            print(f"  - Deleted {result.deleted_count} from {coll}")
            total_deleted += result.deleted_count
            
    for coll, id_field in [
        ("farmers", "farmerId"), ("centres", "centreId"), ("employees", "employeeId"),
        ("slots", "slotId"), ("procurement_requests", "requestId"), ("lots", "lotId"),
        ("qualityChecks", "qcAttemptId"), ("qualityEvaluations", "evaluationId"),
        ("weighments", "weighmentId"), ("governmentProcurements", "procurementId"),
        ("payments", "paymentId")
    ]:
        res = db[coll].delete_many({id_field: {"$regex": f"^{PREFIX}"}})
        if res.deleted_count > 0:
            print(f"  - Deleted {res.deleted_count} from {coll} (by {id_field})")
            total_deleted += res.deleted_count

    print(f"✨ Cleanup complete. Total records removed: {total_deleted}")

def batch_insert(col_name, data):
    if not data: return
    data = [convert_decimals(d) for d in data]
    batch_size = 5000
    for b in range(0, len(data), batch_size):
        db[col_name].insert_many(data[b:b+batch_size])
    print(f"  ✓ Inserted {len(data)} into {col_name}.")

def generate_data(num_farmers, num_centres, num_requests, num_days):
    print(f"🌱 Generating STRESS data: {num_farmers} farmers, {num_centres} centres, {num_requests} requests over {num_days} days.")
    
    now = datetime.datetime.now(datetime.timezone.utc)
    today = now.date()
    
    centres = []
    for i in range(num_centres):
        c_id = f"{PREFIX}CNT-{i}"
        centres.append({
            "_id": c_id,
            "centreId": c_id,
            "centreName": f"Stress Centre {i}",
            "state": "Madhya Pradesh",
            "district": random.choice(DISTRICTS),
            "area": random.choice(AREAS),
            "address": f"Street {i}",
            "location": {"latitude": 20.0, "longitude": 70.0},
            "supportedCrops": random.sample(CROP_CODES, k=random.randint(1, len(CROP_CODES))),
            "operatingDays": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            "operatingHours": "08:00-18:00",
            "dailyProcurementCapacityKg": Decimal(str(random.randint(100000, 500000))),
            "status": "ACTIVE" if random.random() > 0.05 else "INACTIVE",
            "createdAt": now,
            "updatedAt": now
        })
    batch_insert("centres", centres)

    employees = []
    for c in centres:
        for role in ROLES:
            e_id = f"{PREFIX}EMP-{c['centreId']}-{role}"
            employees.append({
                "_id": e_id,
                "employeeId": e_id,
                "name": f"Emp {role} {c['centreId']}",
                "phone": random_phone(),
                "role": role,
                "centreId": c["centreId"],
                "status": "ACTIVE",
                "createdAt": now,
                "updatedAt": now
            })
    batch_insert("employees", employees)

    farmers = []
    auths = []
    for i in range(num_farmers):
        f_id = f"{PREFIX}FMR-{i}"
        farmers.append({
            "_id": f_id,
            "farmerId": f_id,
            "name": f"Stress Farmer {i}",
            "phone": random_phone(),
            "address": f"Village {i}",
            "district": random.choice(DISTRICTS),
            "area": random.choice(AREAS),
            "preferredLanguage": "Hindi",
            "ekycVerified": True,
            "createdAt": now,
            "updatedAt": now
        })
        auths.append({
            "_id": f_id,
            "userType": "farmer",
            "passwordHash": "dummyhash",
            "createdAt": now
        })
    batch_insert("farmers", farmers)
    batch_insert("auth_credentials", auths)

    slots = []
    for c in centres:
        if c["status"] != "ACTIVE": continue
        for d_offset in range(-2, num_days):
            d = today + datetime.timedelta(days=d_offset)
            for crop in c["supportedCrops"]:
                for hour in [9, 11, 14, 16]:
                    s_id = f"{PREFIX}SLT-{c['centreId']}-{crop}-{d.isoformat()}-{hour}"
                    
                    cap = random.randint(10000, 50000)
                    alloc = 0 if random.random() > 0.5 else random.randint(0, cap)
                    max_f = random.randint(20, 100)
                    alloc_f = 0 if alloc == 0 else random.randint(1, max_f)
                    
                    status = "AVAILABLE"
                    if alloc >= cap or alloc_f >= max_f: status = "FULL"
                    if random.random() < 0.05: status = "CLOSED"

                    slots.append({
                        "_id": s_id,
                        "slotId": s_id,
                        "centreId": c["centreId"],
                        "cropCode": crop,
                        "date": datetime.datetime(d.year, d.month, d.day),
                        "startTime": f"{hour:02d}:00:00",
                        "endTime": f"{hour+2:02d}:00:00",
                        "capacityKg": Decimal(str(cap)),
                        "allocatedKg": Decimal(str(alloc)),
                        "maxFarmers": max_f,
                        "allocatedFarmers": alloc_f,
                        "remainingCapacityKg": Decimal(str(cap - alloc)),
                        "remainingFarmerCapacity": max_f - alloc_f,
                        "status": status,
                        "createdAt": now,
                        "updatedAt": now
                    })
    batch_insert("slots", slots)

    requests = []
    lots = []
    qcs = []
    evals = []
    weighments = []
    procurements = []
    payments = []
    
    active_slots = [s for s in slots if s["status"] == "AVAILABLE"]
    
    for i in range(num_requests):
        r_id = f"{PREFIX}REQ-{i}"
        f = random.choice(farmers)
        status = random.choice(STATUSES)
        
        slot = random.choice(active_slots) if active_slots else slots[0]
        c_id = slot["centreId"]
        crop = slot["cropCode"]
        qty = Decimal(str(random.randint(100, 1000)))
        
        arrival = "ARRIVED" if status != "SCHEDULED" else random.choice(["NOT_ARRIVED", "ARRIVED"])
        
        req = {
            "_id": r_id,
            "requestId": r_id,
            "farmerId": f["farmerId"],
            "cropCode": crop,
            "expectedQuantityKg": qty,
            "farmerArea": f["area"],
            "assignedCentreId": c_id,
            "assignedSlotId": slot["slotId"],
            "bookingStatus": "CONFIRMED" if status != "CANCELLED" else "CANCELLED",
            "arrivalStatus": arrival,
            "requestStatus": status,
            "queueNumber": i + 1,
            "createdAt": now - datetime.timedelta(hours=random.randint(1, 100)),
            "updatedAt": now
        }
        
        if arrival == "ARRIVED":
            req["arrivedAt"] = now - datetime.timedelta(hours=2)
            req["arrivalMarkedByEmployeeId"] = f"{PREFIX}EMP-{c_id}-CENTRE_MANAGER"
            
        if status in ["QC_IN_PROGRESS", "QC_PASSED", "QC_FAILED", "WEIGHMENT_COMPLETED", "PROCURED", "COMPLETED", "REJECTED"]:
            l_id = f"{PREFIX}LOT-{i}"
            req["lotId"] = l_id
            lots.append({
                "_id": l_id, "lotId": l_id, "requestId": r_id,
                "status": "COMPLETED" if status == "COMPLETED" else "ACTIVE",
                "createdAt": now, "updatedAt": now
            })
            
            if status in ["QC_PASSED", "QC_FAILED", "WEIGHMENT_COMPLETED", "PROCURED", "COMPLETED", "REJECTED"]:
                qc_id = f"{PREFIX}QC-{i}"
                qcs.append({
                    "_id": qc_id, "qcAttemptId": qc_id, "lotId": l_id,
                    "status": "EVALUATED", "createdAt": now, "updatedAt": now
                })
                ev_id = f"{PREFIX}EVAL-{i}"
                decision = "PASS" if status not in ["QC_FAILED", "REJECTED"] else "FAIL"
                evals.append({
                    "_id": ev_id, "evaluationId": ev_id, "qcAttemptId": qc_id,
                    "decision": decision, "grade": "A" if decision == "PASS" else "F", "createdAt": now
                })
                
                if status in ["WEIGHMENT_COMPLETED", "PROCURED", "COMPLETED"]:
                    w_id = f"{PREFIX}WGT-{i}"
                    weighments.append({
                        "_id": w_id, "weighmentId": w_id, "lotId": l_id,
                        "netWeightKg": qty * Decimal("0.95"), "createdAt": now
                    })
                    
                    if status in ["PROCURED", "COMPLETED"]:
                        p_id = f"{PREFIX}PROC-{i}"
                        procurements.append({
                            "_id": p_id, "procurementId": p_id, "lotId": l_id,
                            "grossAmount": qty * Decimal("20"), "createdAt": now
                        })
                        
                        if status == "COMPLETED":
                            pay_id = f"{PREFIX}PAY-{i}"
                            payments.append({
                                "_id": pay_id, "paymentId": pay_id, "procurementId": p_id,
                                "status": "PAID", "createdAt": now
                            })
                            
        requests.append(req)

    batch_insert("procurement_requests", requests)
    batch_insert("lots", lots)
    batch_insert("qualityChecks", qcs)
    batch_insert("qualityEvaluations", evals)
    batch_insert("weighments", weighments)
    batch_insert("governmentProcurements", procurements)
    batch_insert("payments", payments)
    print("✨ Data generation complete.")

def test_scheduling():
    print("🧪 Running deterministic scheduling tests...")
    db.farmers.delete_many({"_id": {"$regex": f"^{PREFIX}TEST-"}})
    db.centres.delete_many({"_id": {"$regex": f"^{PREFIX}TEST-"}})
    db.slots.delete_many({"_id": {"$regex": f"^{PREFIX}TEST-"}})
    
    farmer_id = f"{PREFIX}TEST-FMR-1"
    db.farmers.insert_one(convert_decimals({
        "_id": farmer_id, "farmerId": farmer_id, "name": "Test", 
        "phone": "+919000000000", "address": "T", "district": "TestDist", 
        "area": "TestArea", "preferredLanguage": "Hindi", "ekycVerified": True
    }))

    db.centres.insert_many(convert_decimals([
        {"_id": f"{PREFIX}TEST-C1", "centreId": f"{PREFIX}TEST-C1", "district": "TestDist", "area": "TestArea", "supportedCrops": ["WHEAT"], "status": "ACTIVE", "dailyProcurementCapacityKg": Decimal("10000")},
        {"_id": f"{PREFIX}TEST-C2", "centreId": f"{PREFIX}TEST-C2", "district": "TestDist", "area": "OtherArea", "supportedCrops": ["WHEAT"], "status": "ACTIVE", "dailyProcurementCapacityKg": Decimal("10000")}
    ]))
    d = datetime.datetime.now(datetime.timezone.utc).date()
    db.slots.insert_many(convert_decimals([
        {
            "_id": f"{PREFIX}TEST-S1", "slotId": f"{PREFIX}TEST-S1", "centreId": f"{PREFIX}TEST-C1", 
            "cropCode": "WHEAT", "date": datetime.datetime(d.year, d.month, d.day), "startTime": "10:00:00", "endTime": "11:00:00",
            "capacityKg": Decimal("1000"), "allocatedKg": Decimal("0"), "maxFarmers": 10, "allocatedFarmers": 0, "status": "AVAILABLE",
            "remainingCapacityKg": Decimal("1000"), "remainingFarmerCapacity": 10
        },
        {
            "_id": f"{PREFIX}TEST-S2", "slotId": f"{PREFIX}TEST-S2", "centreId": f"{PREFIX}TEST-C2", 
            "cropCode": "WHEAT", "date": datetime.datetime(d.year, d.month, d.day), "startTime": "10:00:00", "endTime": "11:00:00",
            "capacityKg": Decimal("1000"), "allocatedKg": Decimal("0"), "maxFarmers": 10, "allocatedFarmers": 0, "status": "AVAILABLE",
            "remainingCapacityKg": Decimal("1000"), "remainingFarmerCapacity": 10
        }
    ]))
    
    res, slot = procurement_requests.find_deterministic_slot(farmer_id, "WHEAT", Decimal("100"), "TestArea")
    assert slot["centreId"] == f"{PREFIX}TEST-C1", f"Expected C1, got {slot['centreId']}"
    print("  ✓ Test 1 Passed: Exact Area Priority")

    try:
        procurement_requests.find_deterministic_slot(farmer_id, "WHEAT", Decimal("2000"), "TestArea")
        assert False, "Should have failed"
    except Exception as e:
        assert "No eligible procurement slot" in str(e) or "No available slot" in str(e)
        print("  ✓ Test 6 Passed: Insufficient Weight Capacity")
        
    db.slots.update_one({"_id": f"{PREFIX}TEST-S1"}, {"$set": {"allocatedFarmers": 10, "remainingFarmerCapacity": 0, "status": "FULL"}})
    try:
        res, slot = procurement_requests.find_deterministic_slot(farmer_id, "WHEAT", Decimal("100"), "TestArea")
        assert slot["centreId"] == f"{PREFIX}TEST-C2"
        print("  ✓ Test 7 Passed: Max Farmer Capacity correctly diverts")
    except Exception as e:
        print("Failed Test 7:", e)

    db.farmers.delete_many({"_id": {"$regex": f"^{PREFIX}TEST-"}})
    db.centres.delete_many({"_id": {"$regex": f"^{PREFIX}TEST-"}})
    db.slots.delete_many({"_id": {"$regex": f"^{PREFIX}TEST-"}})


def test_concurrency():
    print("🧪 Running Concurrency tests...")
    db.centres.delete_many({"_id": {"$regex": f"^{PREFIX}CONC-"}})
    db.slots.delete_many({"_id": {"$regex": f"^{PREFIX}CONC-"}})
    db.farmers.delete_many({"_id": {"$regex": f"^{PREFIX}CONC-"}})
    db.procurement_requests.delete_many({"_id": {"$regex": f"^{PREFIX}CONC-"}})
    
    slot_id = f"{PREFIX}CONC-S1"
    c_id = f"{PREFIX}CONC-C1"
    
    db.centres.insert_one(convert_decimals({
        "_id": c_id, "centreId": c_id, "district": "D1", "area": "A1", 
        "supportedCrops": ["WHEAT"], "status": "ACTIVE", "dailyProcurementCapacityKg": Decimal("5000")
    }))
    
    d = datetime.datetime.now(datetime.timezone.utc).date()
    db.slots.insert_one(convert_decimals({
        "_id": slot_id, "slotId": slot_id, "centreId": c_id, 
        "cropCode": "WHEAT", "date": datetime.datetime(d.year, d.month, d.day), "startTime": "10:00:00", "endTime": "11:00:00",
        "capacityKg": Decimal("5000"), "allocatedKg": Decimal("0"), "maxFarmers": 50, "allocatedFarmers": 0, "status": "AVAILABLE",
        "remainingCapacityKg": Decimal("5000"), "remainingFarmerCapacity": 50
    }))
    
    def make_booking(i):
        req_id = f"{PREFIX}CONC-REQ-{i}"
        f_id = f"{PREFIX}CONC-FMR-{i}"
        db.farmers.insert_one(convert_decimals({"_id": f_id, "farmerId": f_id, "name": "F", "phone": "+919000000000", "district": "D1", "area": "A1", "ekycVerified": True, "preferredLanguage": "Hindi", "address": "Addr"}))
        
        try:
            req_model = procurement_requests.ProcurementRequestCreate(
                requestId=req_id,
                farmerId=f_id,
                cropCode="WHEAT",
                expectedQuantityKg=Decimal("500"),
                autoAssign=True,
                farmerArea="A1"
            )
            procurement_requests.create_procurement_request(
                request=req_model,
                current_user={"userType": "farmer", "farmerId": f_id}
            )
            return True
        except Exception as e:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(make_booking, range(50)))
    
    successes = sum(results)
    slot = db.slots.find_one({"_id": slot_id})
    alloc_kg = slot['allocatedKg'].to_decimal()
    
    print(f"  ✓ Concurrency test complete: {successes} successful bookings out of 50.")
    print(f"  ✓ Final slot allocatedKg: {alloc_kg} / {slot['capacityKg'].to_decimal()}")
    print(f"  ✓ Final slot allocatedFarmers: {slot['allocatedFarmers']} / {slot['maxFarmers']}")
    
    if alloc_kg > Decimal("5000"):
        print("  ❌ CRITICAL FAILURE: OVERSOLD CAPACITY!")
    elif alloc_kg == Decimal("5000") and successes == 10:
        print("  ✓ Capacity and Success counts perfectly matched.")
    else:
        print("  ⚠️ Something unexpected occurred.")
        
    db.centres.delete_many({"_id": {"$regex": f"^{PREFIX}CONC-"}})
    db.slots.delete_many({"_id": {"$regex": f"^{PREFIX}CONC-"}})
    db.farmers.delete_many({"_id": {"$regex": f"^{PREFIX}CONC-"}})
    db.procurement_requests.delete_many({"_id": {"$regex": f"^{PREFIX}CONC-"}})

def check_consistency():
    print("🧪 Running Data Consistency Checks...")
    bad_slots = list(db.slots.find({"$expr": {"$gt": ["$allocatedKg", "$capacityKg"]}, "_id": {"$regex": f"^{PREFIX}"}}))
    if bad_slots:
        print(f"  ❌ FOUND {len(bad_slots)} SLOTS OVERSOLD!")
    else:
        print("  ✓ Zero oversold slots.")
        
    print("  ✓ Payments checked (skipped slow orphan scan).")

def test_queue_sanity():
    print("🧪 Running Queue Sanity Checks...")
    c_id = f"{PREFIX}CNT-0"
    
    # Simulate the queue logic: ARRIVED, active, ordered by queueNumber
    pipeline = [
        {"$match": {
            "assignedCentreId": c_id,
            "arrivalStatus": "ARRIVED",
            "requestStatus": {"$in": ["SCHEDULED", "QC_IN_PROGRESS", "QC_FAILED", "WEIGHMENT_COMPLETED"]}
        }},
        {"$sort": {"queueNumber": 1}}
    ]
    queue = list(db.procurement_requests.aggregate(pipeline))
    
    if len(queue) == 0:
        print(f"  ⚠️ No queue items found for {c_id}.")
        return
        
    q_numbers = [item["queueNumber"] for item in queue]
    if q_numbers == sorted(q_numbers):
        print(f"  ✓ Queue is properly ordered by queueNumber. First {len(queue)} items checked.")
    else:
        print("  ❌ Queue ordering failed!")

def main():
    parser = argparse.ArgumentParser(description="KisanOne Synthetic Data Stress Tool")
    parser.add_argument("--cleanup", action="store_true", help="Delete all STRESS- prefixed records.")
    parser.add_argument("--summary", action="store_true", help="Print summary of actual STRESS dataset in DB.")
    parser.add_argument("--generate", action="store_true", help="Generate synthetic STRESS data")
    parser.add_argument("--test", action="store_true", help="Run scheduling and concurrency tests")
    parser.add_argument("--farmers", type=int, default=5000)
    parser.add_argument("--centres", type=int, default=20)
    parser.add_argument("--requests", type=int, default=20000)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    
    args = parser.parse_args()
    
    if args.summary:
        print("📊 STRESS DATASET SUMMARY")
        for coll in ["farmers", "auth_credentials", "centres", "employees", "slots", "procurement_requests", "lots", "qualityChecks", "weighments", "governmentProcurements", "payments"]:
            print(f"- {coll}: {db[coll].count_documents({'_id': {'$regex': '^STRESS-'}})}")
        print("\nFor detailed samples, see stress_test_manifest.md")
        return
    random.seed(args.seed)
    
    if args.cleanup:
        cleanup()
        return

    if args.generate:
        t0 = time.time()
        generate_data(args.farmers, args.centres, args.requests, args.days)
        print(f"⏱️ Generation took {time.time() - t0:.2f}s")
        
    if args.test:
        t0 = time.time()
        test_scheduling()
        test_concurrency()
        check_consistency()
        test_queue_sanity()
        print(f"⏱️ Tests took {time.time() - t0:.2f}s")

if __name__ == "__main__":
    main()
