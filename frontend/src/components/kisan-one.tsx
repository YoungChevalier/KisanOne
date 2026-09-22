import { useEffect, useState, type ComponentType } from "react";
import {
  Activity, AlertTriangle, ArrowRight, BarChart3, Bell, Check, ChevronLeft, ChevronRight,
  CircleDollarSign, ClipboardCheck, CloudOff, Database, Gauge, IndianRupee, Landmark,
  Leaf, Menu, MessageSquareText, Mic2, Pause, Phone, Play, RotateCcw, Scale, ScanLine,
  ShieldCheck, Signal, Sprout, Truck, UserRound, Users, Warehouse, Weight, Wifi, X, XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { DemoProvider, stages, useDemo, type DemoAction, type Stage } from "@/lib/kisan-state";
import { OperationDialog, type DialogKind } from "@/components/operation-dialogs";
import * as api from "@/lib/api";
import { cn } from "@/lib/utils";

type View = "command" | "farmer" | "ivr" | "trace" | "government";
const nav: { id: View; label: string; short: string; icon: ComponentType<{ className?: string }> }[] = [
  { id: "command", label: "Command Centre", short: "Command", icon: Gauge },
  { id: "farmer", label: "Farmer Experience", short: "Farmer", icon: Sprout },
  { id: "ivr", label: "IVR & SMS", short: "IVR", icon: Phone },
  { id: "trace", label: "Five-ID Trace", short: "Trace", icon: ShieldCheck },
  { id: "government", label: "Government View", short: "Govt", icon: Landmark },
];

const demoSteps: { title: string; text: string; view: View; action?: DemoAction; dialog?: DialogKind }[] = [
  { title: "The operating problem", text: "Sehore has 142 expected farmers. KisanOne begins with live capacity, not static tokens.", view: "command" },
  { title: "One shared operational picture", text: "Every channel reads the same queue, capacity and transaction state.", view: "command" },
  { title: "Farmer requests procurement", text: "Submit a real procurement request to the backend.", view: "farmer", dialog: "booking" },
  { title: "Rules approve capacity", text: "The backend deterministic rules assign a centre and slot.", view: "farmer" },
  { title: "Dynamic Call-to-Come", text: "The assigned arrival window is based on the slot returned by the backend.", view: "farmer" },
  { title: "Accessible IVR channel", text: "Key 2 announces the exact same arrival window without a smartphone.", view: "ivr" },
  { title: "Arrival validation", text: "Validate the farmer at the gate and create a Lot in the backend.", view: "command", dialog: "arrival" },
  { title: "Live pipeline begins", text: "The Lot enters the physical process.", view: "command" },
  { title: "Quality inspection", text: "Enter real QC measurements — the backend Rulebook evaluates the grade.", view: "command", dialog: "qc" },
  { title: "Capacity anomaly", text: "WB-04 slows from 12 to 6 farmers per hour.", view: "command", action: { type: "SLOWDOWN" } },
  { title: "AI advises", text: "The advisory forecasts +22 minutes. It does not control procurement.", view: "command" },
  { title: "Rules decide", text: "The rule engine pauses new Call-to-Come releases at 90% utilization.", view: "command" },
  { title: "Farmer protected from waiting", text: "Ramesh sees the revised time and receives a bilingual capacity alert.", view: "farmer" },
  { title: "Device weight captured", text: "Enter real gross and tare weight — the backend calculates net weight.", view: "command", dialog: "weight" },
  { title: "Procurement transaction", text: "The backend creates the government procurement at the grade-based price.", view: "command", dialog: "procure" },
  { title: "Payment closes the loop", text: "Create a real payment and transition it to PAID in the backend.", view: "command", dialog: "payment" },
  { title: "Five-ID accountability", text: "Inspect the real backend-generated IDs from farmer through payment.", view: "trace" },
  { title: "Government visibility", text: "District officers compare centres and act on bottlenecks, not anecdotes.", view: "government" },
];

export function KisanOneApp() { return <DemoProvider><KisanShell /></DemoProvider>; }

function KisanShell() {
  const { state, dispatch } = useDemo();
  const [view, setView] = useState<View>("command");
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [controls, setControls] = useState(false);
  const [demoOpen, setDemoOpen] = useState(false);
  const [auto, setAuto] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);

  const goStep = (next: number) => {
    const safe = Math.max(0, Math.min(demoSteps.length - 1, next));
    const step = demoSteps[safe] ?? demoSteps[0];
    if (!step) return;
    dispatch({ type: "DEMO_STEP", step: safe });
    setView(step.view);
    if (step.action) dispatch(step.action);
    if (step.dialog) setDialog(step.dialog);
    else setDialog(null);
  };
  useEffect(() => {
    if (!auto || !demoOpen) return;
    const timer = window.setInterval(() => {
      if (state.demoStep >= demoSteps.length - 1) { setAuto(false); return; }
      goStep(state.demoStep + 1);
    }, 4200);
    return () => window.clearInterval(timer);
  }, [auto, demoOpen, state.demoStep]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 border-b border-header-border bg-header text-header-foreground shadow-sm">
        <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-3 px-4 lg:px-6">
          <Button aria-label="Open navigation" variant="ghost" size="icon" className="text-header-foreground hover:bg-header-muted lg:hidden" onClick={() => setMobileNav(true)}><Menu /></Button>
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid size-9 shrink-0 place-items-center rounded-md bg-brand text-brand-foreground"><Leaf className="size-5" /></div>
            <div className="min-w-0"><div className="flex items-baseline gap-2"><strong className="text-lg">KisanOne</strong><span className="hidden text-[10px] font-semibold uppercase text-header-subtle sm:inline">SIH26032</span></div><p className="truncate text-[11px] text-header-subtle">One Platform. One Process. One Farmer.</p></div>
          </div>
          <div className="ml-auto hidden items-center gap-3 md:flex">
            <StatusPill online={state.online} count={state.queuedActions.length} />
            <span className="h-7 w-px bg-header-border" />
            <div className="text-right">
              <p className="text-xs font-semibold">{state.tx.assignedCentreId ? `Centre: ${state.tx.assignedCentreId}` : "No Centre Assigned"}</p>
              <p className="text-[10px] text-header-subtle">{state.tx.requestId ? `Request: ${state.tx.requestId}` : "Create a procurement request to begin"}</p>
            </div>
          </div>
          <Button className="ml-auto bg-demo text-demo-foreground hover:bg-demo/90 md:ml-2" onClick={() => { setDemoOpen(true); goStep(0); }}><Play className="size-4" /><span className="hidden sm:inline">Start Judge Demo</span><span className="sm:hidden">Demo</span></Button>
          <Button aria-label="Open demo controls" title="Demo controls" variant="outline" size="icon" className="border-header-border bg-header-muted text-header-foreground hover:bg-header-muted/80" onClick={() => setControls(true)}><Activity /></Button>
        </div>
      </header>

      <div className="mx-auto flex max-w-[1600px]">
        <aside className="sticky top-16 hidden h-[calc(100vh-4rem)] w-60 shrink-0 border-r bg-sidebar p-3 lg:block">
          <Navigation view={view} setView={setView} />
          <div className="absolute inset-x-3 bottom-4 rounded-md border bg-sidebar-panel p-3">
            <p className="text-[10px] font-bold uppercase text-muted-foreground">Architecture principle</p>
            <p className="mt-1 text-sm font-bold text-primary">AI advisory; Rules decide</p>
            <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">SIH-83 CodeOps · Smart India Hackathon 2026</p>
          </div>
        </aside>
        <main className="min-w-0 flex-1 p-3 pb-24 sm:p-5 lg:p-6">
          {view === "command" && <CommandCentre setDialog={setDialog} />}
          {view === "farmer" && <FarmerExperience setDialog={setDialog} />}
          {view === "ivr" && <IvrSimulator />}
          {view === "trace" && <Traceability />}
          {view === "government" && <GovernmentDashboard />}
        </main>
      </div>

      <div className="fixed inset-x-0 bottom-0 z-30 flex border-t bg-background p-1 lg:hidden">
        {nav.map((item) => <Button key={item.id} variant="ghost" className={cn("h-14 min-w-0 flex-1 flex-col gap-0.5 px-1 text-[10px]", view === item.id && "bg-accent text-primary")} onClick={() => setView(item.id)}><item.icon className="size-4" />{item.short}</Button>)}
      </div>
      <Sheet open={mobileNav} onOpenChange={setMobileNav}><SheetContent side="left" className="w-72"><SheetHeader><SheetTitle>KisanOne</SheetTitle><SheetDescription>Select an operational view.</SheetDescription></SheetHeader><div className="mt-6"><Navigation view={view} setView={(v) => { setView(v); setMobileNav(false); }} /></div></SheetContent></Sheet>
      <DemoControls open={controls} onOpenChange={setControls} setDialog={setDialog} />
      <JudgeDemo open={demoOpen} setOpen={setDemoOpen} auto={auto} setAuto={setAuto} goStep={goStep} />
      <OperationDialog kind={dialog} setKind={setDialog} />
    </div>
  );
}

function Navigation({ view, setView }: { view: View; setView: (v: View) => void }) {
  return <nav aria-label="Main navigation" className="space-y-1">{nav.map(item => <Button key={item.id} variant="ghost" className={cn("w-full justify-start", view === item.id && "bg-primary text-primary-foreground hover:bg-primary hover:text-primary-foreground")} onClick={() => setView(item.id)}><item.icon />{item.label}</Button>)}</nav>;
}

function StatusPill({ online, count }: { online: boolean; count: number }) {
  return <div className={cn("flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-semibold", online ? "border-success/30 bg-success/15 text-success-soft" : "border-warning/40 bg-warning/15 text-warning-soft")}>
    {online ? <Wifi className="size-3.5" /> : <CloudOff className="size-3.5" />}{online ? "Online · Synced" : `Offline · ${count} queued`}
  </div>;
}

function PageHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) {
  return <div className="mb-5 flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-bold uppercase text-primary">{eyebrow}</p><h1 className="mt-1 text-2xl font-bold sm:text-3xl">{title}</h1><p className="mt-1 text-sm text-muted-foreground">{description}</p></div>{action}</div>;
}

function Panel({ title, subtitle, children, className }: { title: string; subtitle?: string; children: React.ReactNode; className?: string }) {
  return <section className={cn("rounded-md border bg-card shadow-xs", className)}><div className="border-b px-4 py-3"><h2 className="font-bold">{title}</h2>{subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}</div><div className="p-4">{children}</div></section>;
}

function DemoTag() {
  return <span className="ml-1 rounded bg-muted px-1.5 py-0.5 text-[9px] font-bold uppercase text-muted-foreground">Demo</span>;
}

/* ─── Command Centre ───────────────────────────────────────────────────────── */

function CommandCentre({ setDialog }: { setDialog: (d: DialogKind) => void }) {
  const { state, dispatch } = useDemo();
  const tx = state.tx;
  const [metrics, setMetrics] = useState<api.OfficerCommandMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);

  const centreId = tx.assignedCentreId || "MP-SEH-04";

  useEffect(() => {
    let active = true;
    setLoading(true);
    setDataError(null);
    api.getOfficerCommandMetrics(centreId)
      .then((m) => {
        if (active) setMetrics(m);
      })
      .catch((err) => {
        if (active) {
          setMetrics(null);
          setDataError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [centreId, tx.requestId, tx.lotId, tx.procurementId, tx.paymentId, state.stage, state.paymentComplete]);

  const kpis = [
    {
      label: "Farmers Today",
      value: loading && !metrics ? "—" : metrics ? String(metrics.farmersToday) : "—",
      subtext: metrics?.farmersTodayDetail ?? "Arrivals today",
      Icon: Users,
      isReal: !!metrics,
    },
    {
      label: "Processed",
      value: loading && !metrics ? "—" : metrics ? String(metrics.processedToday) : "—",
      subtext: metrics?.processedTodayDetail ?? "Completed today",
      Icon: ClipboardCheck,
      isReal: !!metrics,
    },
    {
      label: "In Queue",
      value: loading && !metrics ? "—" : metrics ? String(metrics.inQueue) : "—",
      subtext: metrics?.inQueueDetail ?? "Awaiting completion",
      Icon: Truck,
      isReal: !!metrics,
    },
    {
      label: "Average Wait",
      value: loading && !metrics ? "—" : metrics ? metrics.averageWait : "—",
      subtext: metrics?.averageWaitDetail ?? "Avg. Arrival → QC",
      Icon: Activity,
      isReal: metrics ? metrics.isAverageWaitReal : false,
    },
    {
      label: "Capacity",
      value: loading && !metrics ? "—" : metrics ? metrics.capacity : "—",
      subtext: metrics?.capacityDetail ?? "Slot capacity",
      Icon: Gauge,
      isReal: metrics ? metrics.isCapacityReal : false,
    },
  ];

  const handleProcessNext = async (item: api.QueueItem) => {
    let lotId = item.lotId ?? null;
    let qcAttemptId: string | null = null;
    let qcGrade: string | null = null;
    let qcDecision: string | null = null;
    let qcPricePerKg: number | null = null;
    let weighmentId: string | null = null;
    let netWeightKg: number | null = null;
    let procurementId: string | null = null;
    let grossAmount: number | null = null;
    let paymentId: string | null = null;
    let paymentStatus: string | null = null;

    if (lotId) {
      try {
        const qcs = await api.listQCAttempts(lotId);
        if (qcs && qcs.length > 0) {
          const latestQc = qcs[qcs.length - 1];
          qcAttemptId = latestQc.qcAttemptId;
          try {
            const evalRes = await api.getQCEvaluation(latestQc.qcAttemptId);
            if (evalRes) {
              qcGrade = evalRes.grade;
              qcDecision = evalRes.decision;
              qcPricePerKg = evalRes.pricePerKg;
            }
          } catch {}
        }
      } catch {}

      try {
        const proc = await api.getProcurementForLot(lotId);
        if (proc && proc.procurementId) {
          procurementId = proc.procurementId;
          weighmentId = proc.weighmentId;
          grossAmount = Number(proc.grossAmount);
          netWeightKg = Number(proc.procurementQuantityKg);
        }
      } catch {}
    }

    let nextStage: Stage = "Gate";
    if (item.arrivalStatus === "ARRIVED") {
      if (procurementId) {
        nextStage = "Payment";
      } else if (weighmentId) {
        nextStage = "Procurement";
      } else if (qcAttemptId && qcGrade !== "F") {
        nextStage = "Weighment";
      } else {
        nextStage = "QC";
      }
    }

    dispatch({
      type: "SET_TX",
      data: {
        farmerId: item.farmerId,
        farmerName: item.farmerId,
        cropCode: item.cropCode,
        farmerArea: item.farmerArea ?? null,
        expectedQuantityKg: item.expectedQuantityKg,
        requestId: item.requestId,
        assignedCentreId: item.assignedCentreId,
        assignedCentreName: item.assignedCentreId,
        assignedSlotId: item.assignedSlotId,
        lotId,
        qcAttemptId,
        qcGrade,
        qcDecision,
        qcPricePerKg,
        weighmentId,
        netWeightKg,
        procurementId,
        grossAmount,
        paymentId,
        paymentStatus,
      },
    });
    dispatch({ type: "MOVE", stage: nextStage });
  };

  const [employees, setEmployees] = useState<api.Employee[]>([]);
  const [actionFeedback, setActionFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [rejectingReqId, setRejectingReqId] = useState<string | null>(null);
  const [markingArrivalReqId, setMarkingArrivalReqId] = useState<string | null>(null);

  useEffect(() => {
    api.listEmployees().then(setEmployees).catch(() => {});
  }, []);

  const getActiveEmployeeId = async (targetCentreId: string): Promise<string> => {
    let emps = employees;
    if (!emps || emps.length === 0) {
      emps = await api.listEmployees().catch(() => []);
      setEmployees(emps);
    }
    if (tx.employeeId) {
      const matched = emps.find(
        (e) => e.employeeId === tx.employeeId && e.centreId === targetCentreId && e.status === "ACTIVE"
      );
      if (matched) return matched.employeeId;
    }
    const centreEmp = emps.find((e) => e.centreId === targetCentreId && e.status === "ACTIVE");
    return centreEmp?.employeeId || "EMP-01";
  };

  const handleDirectReject = async (requestId: string, centreForReq?: string) => {
    if (
      !window.confirm(
        `Are you sure you want to REJECT procurement request ${requestId}? This will permanently mark the request and lot as REJECTED and remove it from the active queue.`
      )
    ) {
      return;
    }
    try {
      setRejectingReqId(requestId);
      setActionFeedback(null);
      const targetCentre = centreForReq || tx.assignedCentreId || centreId;
      const empId = await getActiveEmployeeId(targetCentre);
      await api.rejectProcurementRequest(requestId, {
        employeeId: empId,
        rejectionReason: "Explicit rejection by officer following Grade F",
      });
      if (tx.requestId === requestId) {
        dispatch({ type: "REJECT" });
      }
      setActionFeedback({
        type: "success",
        message: `Request ${requestId} successfully rejected and removed from active queue.`,
      });
      const updated = await api.getOfficerCommandMetrics(centreId);
      setMetrics(updated);
    } catch (e) {
      console.error("Failed to reject request:", e);
      const errMsg = e instanceof api.ApiError ? e.detail : (e as Error).message || "Failed to reject request";
      setActionFeedback({
        type: "error",
        message: `Rejection failed: ${errMsg}`,
      });
    } finally {
      setRejectingReqId(null);
    }
  };

  const handleMarkArrival = async (item: api.QueueItem) => {
    try {
      setMarkingArrivalReqId(item.requestId);
      setActionFeedback(null);
      const targetCentre = item.assignedCentreId || centreId;
      const empId = await getActiveEmployeeId(targetCentre);
      const res = await api.markArrival(item.requestId, {
        farmerId: item.farmerId,
        employeeId: empId,
      });
      if (tx.requestId === item.requestId) {
        dispatch({ type: "SET_TX", data: { lotId: res.lotId, employeeId: empId } });
        dispatch({ type: "ARRIVE" });
      }
      setActionFeedback({
        type: "success",
        message: `Arrival marked for Farmer ${item.farmerId} (Request ${item.requestId}). Lot ${res.lotId} created.`,
      });
      const updated = await api.getOfficerCommandMetrics(centreId);
      setMetrics(updated);
    } catch (e) {
      console.error("Failed to mark arrival:", e);
      const errMsg = e instanceof api.ApiError ? e.detail : (e as Error).message || "Failed to record arrival";
      setActionFeedback({
        type: "error",
        message: `Arrival failed: ${errMsg}`,
      });
    } finally {
      setMarkingArrivalReqId(null);
    }
  };

  const handleOpenQcForItem = (item: api.QueueItem) => {
    dispatch({
      type: "SET_TX",
      data: {
        farmerId: item.farmerId,
        farmerName: item.farmerId,
        cropCode: item.cropCode,
        farmerArea: item.farmerArea ?? null,
        expectedQuantityKg: item.expectedQuantityKg,
        requestId: item.requestId,
        assignedCentreId: item.assignedCentreId,
        assignedCentreName: item.assignedCentreId,
        assignedSlotId: item.assignedSlotId,
        lotId: item.lotId ?? null,
        qcAttemptId: item.qcAttemptId ?? null,
        qcGrade: item.qcGrade ?? null,
        qcDecision: item.qcDecision ?? null,
      },
    });
    setDialog("qc");
  };

  const hasArrivedCandidates = metrics?.queueItems?.some((q) => q.isProcessNextCandidate);

  return <>
    <PageHeading eyebrow="Officer Command Centre" title={tx.assignedCentreId ?? "MP-SEH-04"} description={tx.requestId ? `Active Request: ${tx.requestId} · Lot: ${tx.lotId ?? "pending"}` : "Select an arrived request from the queue to begin"} action={<div className="flex items-center gap-2"><span className={cn("rounded-full px-3 py-1.5 text-xs font-bold", state.bottleneck ? "bg-warning-muted text-warning-foreground" : "bg-success-muted text-success")}>{state.bottleneck ? "Overloaded" : "Operational"}</span><StatusPill online={state.online} count={state.queuedActions.length} /></div>} />
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
      {kpis.map(({ label, value, subtext, Icon, isReal }) => (
        <div key={label} className="rounded-md border bg-card p-4 shadow-xs">
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium text-muted-foreground flex items-center gap-1">
              {label}
              {!isReal && <DemoTag />}
            </p>
            <Icon className="size-4 text-primary" />
          </div>
          <p className={cn("mt-2 text-lg font-bold", isReal ? "text-foreground" : "text-muted-foreground italic")}>
            {value}
          </p>
          <p className={cn("mt-1 text-[10px] truncate", isReal ? "text-muted-foreground" : "text-muted-foreground italic")} title={subtext}>
            {subtext}
          </p>
        </div>
      ))}
    </div>
    {dataError && (
      <div className="mt-3 flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
        <AlertTriangle className="size-4 shrink-0" />
        <span className="font-medium">Failed to load live data: {dataError}</span>
      </div>
    )}
    {actionFeedback && (
      <div
        className={cn(
          "mt-3 flex items-center justify-between rounded-md p-3 text-xs",
          actionFeedback.type === "success"
            ? "border border-success/30 bg-success-muted text-success"
            : "border border-destructive/30 bg-destructive/10 text-destructive"
        )}
      >
        <div className="flex items-center gap-2">
          {actionFeedback.type === "success" ? <Check className="size-4" /> : <AlertTriangle className="size-4" />}
          <span className="font-medium">{actionFeedback.message}</span>
        </div>
        <button
          type="button"
          onClick={() => setActionFeedback(null)}
          className="ml-2 cursor-pointer text-xs font-semibold hover:underline"
        >
          Dismiss
        </button>
      </div>
    )}
    <div className="mt-4 grid gap-4 xl:grid-cols-[1.35fr_.65fr]">
      <Panel title="Live Operational Pipeline" subtitle="Real backend operations — click buttons to perform each step">
        <div className="grid grid-cols-3 gap-2 md:grid-cols-6">{stages.map((stage, i) => { const active = stage === state.stage; const done = i < stages.indexOf(state.stage) || (stage === "Payment" && state.paymentComplete); return <Button key={stage} variant="outline" className={cn("h-auto min-h-20 flex-col gap-1 px-2 py-3", active && "border-primary bg-accent ring-2 ring-primary/20", done && "border-success/40 bg-success-muted")} onClick={() => dispatch({ type: "MOVE", stage })}><span className={cn("grid size-6 place-items-center rounded-full text-[11px]", done ? "bg-success text-success-foreground" : active ? "bg-primary text-primary-foreground" : "bg-muted")}>{done ? <Check className="size-3" /> : i + 1}</span><span className="text-xs">{stage}</span></Button>})}</div>
        {tx.requestId && <div className="mt-4 flex flex-wrap items-center gap-2 rounded-md border border-primary/20 bg-accent p-3">
          <strong className="text-sm">{tx.farmerName ?? tx.farmerId ?? "—"}</strong><ArrowRight className="size-4 text-muted-foreground"/><span className="text-sm">{state.stage}</span>
          {tx.qcGrade && <span className={cn("rounded-full px-2 py-0.5 text-xs font-bold", tx.qcGrade === "F" ? "bg-destructive/10 text-destructive" : "bg-success-muted text-success")}>Grade {tx.qcGrade}</span>}
          {tx.netWeightKg != null && <span className="text-xs text-muted-foreground">{tx.netWeightKg} kg</span>}
          {tx.grossAmount != null && <span className="ml-auto text-sm font-bold">₹{tx.grossAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</span>}
        </div>}
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => setDialog("arrival")} disabled={!tx.requestId}><ScanLine />Validate Arrival</Button>
          <Button size="sm" variant="outline" onClick={() => setDialog("qc")} disabled={!tx.lotId}><ClipboardCheck />QC Inspection</Button>
          <Button size="sm" variant="outline" onClick={() => setDialog("weight")} disabled={!tx.lotId || tx.qcGrade === "F"}><Scale />Weighment</Button>
          <Button size="sm" variant="outline" onClick={() => setDialog("procure")} disabled={!tx.weighmentId || !tx.qcAttemptId || tx.qcGrade === "F"}><Warehouse />Procure</Button>
          <Button size="sm" variant="outline" onClick={() => setDialog("payment")} disabled={!tx.procurementId}><IndianRupee />Payment</Button>
          {tx.requestId && (
            <Button
              size="sm"
              variant="destructive"
              onClick={() => handleDirectReject(tx.requestId!, tx.assignedCentreId ?? centreId)}
              disabled={!tx.requestId || tx.paymentStatus === "PAID" || !!rejectingReqId}
            >
              <XCircle className="mr-1 size-3.5" />
              {rejectingReqId === tx.requestId ? "Rejecting..." : "Reject Request"}
            </Button>
          )}
        </div>
      </Panel>
      <Panel title="Transaction Summary" subtitle="Real backend data from current flow">
        <div className="space-y-2 text-sm">
          <TxRow label="Request" value={tx.requestId} />
          <TxRow label="Centre" value={tx.assignedCentreId} />
          <TxRow label="Slot" value={tx.assignedSlotId} />
          <TxRow label="Lot" value={tx.lotId} />
          <TxRow label="QC" value={tx.qcAttemptId ? `${tx.qcAttemptId} · ${tx.qcGrade} · ${tx.qcDecision}` : null} />
          <TxRow label="Price" value={tx.qcPricePerKg != null ? `₹${tx.qcPricePerKg}/kg` : null} />
          <TxRow label="Weighment" value={tx.weighmentId ? `${tx.weighmentId} · ${tx.netWeightKg} kg net` : null} />
          <TxRow label="Procurement" value={tx.procurementId ? `${tx.procurementId} · ₹${tx.grossAmount?.toLocaleString("en-IN", { minimumFractionDigits: 2 })}` : null} />
          <TxRow label="Payment" value={tx.paymentId ? `${tx.paymentId} · ${tx.paymentStatus}` : null} />
        </div>
      </Panel>
    </div>
    <div className="mt-4">
      <Panel
        title="Live Centre Queue · सक्रिय कतार"
        subtitle={`Real operational queue for ${centreId} · ${metrics?.inQueue ?? 0} active request(s) · Earliest arrived farmer is processed next`}
      >
        {loading && !metrics && (
          <p className="py-3 text-sm text-muted-foreground italic">Loading active queue from backend...</p>
        )}
        {!loading && (!metrics || metrics.queueItems.length === 0) && (
          <p className="py-3 text-sm text-muted-foreground italic">No active requests in queue for this centre.</p>
        )}
        {!loading && metrics && metrics.queueItems.length > 0 && (
          <div className="space-y-3">
            {!hasArrivedCandidates && (
              <div className="flex items-center gap-2 rounded-md border border-warning/40 bg-warning-muted p-2.5 text-xs text-warning-foreground">
                <AlertTriangle className="size-4 shrink-0" />
                <span>No arrived farmers ready for processing. Unarrived farmers remain in queue until arrival is marked.</span>
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="pb-2 font-medium">Queue</th>
                    <th className="pb-2 font-medium">Farmer</th>
                    <th className="pb-2 font-medium">Request ID</th>
                    <th className="pb-2 font-medium">Crop</th>
                    <th className="pb-2 font-medium">Expected Qty</th>
                    <th className="pb-2 font-medium">Slot</th>
                    <th className="pb-2 font-medium">Arrival Status</th>
                    <th className="pb-2 font-medium">Processing Status</th>
                    <th className="pb-2 font-medium text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {metrics.queueItems.map((item) => {
                    const isNext = item.isProcessNextCandidate;
                    const isCurrentTx = tx.requestId === item.requestId;
                    const isArrived = item.arrivalStatus === "ARRIVED";

                    return (
                      <tr
                        key={item.requestId}
                        className={cn(
                          "transition-colors",
                          isCurrentTx
                            ? "bg-primary/10 font-medium"
                            : isNext
                            ? "bg-accent/40"
                            : "hover:bg-muted/30"
                        )}
                      >
                        <td className="py-2.5 pr-2">
                          <span
                            className={cn(
                              "inline-flex items-center justify-center rounded-full px-2 py-0.5 font-mono font-bold text-[11px]",
                              isNext
                                ? "bg-primary text-primary-foreground"
                                : "bg-muted text-muted-foreground"
                            )}
                          >
                            #{item.queueNumber}
                          </span>
                        </td>
                        <td className="py-2.5 pr-2 font-medium text-foreground">
                          {item.farmerId}
                        </td>
                        <td className="py-2.5 pr-2 font-mono text-[11px] text-muted-foreground">
                          {item.requestId}
                        </td>
                        <td className="py-2.5 pr-2 font-semibold">
                          {item.cropCode}
                        </td>
                        <td className="py-2.5 pr-2">
                          {item.expectedQuantityKg.toLocaleString()} kg
                        </td>
                        <td className="py-2.5 pr-2 font-mono text-[11px] text-muted-foreground">
                          {item.assignedSlotId}
                        </td>
                        <td className="py-2.5 pr-2">
                          <span
                            className={cn(
                              "inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold",
                              isArrived
                                ? "bg-success-muted text-success"
                                : "bg-muted text-muted-foreground"
                            )}
                          >
                            {isArrived ? "Arrived" : "Not Arrived"}
                          </span>
                        </td>
                        <td className="py-2.5 pr-2">
                          <span className="text-[11px] text-muted-foreground">
                            {item.currentProcessingStatus}
                          </span>
                        </td>
                        <td className="py-2.5 text-right">
                          {isNext ? (
                            <Button
                              size="sm"
                              className="h-7 px-2.5 text-xs font-bold"
                              onClick={() => handleProcessNext(item)}
                            >
                              <Play className="mr-1 size-3" />
                              Process Next
                            </Button>
                          ) : item.qcGrade === "F" ? (
                            <div className="flex items-center justify-end gap-1.5">
                              <Button
                                size="sm"
                                variant="outline"
                                className="h-7 px-2 text-[11px]"
                                onClick={() => handleOpenQcForItem(item)}
                              >
                                <RotateCcw className="mr-1 size-3" />
                                Retest
                              </Button>
                              <Button
                                size="sm"
                                variant="destructive"
                                className="h-7 px-2 text-[11px]"
                                disabled={rejectingReqId === item.requestId}
                                onClick={() => handleDirectReject(item.requestId, item.assignedCentreId)}
                              >
                                <XCircle className="mr-1 size-3" />
                                {rejectingReqId === item.requestId ? "Rejecting..." : "Reject"}
                              </Button>
                            </div>
                          ) : isArrived ? (
                            <span className="text-[11px] text-muted-foreground italic">Arrived (Waiting)</span>
                          ) : (
                            <Button
                              size="sm"
                              variant="outline"
                              className="h-7 px-2.5 text-xs font-semibold"
                              disabled={markingArrivalReqId === item.requestId}
                              onClick={() => handleMarkArrival(item)}
                            >
                              <ScanLine className="mr-1 size-3" />
                              {markingArrivalReqId === item.requestId ? "Marking..." : "Mark Arrived"}
                            </Button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </Panel>
    </div>
    <div className="mt-4 grid gap-4 xl:grid-cols-[1.1fr_.9fr]">
      <CapacityPanel />
      <div className="space-y-4"><DecisionPanel /><Events /></div>
    </div>
  </>;
}

function TxRow({ label, value }: { label: string; value: string | null | undefined }) {
  return <div className="flex justify-between border-b pb-1 last:border-0"><span className="text-muted-foreground">{label}</span><span className={cn("font-mono text-xs", value ? "text-foreground" : "text-muted-foreground italic")}>{value ?? "—"}</span></div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="rounded-md bg-muted p-3"><p className="text-[11px] text-muted-foreground">{label}</p><p className="mt-1 font-bold">{value}</p></div>; }

function CapacityPanel() {
  const { state } = useDemo(); const rows = [["Gate",78,"14/hr"],["QC",71,"11/hr"],["Weighment",state.bottleneck?94:76,state.bottleneck?"6/hr":"12/hr"],["Unloading",62,"9/hr"],["Storage",48,"240 MT"]] as const;
  return <Panel title="Capacity Intelligence Engine" subtitle="Demo / Placeholder — backend aggregate unavailable"><div className="space-y-4">{rows.map(([name,value,rate]) => <div key={name}><div className="mb-1.5 flex items-center justify-between text-xs"><span className="font-semibold">{name}<DemoTag /></span><span className={cn("font-bold", value >= 90 && "text-warning-foreground")}>{value}% · {rate}</span></div><div className="h-2 overflow-hidden rounded-full bg-muted"><div className={cn("h-full rounded-full transition-all duration-700", value >= 90 ? "bg-warning" : value >= 75 ? "bg-primary" : "bg-success")} style={{ width: `${value}%` }}/></div>{value >= 90 && <p className="mt-1 flex items-center gap-1 text-[11px] font-bold text-warning-foreground"><AlertTriangle className="size-3"/>Warning · limiting resource</p>}</div>)}</div></Panel>;
}

function DecisionPanel() {
  const { state } = useDemo();
  return <Panel title="Decision Intelligence" subtitle="Demo / Placeholder — backend aggregate unavailable"><div className="grid gap-3 sm:grid-cols-2"><div className={cn("rounded-md border-l-4 p-3", state.bottleneck ? "border-warning bg-warning-muted" : "border-info bg-info-muted")}><p className="text-[10px] font-bold uppercase">AI Advisory<DemoTag /></p><p className="mt-1 text-sm font-bold">{state.bottleneck ? "Weighbridge risk detected" : "No critical risk detected"}</p><p className="mt-1 text-xs text-muted-foreground">{state.bottleneck ? "+22 min projected impact" : "Load remains within plan"}</p></div><div className={cn("rounded-md border-l-4 p-3", state.bottleneck ? "border-warning bg-warning-muted" : "border-success bg-success-muted")}><p className="text-[10px] font-bold uppercase">Rule Engine Decision<DemoTag /></p><p className="mt-1 text-sm font-bold">{state.bottleneck ? "PAUSE CALL-TO-COME" : "CONTINUE RELEASES"}</p><p className="mt-1 text-xs text-muted-foreground">Rule CAP-WB-90 · auditable</p></div></div></Panel>;
}

function Events() { const { state } = useDemo(); return <Panel title="Recent Events">{state.events.length === 0 ? <p className="text-sm text-muted-foreground italic">No events yet. Start a procurement flow.</p> : <div className="space-y-2">{state.events.slice(0,5).map((event, i) => <div key={`${event.time}-${i}`} className="flex gap-3 text-xs"><span className="font-mono text-muted-foreground">{event.time}</span><span className={cn("size-2 shrink-0 rounded-full mt-1", event.tone === "success" ? "bg-success" : event.tone === "warning" ? "bg-warning" : "bg-info")}/><span>{event.text}</span></div>)}</div>}</Panel>; }

/* ─── Farmer Experience ────────────────────────────────────────────────────── */

function FarmerExperience({ setDialog }: { setDialog: (d: DialogKind) => void }) {
  const { state } = useDemo();
  const tx = state.tx;
  const [history, setHistory] = useState<api.PaymentHistoryItem[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [dataError, setDataError] = useState<string | null>(null);

  const farmerId = tx.farmerId || "FMR-104";

  useEffect(() => {
    setLoadingHistory(true);
    setDataError(null);
    api.getFarmerPaymentHistory(farmerId)
      .then(setHistory)
      .catch((err) => {
        setHistory([]);
        setDataError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => setLoadingHistory(false));
  }, [farmerId, state.paymentComplete, tx.paymentId, tx.procurementId]);

  return <div className="mx-auto max-w-5xl">
    <PageHeading eyebrow="Farmer Experience · किसान सेवा" title={tx.farmerName ? `Namaste, ${tx.farmerName}` : "Welcome to KisanOne"} description={tx.requestId ? `${tx.farmerId} · ${tx.cropCode ?? "—"} · ${tx.assignedCentreId ?? "—"}` : "Create a procurement request to begin"} action={<Button onClick={() => setDialog("booking")}><Sprout/>Book Procurement</Button>} />
    {state.bottleneck && <div className="mb-4 flex gap-3 rounded-md border border-warning/40 bg-warning-muted p-4 text-sm"><AlertTriangle className="size-5 shrink-0 text-warning-foreground"/><div><p className="font-bold">Capacity slowdown · क्षमता में देरी</p><p className="mt-1 text-muted-foreground">Your centre arrival has been delayed. Please do not leave early. / कृपया देरी से आएं।</p></div></div>}
    {tx.requestId ? (
      <section className="overflow-hidden rounded-md border bg-card shadow-sm">
        <div className="bg-primary px-5 py-4 text-primary-foreground">
          <div className="flex items-center justify-between"><div><p className="text-xs font-semibold opacity-80">PROCUREMENT REQUEST · {tx.requestId}</p><h2 className="mt-1 text-xl font-bold">Your centre is ready for you</h2></div><Bell className="size-6"/></div>
        </div>
        <div className="p-5">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric label="Farmer / किसान" value={tx.farmerName ?? tx.farmerId ?? "—"} />
            <Metric label="Centre / केंद्र" value={tx.assignedCentreId ?? "—"} />
            <Metric label="Crop / फसल" value={tx.cropCode ?? "—"} />
            <Metric label="Quantity / मात्रा" value={tx.expectedQuantityKg ? `${tx.expectedQuantityKg} kg` : "—"} />
          </div>
          {tx.assignedSlotId && <div className="mt-4 rounded-md bg-success-muted p-3 text-sm text-success"><strong>Slot Assigned:</strong> {tx.assignedSlotId} · Centre: {tx.assignedCentreId}</div>}
        </div>
      </section>
    ) : (
      <section className="overflow-hidden rounded-md border bg-card shadow-sm p-8 text-center">
        <Sprout className="mx-auto size-12 text-muted-foreground" />
        <h2 className="mt-4 text-xl font-bold">No active request</h2>
        <p className="mt-2 text-sm text-muted-foreground">Click "Book Procurement" to create a real procurement request.</p>
      </section>
    )}
    <div className="mt-4 grid gap-4 md:grid-cols-2">
      <Panel title="Live Pipeline Tracking" subtitle="Updates from real backend operations">
        <div className="space-y-3">{stages.map((s,i)=><div key={s} className="flex items-center gap-3"><span className={cn("grid size-7 place-items-center rounded-full text-xs",i<stages.indexOf(state.stage)||(s==="Payment"&&state.paymentComplete)?"bg-success text-success-foreground":s===state.stage?"bg-primary text-primary-foreground":"bg-muted text-muted-foreground")}>{i<stages.indexOf(state.stage)?<Check className="size-3"/>:i+1}</span><span className={cn("text-sm",s===state.stage&&"font-bold")}>{s}</span>{s===state.stage&&<span className="ml-auto text-xs text-primary">Current stage</span>}</div>)}</div>
      </Panel>
      <Panel title="Payment & Transaction History" subtitle="Full payment records from backend">
        {dataError && (
          <div className="mb-3 flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">
            <AlertTriangle className="size-4 shrink-0" />
            <span className="font-medium">Failed to load history: {dataError}</span>
          </div>
        )}
        {loadingHistory && <p className="text-sm text-muted-foreground italic">Loading payment history...</p>}
        {!loadingHistory && !dataError && history.length === 0 && (
          <p className="text-sm text-muted-foreground italic">No payment records found for this farmer.</p>
        )}
        {!loadingHistory && history.length > 0 && (
          <div className="space-y-3">
            {history.map(item => (
              <div key={item.paymentId} className="rounded-md border p-3.5">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="font-bold text-sm">{item.paymentId}</p>
                    <p className="text-xs text-muted-foreground">
                      Procurement: {item.procurementId} · Lot: {item.lotId} · Crop: {item.cropCode}
                    </p>
                  </div>
                  <span className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-bold",
                    item.paymentStatus === "PAID" ? "bg-success-muted text-success" :
                    item.paymentStatus === "PROCESSING" ? "bg-info-muted text-info" : "bg-muted"
                  )}>
                    {item.paymentStatus}
                  </span>
                </div>
                <div className="mt-2.5 flex items-center justify-between border-t pt-2 text-sm">
                  <span className="text-xs text-muted-foreground">
                    Quantity: <strong className="text-foreground">{item.quantityKg} kg</strong>
                    {item.paymentMethod && <span className="ml-1.5">({item.paymentMethod})</span>}
                  </span>
                  <strong className="font-mono text-sm">₹{item.payableAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}</strong>
                </div>
                {item.paymentReference && (
                  <p className="mt-1 text-[11px] font-mono text-muted-foreground">
                    Ref: {item.paymentReference}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  </div>;
}

/* ─── IVR Simulator — FROZEN · DO NOT MODIFY ──────────────────────────────── */

function IvrSimulator() {
  const { state, arrivalWindow, eta, queuePosition } = useDemo(); const [digits,setDigits]=useState(""); const [transcript,setTranscript]=useState("Welcome to KisanOne. किसानवन में आपका स्वागत है। Press 1 for request status, 2 for arrival time, 3 for queue position."); const [speaking,setSpeaking]=useState(false);
  const response = (key:string) => key==="1" ? `Request K1-104 is ${state.paymentComplete?"complete":`at ${state.stage}`}.` : key==="2" ? `Your Call-to-Come window is ${arrivalWindow}. ${state.bottleneck?"The time changed due to centre capacity slowdown.":"Please arrive only in this window."}` : key==="3" ? `Your queue position is ${queuePosition}. Estimated wait is ${eta} minutes.` : `You pressed ${key}. Press 1, 2 or 3 for KisanOne services.`;
  const press=(key:string)=>{setDigits(d=>`${d}${key}`.slice(-12));const text=response(key);setTranscript(text);if(["1","2","3"].includes(key)) speak(text);};
  const speak=(text=transcript)=>{if(typeof window==="undefined"||!("speechSynthesis" in window))return;window.speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.rate=.9;u.onstart=()=>setSpeaking(true);u.onend=()=>setSpeaking(false);window.speechSynthesis.speak(u)};
  const stop=()=>{if(typeof window!=="undefined"&&"speechSynthesis" in window)window.speechSynthesis.cancel();setSpeaking(false)};
  return <><PageHeading eyebrow="Inclusive access" title="IVR & SMS Simulator" description="The same live data for feature phones, voice and text channels"/><div className="grid gap-4 lg:grid-cols-[.8fr_1.2fr]"><Panel title="KisanOne IVR · 1800-11-26032" subtitle="Accessible DTMF telephone simulation"><div className="mx-auto max-w-xs"><div className="rounded-md bg-header p-4 text-header-foreground"><p className="text-xs text-header-subtle">LIVE TRANSCRIPT</p><p aria-live="polite" className="mt-2 min-h-24 text-sm leading-relaxed">{transcript}</p><p className="mt-3 text-right font-mono text-lg">{digits||"—"}</p></div><div className="mt-3 grid grid-cols-3 gap-2">{["1","2","3","4","5","6","7","8","9","*","0","#"].map(k=><Button key={k} variant="outline" className="h-14 text-lg" aria-label={`Press ${k}`} onClick={()=>press(k)}>{k}{["1","2","3"].includes(k)&&<span className="text-[9px] text-muted-foreground">{k==="1"?"Status":k==="2"?"Window":"Queue"}</span>}</Button>)}</div><div className="mt-3 flex gap-2"><Button className="flex-1" onClick={()=>speak()} disabled={speaking}><Play/>{speaking?"Playing":"Play voice"}</Button><Button variant="outline" onClick={stop}><X/>Stop</Button></div></div></Panel><Panel title="SMS Alert Stream" subtitle={`${state.sms.length} messages sent to Ramesh Kumar · ••••••4210`}><div className="space-y-3">{[...state.sms].reverse().map((sms,i)=><div key={`${sms}-${i}`} className="flex gap-3 rounded-md border bg-muted/40 p-3"><MessageSquareText className="size-5 shrink-0 text-primary"/><div><p className="text-sm">{sms}</p><p className="mt-1 text-[10px] text-muted-foreground">Delivered · {i===0?"just now":"10:39 AM"}</p></div></div>)}</div></Panel></div></>;
}

/* ─── Traceability ─────────────────────────────────────────────────────────── */

function Traceability() {
  const { state } = useDemo();
  const tx = state.tx;
  const [selected,setSelected]=useState(0);
  const nodes: [string,string,string,string][] = [
    ["Farmer", tx.farmerId ?? "—", tx.farmerName ?? "—", tx.farmerId ? "VERIFIED" : "PENDING"],
    ["Request", tx.requestId ?? "—", tx.assignedCentreId ?? "—", tx.requestId ? "APPROVED" : "PENDING"],
    ["Lot", tx.lotId ?? "—", tx.cropCode ?? "—", tx.lotId ? "CREATED" : "PENDING"],
    ["Procurement", tx.procurementId ?? "—", tx.qcGrade ? `Grade ${tx.qcGrade}` : "—", tx.procurementId ? "POSTED" : "PENDING"],
    ["Payment", tx.paymentId ?? "—", tx.paymentStatus ?? "—", tx.paymentStatus === "PAID" ? "SETTLED" : "PENDING"],
  ];
  const n = nodes[selected] ?? nodes[0];
  if (!n) return null;
  return <>
    <PageHeading eyebrow="End-to-end accountability" title="Five-ID Traceability" description="Real backend-generated IDs from farmer identity to final payment"/>
    <Panel title="Procurement chain" subtitle="Select any node to inspect — IDs are from the real backend">
      <div className="flex flex-col items-stretch gap-2 lg:flex-row lg:items-center">{nodes.map((node,i)=><div key={node[1]+i} className="contents"><Button variant="outline" className={cn("h-auto min-h-24 flex-1 flex-col",selected===i&&"border-primary bg-accent ring-2 ring-primary/20")} onClick={()=>setSelected(i)}><span className="text-[10px] uppercase text-muted-foreground">{node[0]}</span><strong className="text-xs">{node[1]}</strong><span className={cn("text-[10px]",node[3]==="PENDING"?"text-muted-foreground":"text-success")}>{node[3]}</span></Button>{i<nodes.length-1&&<ArrowRight className="mx-auto size-4 rotate-90 text-muted-foreground lg:rotate-0"/>}</div>)}</div>
    </Panel>
    <div className="mt-4 grid gap-4 md:grid-cols-[1fr_.7fr]">
      <Panel title={`${n[0]} · ${n[1]}`}>
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <Detail label="Entity" value={n[0]}/>
          <Detail label="ID" value={n[1]}/>
          <Detail label="Detail" value={n[2]}/>
          <Detail label="Status" value={n[3]}/>
          {n[0] === "Procurement" && tx.grossAmount != null && <Detail label="Amount" value={`₹${tx.grossAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`}/>}
          {n[0] === "Payment" && tx.payableAmount != null && <Detail label="Payable" value={`₹${tx.payableAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}`}/>}
        </dl>
      </Panel>
      <Panel title="ID Chain">
        <div className="space-y-2 text-xs font-mono">
          <p>farmerId: {tx.farmerId ?? "—"}</p>
          <p>requestId: {tx.requestId ?? "—"}</p>
          <p>lotId: {tx.lotId ?? "—"}</p>
          <p>qcAttemptId: {tx.qcAttemptId ?? "—"}</p>
          <p>weighmentId: {tx.weighmentId ?? "—"}</p>
          <p>procurementId: {tx.procurementId ?? "—"}</p>
          <p>paymentId: {tx.paymentId ?? "—"}</p>
        </div>
        {tx.paymentId && <p className="mt-3 flex items-center gap-2 text-xs text-success"><ShieldCheck className="size-4"/>Complete chain — all IDs from real backend</p>}
      </Panel>
    </div>
  </>;
}

function Detail({label,value}:{label:string;value:string}) { return <div><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 font-semibold">{value}</dd></div>; }

/* ─── Government Dashboard ─────────────────────────────────────────────────── */

function GovernmentDashboard() {
  const [metrics, setMetrics] = useState<api.GovernmentMetrics | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.getGovernmentMetrics()
      .then(setMetrics)
      .catch(() => setMetrics(null))
      .finally(() => setLoading(false));
  }, []);

  return <>
    <PageHeading eyebrow="Government monitoring" title="District Dashboard" description="Real transaction-derived procurement statistics & telemetry"/>
    <div className="rounded-md border border-info/30 bg-info-muted p-3.5 mb-4 text-sm text-info">
      <strong>Data Source:</strong> Procurement and payment metrics below are derived from real transaction records in the backend. System parameters not tracked by the API are explicitly marked as demo placeholders.
    </div>
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <GovKpi
        label="Total Procured"
        value={metrics ? `${metrics.totalQuantityMT} MT` : "—"}
        change={metrics ? `${metrics.totalQuantityKg.toLocaleString()} kg across ${metrics.totalProcurements} transaction(s)` : "Loading..."}
        isReal={!!metrics}
      />
      <GovKpi
        label="Farmers Served"
        value={metrics ? String(metrics.totalFarmersServed) : "—"}
        change={metrics ? `${metrics.totalFarmersServed} unique farmer(s) completed` : "Loading..."}
        isReal={!!metrics}
      />
      <GovKpi
        label="Active Centres"
        value={metrics ? String(metrics.activeCentresCount) : "—"}
        change={metrics ? `${metrics.activeCentresCount} operational procurement centre(s)` : "Loading..."}
        isReal={!!metrics}
      />
      <GovKpi
        label="Avg. Wait Time"
        value="21 min"
        change="Demo / Placeholder — backend aggregate unavailable"
        isReal={false}
      />
    </div>
    <div className="mt-4 grid gap-4 lg:grid-cols-[1.25fr_.75fr]">
      <Panel title="Centre Performance" subtitle="Real procurement transactions per active centre">
        {loading && <p className="text-sm text-muted-foreground italic">Loading centre statistics...</p>}
        {!loading && (!metrics || metrics.centreComparison.length === 0) && (
          <p className="text-sm text-muted-foreground italic">No centre procurement data found.</p>
        )}
        {!loading && metrics && metrics.centreComparison.map(c => (
          <div key={c.centreId} className="flex items-center justify-between border-b py-2.5 last:border-0">
            <div>
              <p className="text-sm font-bold">{c.centreName}</p>
              <p className="text-xs text-muted-foreground">{c.centreId} · {c.procurementsCount} transaction(s)</p>
            </div>
            <strong className="text-sm font-mono">{c.totalQuantityKg.toLocaleString()} kg</strong>
          </div>
        ))}
      </Panel>
      <Panel title="District Alerts" subtitle="Demo / Placeholder — backend aggregate unavailable">
        <p className="text-sm text-muted-foreground italic">Alert aggregation requires telemetry streams not provided by the current API.<DemoTag /></p>
      </Panel>
    </div>
    <div className="mt-4 grid gap-4 md:grid-cols-3">
      <Panel title="Commodity Mix" subtitle="Real breakdown of procured crops">
        {loading && <p className="text-sm text-muted-foreground italic">Loading crop distribution...</p>}
        {!loading && (!metrics || metrics.commodityMix.length === 0) && (
          <p className="text-sm text-muted-foreground italic">No commodity procurement recorded yet.</p>
        )}
        {!loading && metrics && metrics.commodityMix.map(c => (
          <div key={c.cropCode} className="space-y-1.5 py-1">
            <div className="flex justify-between text-xs font-semibold">
              <span>{c.cropCode} ({c.count} tx)</span>
              <span>{c.quantityKg.toLocaleString()} kg · {c.percent}%</span>
            </div>
            <div className="h-2 rounded-full bg-muted overflow-hidden">
              <div className="h-full bg-primary" style={{ width: `${c.percent}%` }} />
            </div>
          </div>
        ))}
      </Panel>
      <Panel title="Payments Settled" subtitle="Real payment transactions from backend">
        {loading && <p className="text-sm text-muted-foreground italic">Loading payment totals...</p>}
        {!loading && metrics && (
          <div>
            <p className="text-2xl font-bold font-mono">
              ₹{metrics.totalPaymentsAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              {metrics.totalPaymentsSettled} payment(s) marked as PAID
            </p>
            <p className="text-xs text-muted-foreground mt-2 border-t pt-2">
              Total procurement value: ₹{metrics.totalGrossAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })}
            </p>
          </div>
        )}
      </Panel>
      <Panel title="Storage Readiness" subtitle="Demo / Placeholder — backend aggregate unavailable">
        <p className="text-sm text-muted-foreground italic">Storage readiness requires warehouse telemetry not provided by the current API.<DemoTag /></p>
      </Panel>
    </div>
  </>;
}

function GovKpi({ label, value, change, isReal }: { label: string; value: string; change: string; isReal?: boolean }) {
  return (
    <div className="rounded-md border bg-card p-4">
      <p className="text-xs text-muted-foreground flex items-center justify-between">
        {label}
        {!isReal && <DemoTag />}
      </p>
      <p className={cn("mt-2 text-xl font-bold sm:text-2xl", isReal ? "text-foreground" : "text-muted-foreground")}>
        {value}
      </p>
      <p className={cn("mt-1 text-[10px]", isReal ? "text-success font-medium" : "text-muted-foreground italic")}>
        {change}
      </p>
    </div>
  );
}

/* ─── Demo Controls & Judge Demo ───────────────────────────────────────────── */

function DemoControls({open,onOpenChange,setDialog}:{open:boolean;onOpenChange:(v:boolean)=>void;setDialog:(d:DialogKind)=>void}) {
  const {state,dispatch}=useDemo(); const actions:{label:string;icon:ComponentType<{className?:string}>;action:DemoAction;dialog?:DialogKind}[]=
    [["Reset Demo",RotateCcw,{type:"RESET"}], ["Book Procurement Request",Sprout,{type:"DEMO_STEP",step:2},"booking"], ["Validate Arrival",ScanLine,{type:"DEMO_STEP",step:6},"arrival"], ["Slow Weighbridge 12→6/hr",AlertTriangle,{type:"SLOWDOWN"}], ["Restore Weighbridge 12/hr",Activity,{type:"RESTORE_CAPACITY"}], ["QC Inspection",ClipboardCheck,{type:"DEMO_STEP",step:8},"qc"], ["Record Weighment",Scale,{type:"DEMO_STEP",step:13},"weight"], ["Government Procurement",Warehouse,{type:"DEMO_STEP",step:14},"procure"], ["Payment",CircleDollarSign,{type:"DEMO_STEP",step:15},"payment"], ["Switch Offline",CloudOff,{type:"OFFLINE"}], ["Restore Connectivity",Wifi,{type:"ONLINE"}],
  ].map(([label,icon,action,dialog])=>({label:label as string,icon:icon as ComponentType<{className?:string}>,action:action as DemoAction,dialog:dialog as DialogKind}));
  return <Sheet open={open} onOpenChange={onOpenChange}><SheetContent className="w-full overflow-y-auto sm:max-w-md"><SheetHeader><SheetTitle>Demo Controller</SheetTitle><SheetDescription>Drive real backend operations through the KisanOne pipeline.</SheetDescription></SheetHeader><div className="mt-5 rounded-md bg-header p-3 text-header-foreground"><StatusPill online={state.online} count={state.queuedActions.length}/>{!state.online&&<p className="mt-2 text-xs text-header-subtle">Actions stay on this device and sync automatically after connectivity returns.</p>}</div><div className="mt-4 space-y-2">{actions.map(({label,icon:Icon,action,dialog})=><Button key={label} variant="outline" className="h-11 w-full justify-start" disabled={(action.type==="OFFLINE"&&!state.online)||(action.type==="ONLINE"&&state.online)} onClick={()=>{dispatch(action);if(dialog)setDialog(dialog)}}><Icon/>{label}</Button>)}</div><div className="mt-5 rounded-md border bg-muted p-3 text-xs"><p className="font-bold">Live transaction state</p><p className="mt-1 text-muted-foreground">Stage: {state.stage} · Request: {state.tx.requestId ?? "none"} · Lot: {state.tx.lotId ?? "none"} · Grade: {state.tx.qcGrade ?? "none"}</p></div></SheetContent></Sheet>;
}

function JudgeDemo({open,setOpen,auto,setAuto,goStep}:{open:boolean;setOpen:(v:boolean)=>void;auto:boolean;setAuto:(v:boolean)=>void;goStep:(n:number)=>void}) {
  const {state,dispatch}=useDemo(); const step=demoSteps[state.demoStep] ?? demoSteps[0];
  if (!step) return null;
  return <div className={cn("fixed inset-x-3 bottom-20 z-50 mx-auto max-w-2xl transition-all lg:bottom-5",open?"translate-y-0 opacity-100":"pointer-events-none translate-y-8 opacity-0")} role="dialog" aria-label="Judge demo walkthrough"><div className="overflow-hidden rounded-md border border-demo/40 bg-header text-header-foreground shadow-2xl"><div className="h-1 bg-header-muted"><div className="h-full bg-demo transition-all" style={{width:`${((state.demoStep+1)/demoSteps.length)*100}%`}}/></div><div className="p-4"><div className="flex items-start gap-3"><div className="grid size-9 shrink-0 place-items-center rounded-md bg-demo font-bold text-demo-foreground">{state.demoStep+1}</div><div className="min-w-0"><p className="text-[10px] font-bold uppercase text-header-subtle">Judge Demo · Step {state.demoStep+1} of {demoSteps.length}</p><h2 className="mt-0.5 font-bold">{step.title}</h2><p className="mt-1 text-sm leading-relaxed text-header-subtle">{step.text}</p></div><Button variant="ghost" size="icon" className="ml-auto text-header-foreground hover:bg-header-muted" onClick={()=>setOpen(false)}><X/></Button></div><div className="mt-4 flex items-center gap-2"><Button size="icon" variant="outline" className="border-header-border bg-header-muted text-header-foreground" disabled={state.demoStep===0} onClick={()=>goStep(state.demoStep-1)}><ChevronLeft/></Button><Button variant="outline" className="border-header-border bg-header-muted text-header-foreground" onClick={()=>setAuto(!auto)}>{auto?<Pause/>:<Play/>}{auto?"Pause":"Auto play"}</Button><Button className="ml-auto bg-demo text-demo-foreground hover:bg-demo/90" onClick={()=>{if(state.demoStep===demoSteps.length-1){dispatch({type:"RESET"});goStep(0)}else goStep(state.demoStep+1)}}>{state.demoStep===demoSteps.length-1?"Restart":"Next"}<ChevronRight/></Button></div></div></div></div>;
}