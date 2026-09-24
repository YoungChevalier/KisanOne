import os
from dotenv import load_dotenv
from pymongo import MongoClient

def main():
    load_dotenv()
    MONGO_URI = os.getenv("MONGODB_URI")
    client = MongoClient(MONGO_URI)
    db = client.kisanone
    
    PREFIX = "STRESS-"
    
    print("Generating manifest from MongoDB...")
    
    with open("stress_test_manifest.md", "w") as f:
        f.write("# KisanOne Stress Test Manifest\n\n")
        f.write("This manifest is generated from ACTUAL records currently present in MongoDB.\n\n")
        
        # A. DATASET SUMMARY
        f.write("## A. DATASET SUMMARY\n\n")
        f.write("Current counts in MongoDB (Total / Stress-prefixed):\n\n")
        
        collections = [
            "farmers", "auth_credentials", "centres", "employees", "cropConfigurations",
            "slots", "procurement_requests", "lots", "qualityChecks", "qualityEvaluations",
            "weighments", "governmentProcurements", "payments", "rulebooks"
        ]
        
        for coll in collections:
            total = db[coll].count_documents({})
            stress = db[coll].count_documents({"_id": {"$regex": f"^{PREFIX}"}})
            f.write(f"- **{coll}**: {total} / {stress}\n")
            
        # B. REPRESENTATIVE FARMERS
        f.write("\n## B. REPRESENTATIVE FARMERS\n\n")
        f.write("A sample of actual farmer IDs covering different operational states.\n\n")
        
        def write_farmer(fmr):
            if not fmr: return
            reqs = list(db.procurement_requests.find({"farmerId": fmr["_id"]}))
            procs = list(db.governmentProcurements.find({"farmerId": fmr["_id"]}))
            pays = list(db.payments.find({"farmerId": fmr["_id"]}))
            f.write(f"### {fmr['name']} ({fmr['_id']})\n")
            f.write(f"- **District**: {fmr.get('district')} | **Area**: {fmr.get('area')}\n")
            f.write(f"- **Requests**: {len(reqs)}\n")
            f.write(f"- **Procurements**: {len(procs)}\n")
            f.write(f"- **Payments**: {len(pays)}\n")
            if reqs:
                f.write(f"- **Request IDs**: {', '.join([r['_id'] for r in reqs])}\n")
            f.write("\n")
            
        # 1. Zero transactions
        zero_fmr = db.farmers.find_one({"_id": {"$regex": f"^{PREFIX}"}, "_id": {"$nin": db.procurement_requests.distinct("farmerId")}})
        if zero_fmr:
            f.write("#### 1. Farmer with zero transactions\n")
            write_farmer(zero_fmr)
        
        # 2. Active request (NOT COMPLETED/CANCELLED/REJECTED)
        active_req = db.procurement_requests.find_one({"_id": {"$regex": f"^{PREFIX}"}, "requestStatus": {"$in": ["SCHEDULED", "QC_IN_PROGRESS"]}})
        if active_req:
            f.write("#### 2. Farmer with active request\n")
            write_farmer(db.farmers.find_one({"_id": active_req["farmerId"]}))
            
        # 3. ARRIVED request
        arrived_req = db.procurement_requests.find_one({"_id": {"$regex": f"^{PREFIX}"}, "arrivalStatus": "ARRIVED", "requestStatus": "SCHEDULED"})
        if arrived_req:
            f.write("#### 3. Farmer with ARRIVED request\n")
            write_farmer(db.farmers.find_one({"_id": arrived_req["farmerId"]}))
            
        # 4. Completed procurement/payment
        paid_req = db.procurement_requests.find_one({"_id": {"$regex": f"^{PREFIX}"}, "requestStatus": "COMPLETED"})
        if paid_req:
            f.write("#### 4. Farmer with completed procurement/payment\n")
            write_farmer(db.farmers.find_one({"_id": paid_req["farmerId"]}))
            
        # 5. Rejected request
        rej_req = db.procurement_requests.find_one({"_id": {"$regex": f"^{PREFIX}"}, "requestStatus": "REJECTED"})
        if rej_req:
            f.write("#### 5. Farmer with rejected request\n")
            write_farmer(db.farmers.find_one({"_id": rej_req["farmerId"]}))
            
        # C. REPRESENTATIVE CENTRES
        f.write("\n## C. REPRESENTATIVE CENTRES\n\n")
        centres = list(db.centres.find({"_id": {"$regex": f"^{PREFIX}"}}).limit(3))
        for c in centres:
            f.write(f"### {c['centreName']} ({c['_id']})\n")
            f.write(f"- **District**: {c['district']} | **Area**: {c['area']}\n")
            f.write(f"- **Crops**: {', '.join(c.get('supportedCropCodes', []))}\n")
            f.write(f"- **Daily Capacity**: {c.get('dailyProcurementCapacityKg')} kg\n")
            f.write(f"- **Status**: {c.get('status')}\n\n")
            
        # D. REPRESENTATIVE SLOTS
        f.write("\n## D. REPRESENTATIVE SLOTS\n\n")
        def write_slot(s, title):
            if not s: return
            f.write(f"### {title}: {s['_id']}\n")
            f.write(f"- **Centre**: {s['centreId']} | **Crop**: {s['cropCode']}\n")
            f.write(f"- **Date**: {s['date']} | **Time**: {s['startTime']} - {s['endTime']}\n")
            f.write(f"- **Capacity**: {s['capacityKg']} kg | **Allocated**: {s['allocatedKg']} kg | **Remaining**: {s['remainingFarmerCapacity']}\n")
            f.write(f"- **Farmers**: {s['allocatedFarmers']}/{s['maxFarmers']}\n")
            f.write(f"- **Status**: {s['status']}\n\n")
            
        write_slot(db.slots.find_one({"_id": {"$regex": f"^{PREFIX}"}, "status": "AVAILABLE", "allocatedFarmers": 0}), "1. Empty Available Slot")
        write_slot(db.slots.find_one({"_id": {"$regex": f"^{PREFIX}"}, "status": "AVAILABLE", "allocatedFarmers": {"$gt": 0}}), "2. Partially Filled Slot")
        write_slot(db.slots.find_one({"_id": {"$regex": f"^{PREFIX}"}, "status": "FULL"}), "3. Full Slot")
        write_slot(db.slots.find_one({"_id": {"$regex": f"^{PREFIX}"}, "maxFarmers": 1, "allocatedFarmers": 1}), "4. Slot with maxFarmers reached")
        
        # E. REPRESENTATIVE REQUESTS
        f.write("\n## E. REPRESENTATIVE REQUESTS\n\n")
        def write_req(r, title):
            if not r: return
            f.write(f"### {title}: {r['_id']}\n")
            f.write(f"- **Farmer**: {r['farmerId']} | **Crop**: {r['cropCode']}\n")
            f.write(f"- **Centre**: {r['assignedCentreId']} | **Slot**: {r['assignedSlotId']}\n")
            f.write(f"- **Queue Number**: {r.get('queueNumber')}\n")
            f.write(f"- **Qty**: {r.get('expectedQuantityKg')} kg\n")
            f.write(f"- **Arrival**: {r.get('arrivalStatus')} | **Status**: {r.get('requestStatus')}\n")
            if r.get('lotId'):
                f.write(f"- **Lot**: {r.get('lotId')}\n")
            f.write("\n")
            
        write_req(db.procurement_requests.find_one({"_id": {"$regex": f"^{PREFIX}"}, "arrivalStatus": "NOT_ARRIVED"}), "1. NOT_ARRIVED")
        write_req(db.procurement_requests.find_one({"_id": {"$regex": f"^{PREFIX}"}, "arrivalStatus": "ARRIVED", "requestStatus": "SCHEDULED"}), "2. ARRIVED and waiting")
        write_req(db.procurement_requests.find_one({"_id": {"$regex": f"^{PREFIX}"}, "requestStatus": "QC_IN_PROGRESS"}), "3. QC passed/in-progress")
        write_req(db.procurement_requests.find_one({"_id": {"$regex": f"^{PREFIX}"}, "requestStatus": "REJECTED"}), "4. Rejected")
        write_req(db.procurement_requests.find_one({"_id": {"$regex": f"^{PREFIX}"}, "requestStatus": "COMPLETED"}), "5. Completed")
        
        # F. QC TEST EXAMPLES
        f.write("\n## F. QC TEST EXAMPLES\n\n")
        
        qcs = list(db.qualityEvaluations.find({"_id": {"$regex": f"^{PREFIX}"}}).limit(3))
        for qc in qcs:
            f.write(f"### Evaluation: {qc['_id']}\n")
            f.write(f"- **QC Attempt**: {qc.get('qcAttemptId')} | **Grade**: {qc.get('grade')} | **Decision**: {qc.get('decision')}\n")
            f.write(f"- **Price/kg**: {qc.get('pricePerKg')}\n\n")
            
        # G. TRACEABILITY EXAMPLES
        f.write("\n## G. COMPLETE TRACEABILITY EXAMPLES\n\n")
        
        chains = list(db.procurement_requests.find({"_id": {"$regex": f"^{PREFIX}"}, "requestStatus": "COMPLETED"}).limit(3))
        for i, ch in enumerate(chains):
            f.write(f"### Chain {i+1} (Completed)\n")
            f.write(f"- **Farmer**: {ch['farmerId']}\n")
            f.write(f"- **Request**: {ch['_id']}\n")
            f.write(f"- **Lot**: {ch.get('lotId')}\n")
            
            qc = db.qualityChecks.find_one({"lotId": ch.get('lotId')})
            if qc:
                f.write(f"- **QC Attempt**: {qc['_id']}\n")
                eval = db.qualityEvaluations.find_one({"qcAttemptId": qc['_id']})
                if eval:
                    f.write(f"- **Evaluation**: {eval['_id']} (Grade {eval.get('grade')})\n")
                    
            w = db.weighments.find_one({"lotId": ch.get('lotId')})
            if w:
                f.write(f"- **Weighment**: {w['_id']}\n")
                
            p = db.governmentProcurements.find_one({"weighmentId": w['_id'] if w else None})
            if p:
                f.write(f"- **Procurement**: {p['_id']}\n")
                pay = db.payments.find_one({"procurementId": p['_id']})
                if pay:
                    f.write(f"- **Payment**: {pay['_id']}\n")
            f.write("\n")
            
        rej = db.procurement_requests.find_one({"_id": {"$regex": f"^{PREFIX}"}, "requestStatus": "REJECTED", "lotId": {"$ne": None}})
        if rej:
            f.write("### Chain (Rejected)\n")
            f.write(f"- **Farmer**: {rej['farmerId']}\n")
            f.write(f"- **Request**: {rej['_id']}\n")
            f.write(f"- **Lot**: {rej.get('lotId')}\n")
            qc = db.qualityChecks.find_one({"lotId": rej.get('lotId')})
            if qc:
                f.write(f"- **QC Attempt**: {qc['_id']}\n")
                eval = db.qualityEvaluations.find_one({"qcAttemptId": qc['_id']})
                if eval:
                    f.write(f"- **Evaluation**: {eval['_id']} (Grade {eval.get('grade')})\n")
            f.write("- **REJECTED**\n\n")
            
        # H & I. MANUAL SCENARIOS
        f.write("\n## H. MANUAL SCHEDULING TESTS\n\n")
        f.write("Use the provided actual DB records from Section E to test the UI flow:\n")
        f.write("1. **TEST 1**: Log in as a zero-transaction farmer, book a request, verify assignment logic.\n")
        f.write("2. **TEST 2**: Wait for slot capacity to run out, then observe new bookings divert to the next slot.\n\n")
        
        f.write("\n## I. MANUAL QUEUE TEST SCENARIOS\n\n")
        f.write("1. **Scenario A**: Open Command Centre, observe NOT_ARRIVED requests are bypassed for processing.\n")
        f.write("2. **Scenario B**: Observe multiple ARRIVED requests are sorted strictly by `queueNumber`.\n")

    print("Created stress_test_manifest.md!")
    
if __name__ == "__main__":
    main()
