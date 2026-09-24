# Kisan Smart Flow

Build KisanOne ("One Platform. One Process. One Farmer."), a smart procurement orchestration platform for Smart India Hackathon 2026 (SIH26032, Team SIH-83 CodeOps).

Core Innovation & Concept:
Capacity Intelligence Engine + Dynamic Call-to-Come + Live Queue with Dynamic ETA. Grounded in the submitted SIH-83 presentation:
"Instead of asking farmers to wait for the procurement centre, KisanOne makes the procurement centre tell farmers when to come."
Architecture principle: "AI advisory; Rules decide".

Major Interactive Screens & Unified Shared State (All screens MUST react to the exact same state):
1. JUDGE DEMO MODE & DEMO CONTROLLER:
   - Sticky top or accessible drawer "START JUDGE DEMO" 18-step interactive walkthrough with step-by-step narrative and auto-advance / manual step controls.
   - Demo controls: [Reset Demo], [Simulate Farmer Request], [Simulate Farmer Arrival], [Simulate Weighbridge Slowdown (12->6/hr)], [Restore Weighbridge (12/hr)], [Complete QC], [Simulate Weight (RS-232 WB-04)], [Complete Procurement], [Complete Payment], [Switch Offline], [Restore Connectivity].
   - Offline-first toggle showing local queued actions and auto-sync badge.

2. OFFICER COMMAND CENTRE (Primary screen for Sehore Procurement Centre, MP):
   - Header with centre status (Operational/Overloaded), connectivity indicator (Online/Offline local sync).
   - Top KPI cards: Farmers Today (142), Processed (97), In Queue (18), Average Wait (21 min), Capacity (78%).
   - Live Operational Pipeline: Gate -> QC -> Weighment -> Unloading -> Procurement -> Payment, showing active counts, avg times, and allows moving demo farmer K1-104 through stages with visual badges.
   - Capacity Intelligence Engine: Live load, capacity, utilization for Gate (78%), QC (71%), Weighment (94% -> Warning Limiting Resource), Unloading (62%), Storage (48%).
   - AI Advisory Card ("Weighbridge risk detected, +22 min impact") -> paired with Rule Engine Decision ("PAUSE CALL-TO-COME").
   - Dynamic Call-to-Come status box: Active/Paused, Next release, Farmers released (6), Farmers waiting (12).
   - Live Queue Table: Position, Farmer, Request ID, Arrival Window, Stage, ETA, Status, with real-time recalculation indicators.
   - Operational modals/screens:
     * Arrival Validation: Farmer ID + Request ID validation, Simulated Signed QR scanner/modal, timestamp 10:43 AM, OP-07, GATE-02.
     * QC Inspection: Moisture 12.4%, Foreign Matter 1.8%, Grade A, Pass/Flag actions.
     * Weighment Console: Simulated Device Stream (RS-232 WB-04, 52.40 KG, Simulate Weight, Confirm Weight).
     * Procurement & Payment Transaction: Lot generation, rate ₹2,275/qtl (Wheat MSP), gross calculation, mark payment completed.
   - Recent Events audit log with real-time timestamps.

3. FARMER EXPERIENCE (Mobile-responsive & bilingual Hindi/English hints):
   - Farmer profile: Ramesh Kumar (FMR-104), Request K1-104, Wheat, Sehore Procurement Centre.
   - Prominent Call-to-Come Card with Hindi labels ("आगमन समय" / Arrival Window: 10:40 AM - 10:55 AM, "अनुमानित प्रतीक्षा समय" / Estimated Wait: 18 min, Queue #4, Operational advice).
   - When bottleneck hits: Arrival window updates to 11:05 AM with clear alert banner explaining capacity slowdown.
   - "Book Procurement" functional flow: Farmer ID, Crop, Quantity (52.4 kg), Centre selection -> generates Request K1-104 -> Capacity engine approval -> Call-to-Come issued.
   - Live Queue tracking tab and Payment / Transaction History tab.

4. IVR SIMULATOR (Accessible telephone simulation with DTMF dialpad & audio/TTS voice feedback):
   - Dialpad (1-9, *, 0, #), Play/Stop audio button, live transcript display.
   - Key 1: Status of request K1-104.
   - Key 2: Call-to-Come window (synchronously announces 10:40-10:55 AM before bottleneck, and dynamically changes to 11:05 AM after bottleneck).
   - Key 3: Queue position & ETA.
   - Multichannel SMS simulator drawer showing SMS alerts sent to farmers.

5. FIVE-ID TRACEABILITY & TAMPER-EVIDENT AUDIT:
   - Interactive flow: Farmer (FMR-104) -> Request (K1-104) -> Lot (LOT-2026-0104) -> Transaction (TXN-10482) -> Payment (PAY-10482).
   - Inspectable node cards displaying Created By, Timestamp, Operator, Device, Status, and SHA-256 demo hash.

6. GOVERNMENT / ADMIN MONITORING DASHBOARD:
   - High-level District (Sehore, MP) and State overview with peer centres (Bhopal, Raisen, Vidisha, Sehore), comparative bottleneck alerts, and aggregate procurement KPIs.

Design style:
Official Indian Agricultural Procurement System aesthetic (Government of India / MP e-Uparjan / e-NAM inspired). Deep navy/slate header (#1e293b / #0f172a), restrained agricultural emerald/green accents (#15803d), crisp light backgrounds, amber warnings, high legibility, clean status chips, and professional typography. No crypto/flashy neon gradients. Highly robust interactive state in React/TypeScript.

This project was built with [Lovable](https://lovable.dev).

## Build with Lovable

Continue developing this project in the [Lovable editor](https://lovable.dev/projects/ca0ae274-15da-405b-82cb-a1d20f204484).

- **Ship faster**: describe what you want to build and Lovable handles the code.
- **Stay in sync**: every change made in Lovable is committed straight to this repository.
- **Full ownership**: this code is yours. Push to `main` on GitHub and your changes sync back into Lovable, ready for your next prompt.

## Development

Prefer working locally? You need Node.js and npm — [install with nvm](https://github.com/nvm-sh/nvm#installing-and-updating).

```sh
git clone <this-repository-url>
cd <repository-name>
npm i
npm run dev
```
