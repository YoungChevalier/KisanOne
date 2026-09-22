# KisanOne Stress Test Manifest

This manifest is generated from ACTUAL records currently present in MongoDB.

## A. DATASET SUMMARY

Current counts in MongoDB (Total / Stress-prefixed):

- **farmers**: 5016 / 5000
- **auth_credentials**: 5020 / 5000
- **centres**: 22 / 20
- **employees**: 84 / 80
- **cropConfigurations**: 10 / 0
- **slots**: 6922 / 6912
- **procurement_requests**: 20000 / 20000
- **lots**: 15615 / 15588
- **qualityChecks**: 13282 / 13252
- **qualityEvaluations**: 13296 / 13252
- **weighments**: 6569 / 6547
- **governmentProcurements**: 4329 / 4309
- **payments**: 2215 / 2199
- **rulebooks**: 10 / 0

## B. REPRESENTATIVE FARMERS

A sample of actual farmer IDs covering different operational states.

#### 1. Farmer with zero transactions
### Ramesh Kumar (FMR-104)
- **District**: Sehore | **Area**: Sehore
- **Requests**: 0
- **Procurements**: 11
- **Payments**: 9

#### 2. Farmer with active request
### Stress Farmer 2005 (STRESS-FMR-2005)
- **District**: Pune | **Area**: South Zone
- **Requests**: 3
- **Procurements**: 0
- **Payments**: 0
- **Request IDs**: STRESS-REQ-100, STRESS-REQ-3391, STRESS-REQ-10849

#### 3. Farmer with ARRIVED request
### Stress Farmer 1281 (STRESS-FMR-1281)
- **District**: Indore | **Area**: South Zone
- **Requests**: 7
- **Procurements**: 0
- **Payments**: 0
- **Request IDs**: STRESS-REQ-1000, STRESS-REQ-2055, STRESS-REQ-2648, STRESS-REQ-5157, STRESS-REQ-11743, STRESS-REQ-13574, STRESS-REQ-18617

#### 4. Farmer with completed procurement/payment
### Stress Farmer 1064 (STRESS-FMR-1064)
- **District**: Bhopal | **Area**: Area-A
- **Requests**: 4
- **Procurements**: 0
- **Payments**: 0
- **Request IDs**: STRESS-REQ-0, STRESS-REQ-4938, STRESS-REQ-13879, STRESS-REQ-14409

#### 5. Farmer with rejected request
### Stress Farmer 4893 (STRESS-FMR-4893)
- **District**: Pune | **Area**: Area-C
- **Requests**: 2
- **Procurements**: 0
- **Payments**: 0
- **Request IDs**: STRESS-REQ-8636, STRESS-REQ-10004


## C. REPRESENTATIVE CENTRES

### Stress Centre 0 (STRESS-CNT-0)
- **District**: Bhopal | **Area**: Area-A
- **Crops**: 
- **Daily Capacity**: 486123 kg
- **Status**: ACTIVE

### Stress Centre 1 (STRESS-CNT-1)
- **District**: Sehore | **Area**: Area-A
- **Crops**: 
- **Daily Capacity**: 221981 kg
- **Status**: ACTIVE

### Stress Centre 10 (STRESS-CNT-10)
- **District**: Bhopal | **Area**: Area-B
- **Crops**: 
- **Daily Capacity**: 307425 kg
- **Status**: ACTIVE


## D. REPRESENTATIVE SLOTS

### 1. Empty Available Slot: STRESS-SLT-STRESS-CNT-0-ONION-2026-09-19-14
- **Centre**: STRESS-CNT-0 | **Crop**: ONION
- **Date**: 2026-09-19 00:00:00 | **Time**: 14:00:00 - 16:00:00
- **Capacity**: 31892 kg | **Allocated**: 0 kg | **Remaining**: 42
- **Farmers**: 0/42
- **Status**: AVAILABLE

### 2. Partially Filled Slot: STRESS-SLT-STRESS-CNT-0-ONION-2026-09-19-16
- **Centre**: STRESS-CNT-0 | **Crop**: ONION
- **Date**: 2026-09-19 00:00:00 | **Time**: 16:00:00 - 18:00:00
- **Capacity**: 16443 kg | **Allocated**: 13700 kg | **Remaining**: 20
- **Farmers**: 53/73
- **Status**: AVAILABLE

### 3. Full Slot: STRESS-SLT-STRESS-CNT-0-RICE-2026-09-30-11
- **Centre**: STRESS-CNT-0 | **Crop**: RICE
- **Date**: 2026-09-30 00:00:00 | **Time**: 11:00:00 - 13:00:00
- **Capacity**: 11692 kg | **Allocated**: 7708 kg | **Remaining**: 0
- **Farmers**: 24/24
- **Status**: FULL


## E. REPRESENTATIVE REQUESTS

### 1. NOT_ARRIVED: STRESS-REQ-10012
- **Farmer**: STRESS-FMR-4593 | **Crop**: SOYBEAN
- **Centre**: STRESS-CNT-18 | **Slot**: STRESS-SLT-STRESS-CNT-18-SOYBEAN-2026-10-19-9
- **Queue Number**: 10013
- **Qty**: 134 kg
- **Arrival**: NOT_ARRIVED | **Status**: SCHEDULED

### 2. ARRIVED and waiting: STRESS-REQ-1000
- **Farmer**: STRESS-FMR-1281 | **Crop**: WHEAT
- **Centre**: STRESS-CNT-16 | **Slot**: STRESS-SLT-STRESS-CNT-16-WHEAT-2026-10-03-14
- **Queue Number**: 1001
- **Qty**: 209 kg
- **Arrival**: ARRIVED | **Status**: SCHEDULED

### 3. QC passed/in-progress: STRESS-REQ-100
- **Farmer**: STRESS-FMR-2005 | **Crop**: WHEAT
- **Centre**: STRESS-CNT-18 | **Slot**: STRESS-SLT-STRESS-CNT-18-WHEAT-2026-10-11-9
- **Queue Number**: 101
- **Qty**: 590 kg
- **Arrival**: ARRIVED | **Status**: QC_IN_PROGRESS
- **Lot**: STRESS-LOT-100

### 4. Rejected: STRESS-REQ-10004
- **Farmer**: STRESS-FMR-4893 | **Crop**: RICE
- **Centre**: STRESS-CNT-7 | **Slot**: STRESS-SLT-STRESS-CNT-7-RICE-2026-09-19-9
- **Queue Number**: 10005
- **Qty**: 464 kg
- **Arrival**: ARRIVED | **Status**: REJECTED
- **Lot**: STRESS-LOT-10004

### 5. Completed: STRESS-REQ-0
- **Farmer**: STRESS-FMR-1064 | **Crop**: RICE
- **Centre**: STRESS-CNT-10 | **Slot**: STRESS-SLT-STRESS-CNT-10-RICE-2026-09-23-11
- **Queue Number**: 1
- **Qty**: 517 kg
- **Arrival**: ARRIVED | **Status**: COMPLETED
- **Lot**: STRESS-LOT-0


## F. QC TEST EXAMPLES

### Evaluation: STRESS-EVAL-0
- **QC Attempt**: STRESS-QC-0 | **Grade**: A | **Decision**: PASS
- **Price/kg**: None

### Evaluation: STRESS-EVAL-1
- **QC Attempt**: STRESS-QC-1 | **Grade**: F | **Decision**: FAIL
- **Price/kg**: None

### Evaluation: STRESS-EVAL-10
- **QC Attempt**: STRESS-QC-10 | **Grade**: A | **Decision**: PASS
- **Price/kg**: None


## G. COMPLETE TRACEABILITY EXAMPLES

### Chain 1 (Completed)
- **Farmer**: STRESS-FMR-1064
- **Request**: STRESS-REQ-0
- **Lot**: STRESS-LOT-0
- **QC Attempt**: STRESS-QC-0
- **Evaluation**: STRESS-EVAL-0 (Grade A)
- **Weighment**: STRESS-WGT-0

### Chain 2 (Completed)
- **Farmer**: STRESS-FMR-653
- **Request**: STRESS-REQ-10006
- **Lot**: STRESS-LOT-10006
- **QC Attempt**: STRESS-QC-10006
- **Evaluation**: STRESS-EVAL-10006 (Grade A)
- **Weighment**: STRESS-WGT-10006

### Chain 3 (Completed)
- **Farmer**: STRESS-FMR-3758
- **Request**: STRESS-REQ-10011
- **Lot**: STRESS-LOT-10011
- **QC Attempt**: STRESS-QC-10011
- **Evaluation**: STRESS-EVAL-10011 (Grade A)
- **Weighment**: STRESS-WGT-10011

### Chain (Rejected)
- **Farmer**: STRESS-FMR-4893
- **Request**: STRESS-REQ-10004
- **Lot**: STRESS-LOT-10004
- **QC Attempt**: STRESS-QC-10004
- **Evaluation**: STRESS-EVAL-10004 (Grade F)
- **REJECTED**


## H. MANUAL SCHEDULING TESTS

Use the provided actual DB records from Section E to test the UI flow:
1. **TEST 1**: Log in as a zero-transaction farmer, book a request, verify assignment logic.
2. **TEST 2**: Wait for slot capacity to run out, then observe new bookings divert to the next slot.


## I. MANUAL QUEUE TEST SCENARIOS

1. **Scenario A**: Open Command Centre, observe NOT_ARRIVED requests are bypassed for processing.
2. **Scenario B**: Observe multiple ARRIVED requests are sorted strictly by `queueNumber`.
