# KisanOne SIH 2026 Demo Platform

## Goal
Build a polished, judge-ready procurement orchestration prototype where every officer, farmer, IVR, traceability, and government view responds to one shared simulation state.

## Product structure
- Create a responsive application shell with KisanOne branding, SIH26032 / Team SIH-83 identity, role-based navigation, centre status, connectivity, and a persistent Judge Demo launcher.
- Use focused views inside the main experience: Officer Command Centre, Farmer Experience, IVR Simulator, Five-ID Traceability, and Government Dashboard.
- Keep the Officer Command Centre as the default first screen and provide a compact mobile navigation pattern.

## Unified simulation engine
- Create one React context/reducer as the source of truth for the demo farmer, queue, pipeline stage, bottleneck state, arrival window, ETA, capacity, connectivity, queued offline actions, transaction, payment, SMS messages, and audit events.
- Implement all requested simulation actions and make each action update every dependent view consistently.
- Model the principle “AI advisory; Rules decide”: slowdown raises an advisory and independently triggers the deterministic pause/recalculation rule.
- Add resettable seeded data for Sehore and peer centres so the full story is reproducible.

## Judge Demo Mode
- Add a persistent “Start Judge Demo” control opening an 18-step guided walkthrough.
- Each step will present concise judge narration, highlight the relevant area, and optionally run its state transition.
- Include previous, next, play/pause auto-advance, current-step progress, reset, and close controls.
- Provide the complete manual simulation control set in an accessible drawer.

## Officer Command Centre
- Build centre header, five KPI tiles, operational pipeline, capacity intelligence, paired AI advisory/rule decision, call-to-come status, live queue, and timestamped event log.
- Make K1-104 move through Gate, QC, Weighment, Unloading, Procurement, and Payment with visible stage and ETA changes.
- Add operational dialogs for signed arrival validation, QC inspection, RS-232 weighment, procurement lot creation, and payment completion.

## Farmer, IVR, and notifications
- Build a mobile-first farmer view for Ramesh Kumar with bilingual call-to-come details, delay alerts, booking flow, queue tracking, and transaction history.
- Add an accessible telephone simulator with DTMF controls, transcript, browser speech playback where available, and stop control.
- Make IVR keys 1–3 and simulated SMS messages read directly from the shared queue and arrival state.

## Traceability and administration
- Build the interactive five-ID chain from farmer through payment, with inspectable provenance fields and deterministic demo SHA-256-style hashes.
- Build Sehore district and Madhya Pradesh oversight views with aggregate KPIs, peer-centre comparison, utilization bars, and bottleneck alerts.

## Visual system and quality
- Replace the starter palette with semantic navy, emerald, amber, red, and neutral tokens; use high-legibility government-service styling with compact data density and restrained motion.
- Add application-specific page metadata and remove all starter branding.
- Verify the full demo sequence, dialogs, shared-state reactions, offline queue/sync behavior, IVR transcript, desktop layout, and mobile farmer layout in the running preview.

## Technical details
- React 19 + TypeScript reducer/context; no backend is needed because this is a deterministic hackathon simulation.
- TanStack Router remains the application framework; the primary experience lives at `/`.
- Use existing Lucide icons, semantic Tailwind v4 tokens, native dialogs/accessible controls, and Web Speech synthesis as an enhancement with transcript fallback.
- Keep queue and capacity calculations deterministic so repeated demo runs produce the same evidence.
