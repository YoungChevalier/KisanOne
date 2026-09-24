/**
 * Real operation dialogs that collect user input and call the KisanOne backend.
 * Each dialog replaces the original static display with actual form fields + API calls.
 */
import { useEffect, useState } from "react";
import { Check, AlertTriangle, Loader2, RotateCcw, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useDemo, type DemoAction } from "@/lib/kisan-state";
import * as api from "@/lib/api";

export type DialogKind = "arrival" | "qc" | "weight" | "procure" | "payment" | "booking" | null;

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div><label className="text-xs font-semibold text-muted-foreground">{label}</label><div className="mt-1">{children}</div></div>;
}

function Input({ value, onChange, placeholder, type = "text", disabled }: { value: string; onChange: (v: string) => void; placeholder?: string; type?: string; disabled?: boolean }) {
  return <input type={type} value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder} disabled={disabled} className="w-full rounded-md border bg-background px-3 py-2 text-sm disabled:opacity-50" />;
}

function Select({ value, onChange, options, placeholder, disabled }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; placeholder?: string; disabled?: boolean }) {
  return <select value={value} onChange={e => onChange(e.target.value)} disabled={disabled} className="w-full rounded-md border bg-background px-3 py-2 text-sm disabled:opacity-50">
    {placeholder && <option value="">{placeholder}</option>}
    {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
  </select>;
}

function ResultRow({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return <div><label className="text-xs font-semibold text-muted-foreground">{label}</label><div className={`mt-1 rounded-md border bg-muted/30 px-3 py-2 text-sm font-medium ${highlight ? "text-primary font-bold" : ""}`}>{value}</div></div>;
}

function ErrorBanner({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="flex gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"><AlertTriangle className="size-4 shrink-0 mt-0.5" />{error}</div>;
}

// ─── Booking Dialog ─────────────────────────────────────────────────────────────

function BookingForm({ onDone }: { onDone: () => void }) {
  const { state, dispatch } = useDemo();
  const [farmers, setFarmers] = useState<api.Farmer[]>([]);
  const [employees, setEmployees] = useState<api.Employee[]>([]);
  const [mode, setMode] = useState<"select" | "create">("select");
  const [farmerId, setFarmerId] = useState("");
  const [newName, setNewName] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newDistrict, setNewDistrict] = useState("");
  const [newArea, setNewArea] = useState("");
  const [cropCode, setCropCode] = useState("");
  const [area, setArea] = useState("");
  const [qty, setQty] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<api.ProcurementRequest | null>(null);

  useEffect(() => {
    api.listFarmers().then(setFarmers).catch(() => {});
    api.listEmployees().then(setEmployees).catch(() => {});
  }, []);

  const submit = async () => {
    setError(null);
    setLoading(true);
    try {
      let fId = farmerId;
      let fName = farmers.find(f => f.farmerId === fId)?.name ?? "";
      let fArea = area;

      if (mode === "create") {
        const fData: api.Farmer = {
          farmerId: `FMR-${Date.now()}`,
          name: newName,
          phone: newPhone,
          address: `${newArea}, ${newDistrict}`,
          district: newDistrict,
          area: newArea,
          preferredLanguage: "Hindi",
          ekycVerified: true,
        };
        const created = await api.createFarmer(fData);
        fId = created.farmerId;
        fName = created.name;
        fArea = fArea || newArea;
      }

      if (!fId) throw new Error("Please select or create a farmer");
      if (!cropCode) throw new Error("Please enter a crop");
      if (!qty || Number(qty) <= 0) throw new Error("Please enter a valid quantity");

      const farmer = farmers.find(f => f.farmerId === fId);
      const reqArea = fArea || farmer?.area || "";

      const reqId = `REQ-${Date.now()}`;
      const res = await api.createProcurementRequest({
        requestId: reqId,
        farmerId: fId,
        cropCode,
        farmerArea: reqArea || undefined,
        expectedQuantityKg: Number(qty),
        autoAssign: true,
      });

      dispatch({ type: "SET_TX", data: {
        farmerId: fId,
        farmerName: fName || fId,
        cropCode,
        farmerArea: reqArea,
        expectedQuantityKg: Number(qty),
        requestId: res.requestId,
        assignedCentreId: res.assignedCentreId,
        assignedSlotId: res.assignedSlotId,
        employeeId: employees[0]?.employeeId ?? null,
      }});
      dispatch({ type: "REQUEST" });
      setResult(res);
    } catch (e) {
      setError(e instanceof api.ApiError ? e.detail : (e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  if (result) return <>
    <div className="rounded-md bg-success-muted p-3 text-sm text-success"><Check className="mr-1 inline size-4" />Procurement request created successfully!</div>
    <ResultRow label="Request ID" value={result.requestId} highlight />
    <ResultRow label="Farmer" value={state.tx.farmerName ?? result.farmerId} />
    <ResultRow label="Crop" value={result.cropCode} />
    <ResultRow label="Assigned Centre" value={result.assignedCentreId} highlight />
    <ResultRow label="Assigned Slot" value={result.assignedSlotId} highlight />
    <ResultRow label="Status" value={result.status} />
    <DialogFooter><Button onClick={onDone}><Check />Done</Button></DialogFooter>
  </>;

  return <>
    <ErrorBanner error={error} />
    <div className="flex gap-2">
      <Button size="sm" variant={mode === "select" ? "default" : "outline"} onClick={() => setMode("select")}>Select Existing Farmer</Button>
      <Button size="sm" variant={mode === "create" ? "default" : "outline"} onClick={() => setMode("create")}>Create New Farmer</Button>
    </div>
    {mode === "select" ? (
      <Field label="Farmer / किसान">
        <Select value={farmerId} onChange={setFarmerId} options={farmers.map(f => ({ value: f.farmerId, label: `${f.name} (${f.farmerId})` }))} placeholder="Select a farmer..." />
      </Field>
    ) : (<>
      <Field label="Farmer Name"><Input value={newName} onChange={setNewName} placeholder="e.g. Ramesh Kumar" /></Field>
      <Field label="Phone"><Input value={newPhone} onChange={setNewPhone} placeholder="+919876543210" /></Field>
      <Field label="District"><Input value={newDistrict} onChange={setNewDistrict} placeholder="e.g. Bhopal" /></Field>
      <Field label="Area"><Input value={newArea} onChange={setNewArea} placeholder="e.g. Sehore" /></Field>
    </>)}
    <Field label="Crop / फसल">
      <Input value={cropCode} onChange={setCropCode} placeholder="e.g. WHEAT" />
    </Field>
    <Field label="Area / क्षेत्र (for slot assignment)">
      <Input value={area} onChange={setArea} placeholder="e.g. Area-A" />
    </Field>
    <Field label="Expected Quantity (kg) / अपेक्षित मात्रा">
      <Input value={qty} onChange={setQty} placeholder="e.g. 500" type="number" />
    </Field>
    <DialogFooter>
      <Button variant="outline" onClick={onDone}>Cancel</Button>
      <Button onClick={submit} disabled={loading}>{loading && <Loader2 className="animate-spin" />}{loading ? "Creating..." : "Submit Request"}</Button>
    </DialogFooter>
  </>;
}

// ─── Arrival Dialog ─────────────────────────────────────────────────────────────

function ArrivalForm({ onDone }: { onDone: () => void }) {
  const { state, dispatch } = useDemo();
  const [employees, setEmployees] = useState<api.Employee[]>([]);
  const [employeeId, setEmployeeId] = useState(state.tx.employeeId ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<api.ArrivalResult | null>(null);

  useEffect(() => {
    api.listEmployees().then(emps => {
      setEmployees(emps);
      if (!employeeId) {
        const match = emps.find(e => e.centreId === (state.tx.assignedCentreId || "MP-SEH-04") && e.status === "ACTIVE");
        if (match) setEmployeeId(match.employeeId);
      }
    }).catch(() => {});
  }, []);

  const submit = async () => {
    setError(null);
    if (!state.tx.requestId) { setError("No procurement request. Please create one first."); return; }
    if (!state.tx.farmerId) { setError("No farmer ID in current transaction."); return; }
    if (!employeeId) { setError("Please select an employee."); return; }
    setLoading(true);
    try {
      const res = await api.markArrival(state.tx.requestId, { farmerId: state.tx.farmerId, employeeId });
      dispatch({ type: "SET_TX", data: { lotId: res.lotId, employeeId } });
      dispatch({ type: "ARRIVE" });
      setResult(res);
    } catch (e) {
      setError(e instanceof api.ApiError ? e.detail : (e as Error).message);
    } finally { setLoading(false); }
  };

  if (result) return <>
    <div className="rounded-md bg-success-muted p-3 text-sm text-success"><Check className="mr-1 inline size-4" />Arrival validated! Lot created.</div>
    <ResultRow label="Request ID" value={result.requestId} />
    <ResultRow label="Lot ID" value={result.lotId} highlight />
    <ResultRow label="Status" value={result.status} />
    <DialogFooter><Button onClick={onDone}><Check />Done</Button></DialogFooter>
  </>;

  return <>
    <ErrorBanner error={error} />
    <ResultRow label="Request ID" value={state.tx.requestId ?? "—"} />
    <ResultRow label="Farmer" value={`${state.tx.farmerName ?? "—"} (${state.tx.farmerId ?? "—"})`} />
    <Field label="Validating Employee">
      <Select value={employeeId} onChange={setEmployeeId} options={employees.filter(e => e.status === "ACTIVE").map(e => ({ value: e.employeeId, label: `${e.name} (${e.role})` }))} placeholder="Select employee..." />
    </Field>
    <DialogFooter>
      <Button variant="outline" onClick={onDone}>Cancel</Button>
      <Button onClick={submit} disabled={loading || !state.tx.requestId}>{loading && <Loader2 className="animate-spin" />}{loading ? "Validating..." : "Validate & Admit"}</Button>
    </DialogFooter>
  </>;
}

// ─── QC Dialog ──────────────────────────────────────────────────────────────────

function QCForm({ onDone }: { onDone: () => void }) {
  const { state, dispatch } = useDemo();
  const [employees, setEmployees] = useState<api.Employee[]>([]);
  const [employeeId, setEmployeeId] = useState(state.tx.employeeId ?? "");
  const [cropConfig, setCropConfig] = useState<api.CropConfig | null>(null);
  const [tests, setTests] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<api.QCEvaluation | null>(null);

  useEffect(() => {
    api.listEmployees().then(emps => {
      setEmployees(emps);
      if (!employeeId) {
        const match = emps.find(e => e.centreId === (state.tx.assignedCentreId || "MP-SEH-04") && e.status === "ACTIVE");
        if (match) setEmployeeId(match.employeeId);
      }
    }).catch(() => {});
    if (state.tx.cropCode) {
      api.getCropConfig(state.tx.cropCode).then(c => {
        setCropConfig(c);
        const init: Record<string, string> = {};
        c.qualityTests.forEach(t => { init[t.testCode] = ""; });
        setTests(init);
      }).catch(() => {});
    }
  }, [state.tx.cropCode]);

  const submit = async () => {
    setError(null);
    if (!state.tx.lotId) { setError("No Lot ID. Please validate arrival first."); return; }
    if (!employeeId) { setError("Please select a QC officer."); return; }

    const numTests: Record<string, number> = {};
    for (const [code, val] of Object.entries(tests)) {
      if (val === "") { setError(`Please enter a value for ${code}`); return; }
      numTests[code] = Number(val);
    }

    setLoading(true);
    try {
      const qc = await api.submitQualityCheck(state.tx.lotId, { employeeId, tests: numTests });
      const ev = await api.evaluateQC(qc.qcAttemptId);
      dispatch({ type: "SET_TX", data: {
        qcAttemptId: qc.qcAttemptId,
        qcGrade: ev.grade,
        qcDecision: ev.decision,
        qcPricePerKg: ev.pricePerKg,
        qcEvaluation: ev.testResults,
        employeeId,
      }});
      dispatch({ type: "QC" });
      setEvaluation(ev);
    } catch (e) {
      setError(e instanceof api.ApiError ? e.detail : (e as Error).message);
    } finally { setLoading(false); }
  };

  const [rejecting, setRejecting] = useState(false);

  const handleReject = async () => {
    if (!state.tx.requestId) return;
    if (!window.confirm(`Are you sure you want to REJECT request ${state.tx.requestId}? This will permanently mark the request and lot as REJECTED and close it.`)) {
      return;
    }
    setRejecting(true);
    setError(null);
    try {
      let empId = employeeId;
      if (!empId) {
        const targetCentre = state.tx.assignedCentreId || "MP-SEH-04";
        const match = employees.find(e => e.centreId === targetCentre && e.status === "ACTIVE");
        empId = match?.employeeId || "EMP-01";
      }
      await api.rejectProcurementRequest(state.tx.requestId, {
        employeeId: empId,
        rejectionReason: `QC Failed: Grade F (${evaluation?.decision ?? "FAIL"})`,
      });
      dispatch({ type: "REJECT" });
      onDone();
    } catch (e) {
      setError(e instanceof api.ApiError ? e.detail : (e as Error).message);
      setRejecting(false);
    }
  };

  if (evaluation) {
    const isF = evaluation.grade === "F";
    return <>
      <div className={`rounded-md p-3 text-sm ${isF ? "bg-destructive/10 text-destructive" : "bg-success-muted text-success"}`}>
        {isF ? <><AlertTriangle className="mr-1 inline size-4" />Quality Failed (Grade F) — Procurement Blocked</> : <><Check className="mr-1 inline size-4" />Quality Check Passed!</>}
      </div>
      <div className="grid grid-cols-2 gap-3">
        <ResultRow label="Grade" value={evaluation.grade} highlight />
        <ResultRow label="Decision" value={evaluation.decision} highlight />
        <ResultRow label="Price / kg" value={`₹${evaluation.pricePerKg}`} highlight />
        <ResultRow label="QC Attempt ID" value={evaluation.qcAttemptId} />
        <ResultRow label="Rulebook" value={evaluation.rulebookId} />
        <ResultRow label="Version" value={String(evaluation.rulebookVersion)} />
      </div>
      {evaluation.testResults && <div className="rounded-md border p-3">
        <p className="text-xs font-bold uppercase text-muted-foreground mb-2">Test-by-Test Results</p>
        {Object.entries(evaluation.testResults).map(([k, v]) => <div key={k} className="flex justify-between text-xs py-1 border-b last:border-0">
          <span>{k}</span><span className="font-mono">{JSON.stringify(v)}</span>
        </div>)}
      </div>}
      {isF && <div className="rounded-md border border-destructive/30 bg-destructive/5 p-3 text-sm">
        <strong>Grade F Action Required:</strong> This lot failed quality specifications. You may perform an immediate retest if allowed, or explicitly reject and terminate the request to remove it from the operational queue.
      </div>}
      <DialogFooter className="flex-col sm:flex-row gap-2">
        {isF ? (
          <>
            <Button variant="outline" onClick={() => setEvaluation(null)}>
              <RotateCcw className="mr-1 size-4" />Retest QC
            </Button>
            <Button variant="destructive" onClick={handleReject} disabled={rejecting}>
              {rejecting ? <Loader2 className="animate-spin mr-1 size-4" /> : <XCircle className="mr-1 size-4" />}
              {rejecting ? "Rejecting..." : "Reject Request"}
            </Button>
            <Button variant="ghost" onClick={onDone}>Close</Button>
          </>
        ) : (
          <Button onClick={onDone}><Check />Done</Button>
        )}
      </DialogFooter>
    </>;
  }

  return <>
    <ErrorBanner error={error} />
    <ResultRow label="Lot ID" value={state.tx.lotId ?? "—"} />
    <ResultRow label="Crop" value={state.tx.cropCode ?? "—"} />
    <Field label="QC Officer">
      <Select value={employeeId} onChange={setEmployeeId} options={employees.filter(e => e.status === "ACTIVE").map(e => ({ value: e.employeeId, label: `${e.name} (${e.role})` }))} placeholder="Select QC officer..." />
    </Field>
    {cropConfig ? (
      <div className="space-y-3">
        <p className="text-xs font-bold uppercase text-muted-foreground">Quality Measurements (from crop config)</p>
        {cropConfig.qualityTests.map(t => (
          <Field key={t.testCode} label={`${t.testName} (${t.unit}) ${t.required ? "*" : ""}`}>
            <Input value={tests[t.testCode] ?? ""} onChange={v => setTests(prev => ({ ...prev, [t.testCode]: v }))} placeholder={`Enter ${t.testName}`} type="number" />
          </Field>
        ))}
      </div>
    ) : <p className="text-sm text-muted-foreground">Loading crop configuration...</p>}
    <DialogFooter>
      <Button variant="outline" onClick={onDone}>Cancel</Button>
      <Button onClick={submit} disabled={loading || !state.tx.lotId}>{loading && <Loader2 className="animate-spin" />}{loading ? "Evaluating..." : "Submit & Evaluate"}</Button>
    </DialogFooter>
  </>;
}

// ─── Weighment Dialog ───────────────────────────────────────────────────────────

function WeighmentForm({ onDone }: { onDone: () => void }) {
  const { state, dispatch } = useDemo();
  const [employees, setEmployees] = useState<api.Employee[]>([]);
  const [employeeId, setEmployeeId] = useState(state.tx.employeeId ?? "");
  const [gross, setGross] = useState("");
  const [tare, setTare] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<api.Weighment | null>(null);

  useEffect(() => { api.listEmployees().then(setEmployees).catch(() => {}); }, []);

  // Grade F check - Weighment not allowed
  if (state.tx.qcGrade === "F") {
    return <>
      <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm">
        <div className="flex items-center gap-2 text-destructive font-bold"><AlertTriangle className="size-5" />Grade F — Weighment Not Allowed</div>
        <p className="mt-2 text-muted-foreground">This lot received Grade F (FAIL). Produce cannot proceed to weighment or government procurement. Perform a QC retest to obtain a passing grade, or reject the request.</p>
      </div>
      <DialogFooter><Button variant="outline" onClick={onDone}>Close</Button></DialogFooter>
    </>;
  }

  const submit = async () => {
    setError(null);
    if (!state.tx.lotId) { setError("No Lot ID. Please validate arrival first."); return; }
    if (!employeeId) { setError("Please select an employee."); return; }
    if (!gross || Number(gross) <= 0) { setError("Enter a valid gross weight."); return; }
    if (!tare || Number(tare) < 0) { setError("Enter a valid tare weight."); return; }
    if (Number(tare) >= Number(gross)) { setError("Tare weight must be less than gross weight."); return; }
    setLoading(true);
    try {
      const res = await api.createWeighment(state.tx.lotId, { employeeId, grossWeightKg: Number(gross), tareWeightKg: Number(tare) });
      dispatch({ type: "SET_TX", data: {
        weighmentId: res.weighmentId,
        grossWeightKg: res.grossWeightKg,
        tareWeightKg: res.tareWeightKg,
        netWeightKg: res.netWeightKg,
        employeeId,
      }});
      dispatch({ type: "WEIGHT" });
      setResult(res);
    } catch (e) {
      setError(e instanceof api.ApiError ? e.detail : (e as Error).message);
    } finally { setLoading(false); }
  };

  if (result) return <>
    <div className="rounded-md bg-success-muted p-3 text-sm text-success"><Check className="mr-1 inline size-4" />Weighment recorded!</div>
    <div className="grid grid-cols-2 gap-3">
      <ResultRow label="Weighment ID" value={result.weighmentId} highlight />
      <ResultRow label="Lot ID" value={result.lotId} />
      <ResultRow label="Gross Weight" value={`${result.grossWeightKg} kg`} />
      <ResultRow label="Tare Weight" value={`${result.tareWeightKg} kg`} />
    </div>
    <ResultRow label="Net Weight (backend-calculated)" value={`${result.netWeightKg} kg`} highlight />
    <DialogFooter><Button onClick={onDone}><Check />Done</Button></DialogFooter>
  </>;

  return <>
    <ErrorBanner error={error} />
    <ResultRow label="Lot ID" value={state.tx.lotId ?? "—"} />
    <Field label="Weighment Officer">
      <Select value={employeeId} onChange={setEmployeeId} options={employees.filter(e => e.status === "ACTIVE").map(e => ({ value: e.employeeId, label: `${e.name} (${e.role})` }))} placeholder="Select employee..." />
    </Field>
    <Field label="Gross Weight (kg)">
      <Input value={gross} onChange={setGross} placeholder="e.g. 1000" type="number" />
    </Field>
    <Field label="Tare Weight (kg)">
      <Input value={tare} onChange={setTare} placeholder="e.g. 50" type="number" />
    </Field>
    <DialogFooter>
      <Button variant="outline" onClick={onDone}>Cancel</Button>
      <Button onClick={submit} disabled={loading || !state.tx.lotId}>{loading && <Loader2 className="animate-spin" />}{loading ? "Recording..." : "Confirm Weight"}</Button>
    </DialogFooter>
  </>;
}

// ─── Procurement Dialog ─────────────────────────────────────────────────────────

function ProcurementForm({ onDone }: { onDone: () => void }) {
  const { state, dispatch } = useDemo();
  const [employees, setEmployees] = useState<api.Employee[]>([]);
  const [employeeId, setEmployeeId] = useState(state.tx.employeeId ?? "");
  const [qty, setQty] = useState(state.tx.netWeightKg?.toString() ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<api.GovProcurement | null>(null);

  useEffect(() => { api.listEmployees().then(setEmployees).catch(() => {}); }, []);

  // Grade F check
  if (state.tx.qcGrade === "F") {
    return <>
      <div className="rounded-md border border-destructive/40 bg-destructive/10 p-4 text-sm">
        <div className="flex items-center gap-2 text-destructive font-bold"><AlertTriangle className="size-5" />Grade F — Procurement Not Allowed</div>
        <p className="mt-2 text-muted-foreground">This lot received Grade F (FAIL). Procurement cannot proceed. Perform a QC retest to obtain a passing grade.</p>
        <p className="mt-1 text-muted-foreground">Price = ₹0.00</p>
      </div>
      <DialogFooter><Button variant="outline" onClick={onDone}>Close</Button></DialogFooter>
    </>;
  }

  const submit = async () => {
    setError(null);
    if (!state.tx.lotId) { setError("No Lot. Validate arrival first."); return; }
    if (!state.tx.weighmentId) { setError("No weighment. Record weighment first."); return; }
    if (!state.tx.qcAttemptId) { setError("No QC attempt. Perform QC first."); return; }
    if (!employeeId) { setError("Select an employee."); return; }
    if (!qty || Number(qty) <= 0) { setError("Enter a valid procurement quantity."); return; }
    setLoading(true);
    try {
      const res = await api.createGovProcurement(state.tx.lotId, {
        weighmentId: state.tx.weighmentId,
        procurementQuantityKg: Number(qty),
        qcAttemptId: state.tx.qcAttemptId,
        employeeId,
      });
      dispatch({ type: "SET_TX", data: {
        procurementId: res.procurementId,
        grossAmount: res.grossAmount,
      }});
      dispatch({ type: "PROCURE" });
      setResult(res);
    } catch (e) {
      setError(e instanceof api.ApiError ? e.detail : (e as Error).message);
    } finally { setLoading(false); }
  };

  if (result) return <>
    <div className="rounded-md bg-success-muted p-3 text-sm text-success"><Check className="mr-1 inline size-4" />Government Procurement created!</div>
    <div className="grid grid-cols-2 gap-3">
      <ResultRow label="Procurement ID" value={result.procurementId} highlight />
      <ResultRow label="Lot ID" value={result.lotId} />
      <ResultRow label="Grade" value={result.qualityGrade} highlight />
      <ResultRow label="Price / kg" value={`₹${result.pricePerKg}`} highlight />
      <ResultRow label="Quantity" value={`${result.procurementQuantityKg} kg`} />
      <ResultRow label="Gross Amount" value={`₹${result.grossAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`} highlight />
    </div>
    <DialogFooter><Button onClick={onDone}><Check />Done</Button></DialogFooter>
  </>;

  return <>
    <ErrorBanner error={error} />
    <ResultRow label="Lot ID" value={state.tx.lotId ?? "—"} />
    <ResultRow label="QC Grade" value={`${state.tx.qcGrade ?? "—"} (${state.tx.qcDecision ?? "—"}) · ₹${state.tx.qcPricePerKg ?? 0}/kg`} />
    <ResultRow label="Net Weight" value={`${state.tx.netWeightKg ?? "—"} kg`} />
    <Field label="Procurement Officer">
      <Select value={employeeId} onChange={setEmployeeId} options={employees.filter(e => e.status === "ACTIVE").map(e => ({ value: e.employeeId, label: `${e.name} (${e.role})` }))} placeholder="Select officer..." />
    </Field>
    <Field label="Procurement Quantity (kg)">
      <Input value={qty} onChange={setQty} placeholder="e.g. 950" type="number" />
    </Field>
    <DialogFooter>
      <Button variant="outline" onClick={onDone}>Cancel</Button>
      <Button onClick={submit} disabled={loading}>{loading && <Loader2 className="animate-spin" />}{loading ? "Creating..." : "Complete Procurement"}</Button>
    </DialogFooter>
  </>;
}

// ─── Payment Dialog ─────────────────────────────────────────────────────────────

function PaymentForm({ onDone }: { onDone: () => void }) {
  const { state, dispatch } = useDemo();
  const [employees, setEmployees] = useState<api.Employee[]>([]);
  const [employeeId, setEmployeeId] = useState(state.tx.employeeId ?? "");
  const [method, setMethod] = useState("BANK_TRANSFER");
  const [reference, setReference] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payment, setPayment] = useState<api.Payment | null>(null);
  const [step, setStep] = useState<"create" | "process" | "done">("create");

  useEffect(() => { api.listEmployees().then(setEmployees).catch(() => {}); }, []);

  const createPay = async () => {
    setError(null);
    if (!state.tx.procurementId) { setError("No procurement. Complete procurement first."); return; }
    if (!employeeId) { setError("Select an employee."); return; }
    setLoading(true);
    try {
      const res = await api.createPayment(state.tx.procurementId, { employeeId });
      dispatch({ type: "SET_TX", data: { paymentId: res.paymentId, payableAmount: res.payableAmount, paymentStatus: res.paymentStatus } });
      setPayment(res);
      setStep("process");
    } catch (e) {
      setError(e instanceof api.ApiError ? e.detail : (e as Error).message);
    } finally { setLoading(false); }
  };

  const processPay = async () => {
    setError(null);
    if (!payment) return;
    setLoading(true);
    try {
      await api.updatePaymentStatus(payment.paymentId, { employeeId, paymentStatus: "PROCESSING", paymentMethod: method });
      dispatch({ type: "SET_TX", data: { paymentStatus: "PROCESSING" } });
      setStep("done");
    } catch (e) {
      setError(e instanceof api.ApiError ? e.detail : (e as Error).message);
    } finally { setLoading(false); }
  };

  const completePay = async () => {
    setError(null);
    if (!payment) return;
    if (!reference) { setError("Enter a payment reference."); return; }
    setLoading(true);
    try {
      const res = await api.updatePaymentStatus(payment.paymentId, { employeeId, paymentStatus: "PAID", paymentMethod: method, paymentReference: reference });
      dispatch({ type: "SET_TX", data: { paymentStatus: "PAID" } });
      dispatch({ type: "PAY" });
      setPayment(res);
    } catch (e) {
      setError(e instanceof api.ApiError ? e.detail : (e as Error).message);
    } finally { setLoading(false); }
  };

  if (state.tx.paymentStatus === "PAID" && payment) return <>
    <div className="rounded-md bg-success-muted p-3 text-sm text-success"><Check className="mr-1 inline size-4" />Payment completed!</div>
    <div className="grid grid-cols-2 gap-3">
      <ResultRow label="Payment ID" value={payment.paymentId} highlight />
      <ResultRow label="Status" value="PAID" highlight />
      <ResultRow label="Payable Amount" value={`₹${payment.payableAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`} highlight />
      <ResultRow label="Method" value={method} />
    </div>
    <DialogFooter><Button onClick={onDone}><Check />Done</Button></DialogFooter>
  </>;

  return <>
    <ErrorBanner error={error} />
    <ResultRow label="Procurement ID" value={state.tx.procurementId ?? "—"} />
    <ResultRow label="Gross Amount" value={state.tx.grossAmount ? `₹${state.tx.grossAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : "—"} />
    {payment && <>
      <ResultRow label="Payment ID" value={payment.paymentId} highlight />
      <ResultRow label="Payable Amount" value={`₹${payment.payableAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`} highlight />
      <ResultRow label="Current Status" value={state.tx.paymentStatus ?? payment.paymentStatus} />
    </>}
    <Field label="Employee">
      <Select value={employeeId} onChange={setEmployeeId} options={employees.filter(e => e.status === "ACTIVE").map(e => ({ value: e.employeeId, label: `${e.name} (${e.role})` }))} placeholder="Select employee..." />
    </Field>
    <Field label="Payment Method">
      <Select value={method} onChange={setMethod} options={[
        { value: "BANK_TRANSFER", label: "Bank Transfer (DBT)" },
        { value: "UPI", label: "UPI" },
        { value: "CASH", label: "Cash" },
        { value: "OTHER", label: "Other" },
      ]} />
    </Field>
    {step === "done" && <Field label="Payment Reference">
      <Input value={reference} onChange={setReference} placeholder="e.g. BANK-REF-12345" />
    </Field>}
    <DialogFooter>
      <Button variant="outline" onClick={onDone}>Cancel</Button>
      {step === "create" && <Button onClick={createPay} disabled={loading || !state.tx.procurementId}>{loading && <Loader2 className="animate-spin" />}Create Payment</Button>}
      {step === "process" && <Button onClick={processPay} disabled={loading}>{loading && <Loader2 className="animate-spin" />}Mark Processing</Button>}
      {step === "done" && <Button onClick={completePay} disabled={loading}>{loading && <Loader2 className="animate-spin" />}Mark Paid</Button>}
    </DialogFooter>
  </>;
}

// ─── Main Export ─────────────────────────────────────────────────────────────────

const titles: Record<string, [string, string]> = {
  booking: ["Book Procurement", "Submit a real procurement request to the backend"],
  arrival: ["Arrival Validation", "Validate farmer arrival and create a Lot in the backend"],
  qc: ["QC Inspection", "Record quality measurements and evaluate against the Rulebook"],
  weight: ["Weighment Console", "Record gross and tare weight — backend calculates net weight"],
  procure: ["Government Procurement", "Create the procurement transaction at the backend grade-based price"],
  payment: ["Payment Transaction", "Create payment and transition through PENDING → PROCESSING → PAID"],
};

export function OperationDialog({ kind, setKind }: { kind: DialogKind; setKind: (k: DialogKind) => void }) {
  if (!kind) return null;
  const [title, desc] = titles[kind] ?? ["Operation", ""];
  const close = () => setKind(null);
  return (
    <Dialog open onOpenChange={v => !v && close()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{desc}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {kind === "booking" && <BookingForm onDone={close} />}
          {kind === "arrival" && <ArrivalForm onDone={close} />}
          {kind === "qc" && <QCForm onDone={close} />}
          {kind === "weight" && <WeighmentForm onDone={close} />}
          {kind === "procure" && <ProcurementForm onDone={close} />}
          {kind === "payment" && <PaymentForm onDone={close} />}
        </div>
      </DialogContent>
    </Dialog>
  );
}
