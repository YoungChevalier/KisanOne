import { createContext, useContext, useMemo, useReducer, type ReactNode } from "react";

export const stages = ["Gate", "QC", "Weighment", "Unloading", "Procurement", "Payment"] as const;
export type Stage = (typeof stages)[number];

/** Real backend entity references from the current transaction. */
export type TransactionData = {
  farmerId: string | null;
  farmerName: string | null;
  cropCode: string | null;
  farmerArea: string | null;
  expectedQuantityKg: number | null;
  requestId: string | null;
  assignedCentreId: string | null;
  assignedCentreName: string | null;
  assignedSlotId: string | null;
  lotId: string | null;
  qcAttemptId: string | null;
  qcGrade: string | null;
  qcDecision: string | null;
  qcPricePerKg: number | null;
  qcEvaluation: Record<string, unknown> | null;
  weighmentId: string | null;
  grossWeightKg: number | null;
  tareWeightKg: number | null;
  netWeightKg: number | null;
  procurementId: string | null;
  grossAmount: number | null;
  paymentId: string | null;
  payableAmount: number | null;
  paymentStatus: string | null;
  employeeId: string | null;
};

const emptyTransaction: TransactionData = {
  farmerId: null, farmerName: null, cropCode: null, farmerArea: null, expectedQuantityKg: null,
  requestId: null, assignedCentreId: null, assignedCentreName: null, assignedSlotId: null,
  lotId: null, qcAttemptId: null, qcGrade: null, qcDecision: null, qcPricePerKg: null,
  qcEvaluation: null, weighmentId: null, grossWeightKg: null, tareWeightKg: null,
  netWeightKg: null, procurementId: null, grossAmount: null, paymentId: null,
  payableAmount: null, paymentStatus: null, employeeId: null,
};

export type DemoState = {
  requestCreated: boolean;
  arrived: boolean;
  bottleneck: boolean;
  online: boolean;
  stage: Stage;
  weightConfirmed: boolean;
  qcPassed: boolean;
  procurementComplete: boolean;
  paymentComplete: boolean;
  queuedActions: string[];
  events: { time: string; text: string; tone: "info" | "success" | "warning" }[];
  sms: string[];
  demoStep: number;
  /** Real backend data for the current transaction */
  tx: TransactionData;
};

export type DemoAction =
  | { type: "RESET" }
  | { type: "REQUEST" }
  | { type: "ARRIVE" }
  | { type: "SLOWDOWN" }
  | { type: "RESTORE_CAPACITY" }
  | { type: "QC" }
  | { type: "WEIGHT" }
  | { type: "PROCURE" }
  | { type: "PAY" }
  | { type: "OFFLINE" }
  | { type: "ONLINE" }
  | { type: "MOVE"; stage: Stage }
  | { type: "DEMO_STEP"; step: number }
  | { type: "SET_TX"; data: Partial<TransactionData> }
  | { type: "REJECT" };

const initialState: DemoState = {
  requestCreated: false,
  arrived: false,
  bottleneck: false,
  online: true,
  stage: "Gate",
  weightConfirmed: false,
  qcPassed: false,
  procurementComplete: false,
  paymentComplete: false,
  queuedActions: [],
  events: [],
  sms: [],
  demoStep: 0,
  tx: { ...emptyTransaction },
};

const now = () => new Date().toLocaleTimeString("en-IN", { hour12: false });

function addEvent(state: DemoState, text: string, tone: "info" | "success" | "warning" = "info") {
  return [{ time: now(), text, tone }, ...state.events].slice(0, 8);
}

function reducer(state: DemoState, action: DemoAction): DemoState {
  const queueOffline = (label: string) => (state.online ? state.queuedActions : [...state.queuedActions, label]);
  switch (action.type) {
    case "RESET": return { ...initialState, events: [] };
    case "REQUEST": return { ...state, requestCreated: true, stage: "Gate", events: addEvent(state, state.tx.requestId ? `Procurement request ${state.tx.requestId} created` : "Procurement request created", "success") };
    case "ARRIVE": return { ...state, arrived: true, stage: "QC", queuedActions: queueOffline("Arrival"), events: addEvent(state, state.tx.lotId ? `Arrival validated — Lot ${state.tx.lotId} created` : "Arrival validated", "success") };
    case "SLOWDOWN": return { ...state, bottleneck: true, events: addEvent(state, "Weighbridge throughput fell — releases paused", "warning") };
    case "RESTORE_CAPACITY": return { ...state, bottleneck: false, events: addEvent(state, "Weighbridge restored — releases resumed", "success") };
    case "QC": return { ...state, qcPassed: state.tx.qcDecision === "PASS" || state.tx.qcGrade !== "F", stage: "Weighment", queuedActions: queueOffline("QC"), events: addEvent(state, state.tx.qcGrade ? `QC: Grade ${state.tx.qcGrade} · ${state.tx.qcDecision} · ₹${state.tx.qcPricePerKg ?? 0}/kg` : "QC completed", state.tx.qcGrade === "F" ? "warning" : "success") };
    case "WEIGHT": return { ...state, weightConfirmed: true, stage: "Unloading", queuedActions: queueOffline(`Weight ${state.tx.netWeightKg ?? "?"} kg`), events: addEvent(state, state.tx.netWeightKg ? `${state.tx.netWeightKg} kg net weight captured` : "Weight captured", "success") };
    case "PROCURE": return { ...state, procurementComplete: true, stage: "Payment", queuedActions: queueOffline(`Procurement ${state.tx.procurementId ?? ""}`), events: addEvent(state, state.tx.procurementId ? `${state.tx.procurementId} created · ₹${state.tx.grossAmount?.toLocaleString("en-IN", { minimumFractionDigits: 2 }) ?? "0.00"}` : "Procurement completed", "success") };
    case "PAY": return { ...state, paymentComplete: true, stage: "Payment", events: addEvent(state, state.tx.paymentId ? `${state.tx.paymentId} · ₹${state.tx.payableAmount?.toLocaleString("en-IN", { minimumFractionDigits: 2 }) ?? "0.00"} · ${state.tx.paymentStatus ?? "PAID"}` : "Payment completed", "success"), sms: [...state.sms, state.tx.payableAmount ? `KisanOne: ₹${state.tx.payableAmount.toLocaleString("en-IN", { minimumFractionDigits: 2 })} payment completed for ${state.tx.procurementId ?? "procurement"}.` : "KisanOne: Payment completed."] };
    case "OFFLINE": return { ...state, online: false, events: addEvent(state, "Connectivity lost · offline-first mode active", "warning") };
    case "ONLINE": return { ...state, online: true, queuedActions: [], events: addEvent(state, `${state.queuedActions.length} local action(s) synced`, "success") };
    case "MOVE": return { ...state, stage: action.stage, events: addEvent(state, `Moved to ${action.stage}`, "info") };
    case "DEMO_STEP": return { ...state, demoStep: action.step };
    case "SET_TX": return { ...state, tx: { ...state.tx, ...action.data } };
    case "REJECT": return { ...state, stage: "Gate", tx: { ...emptyTransaction }, events: addEvent(state, state.tx.requestId ? `Request ${state.tx.requestId} REJECTED and closed` : "Request rejected", "warning") };
  }
}

type ContextValue = {
  state: DemoState;
  dispatch: React.Dispatch<DemoAction>;
  arrivalWindow: string;
  eta: number;
  queuePosition: number;
  gross: number;
};
const DemoContext = createContext<ContextValue | null>(null);

export function DemoProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const value = useMemo(() => ({
    state,
    dispatch,
    arrivalWindow: state.bottleneck ? "11:05 AM – 11:20 AM" : "10:40 AM – 10:55 AM",
    eta: state.paymentComplete ? 0 : state.bottleneck ? 40 : state.stage === "Gate" ? 18 : Math.max(4, 16 - stages.indexOf(state.stage) * 3),
    queuePosition: state.paymentComplete ? 0 : Math.max(1, 4 - stages.indexOf(state.stage)),
    gross: state.tx.grossAmount ?? 1192.1,
  }), [state]);
  return <DemoContext.Provider value={value}>{children}</DemoContext.Provider>;
}

export function useDemo() {
  const value = useContext(DemoContext);
  if (!value) throw new Error("useDemo must be used inside DemoProvider");
  return value;
}