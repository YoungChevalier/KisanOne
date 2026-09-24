/**
 * KisanOne API Client
 * Centralized HTTP client for the KisanOne FastAPI backend.
 * All business logic lives in the backend — this file only transports data.
 */

// In dev the Vite proxy rewrites /api/* → backend; in production use the env var directly.
const BASE =
  typeof window !== "undefined" && import.meta.env.DEV
    ? "/api"
    : (import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000");

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = (data as { detail?: string })?.detail ?? res.statusText;
    throw new ApiError(res.status, detail);
  }
  return data as T;
}

// ─── Farmers ────────────────────────────────────────────────────────────────────

export interface Farmer {
  farmerId: string;
  name: string;
  phone: string;
  address: string;
  district: string;
  area: string;
  preferredLanguage?: string;
  ekycVerified?: boolean;
}

export const createFarmer = (f: Farmer) => request<Farmer>("POST", "/farmers", f);
export const listFarmers = () => request<Farmer[]>("GET", "/farmers");
export const getFarmer = (id: string) => request<Farmer>("GET", `/farmers/${id}`);

// ─── Centres ────────────────────────────────────────────────────────────────────

export interface Centre {
  centreId: string;
  centreName: string;
  state: string;
  district: string;
  area: string;
  address: string;
  supportedCrops: string[];
  operatingDays: string[];
  operatingHours: string;
  dailyProcurementCapacityKg: number;
  dailyQcCapacity: number;
  dailyWeighmentCapacity: number;
  status: string;
}

export const listCentres = () => request<Centre[]>("GET", "/centres");
export const getCentre = (id: string) => request<Centre>("GET", `/centres/${id}`);

// ─── Crop Configurations ────────────────────────────────────────────────────────

export interface QualityTest {
  testCode: string;
  testName: string;
  unit: string;
  dataType: string;
  required: boolean;
  description?: string;
}

export interface CropConfig {
  cropCode: string;
  cropName: string;
  status: string;
  qualityTests: QualityTest[];
}

export const listCropConfigs = () => request<CropConfig[]>("GET", "/crop-configurations");
export const getCropConfig = (code: string) => request<CropConfig>("GET", `/crop-configurations/${code}`);

// ─── Employees ──────────────────────────────────────────────────────────────────

export interface Employee {
  employeeId: string;
  name: string;
  phone: string;
  email: string;
  role: string;
  centreId: string;
  status: string;
}

export const listEmployees = () => request<Employee[]>("GET", "/employees");

// ─── Slots ──────────────────────────────────────────────────────────────────────

export interface SlotAssignResult {
  centreId: string;
  slotId: string;
  centre: Centre;
  slot: {
    slotId: string;
    centreId: string;
    cropCode: string;
    date: string;
    startTime: string;
    endTime: string;
    capacityKg: number;
    allocatedKg: number;
    remainingCapacityKg: number;
    maxFarmers: number;
    allocatedFarmers: number;
    remainingFarmerCapacity: number;
    status: string;
  };
}

export const assignSlot = (p: {
  farmerId: string;
  cropCode: string;
  expectedQuantityKg: number;
  farmerArea?: string;
}) => request<SlotAssignResult>("POST", "/slots/assign", p);

export interface CentreSlot {
  slotId: string;
  centreId: string;
  cropCode: string;
  date: string;
  startTime: string;
  endTime: string;
  capacityKg: number | string;
  maxFarmers: number;
  allocatedKg: number | string;
  allocatedFarmers: number;
  remainingCapacityKg: number | string;
  remainingFarmerCapacity: number;
  status: string;
}

export const listCentreSlots = (centreId: string) =>
  request<CentreSlot[]>("GET", `/centres/${centreId}/slots`);

// ─── Procurement Requests ───────────────────────────────────────────────────────

export interface ProcurementRequest {
  requestId: string;
  farmerId: string;
  cropCode: string;
  farmerArea?: string;
  expectedQuantityKg: number;
  assignedCentreId: string;
  assignedSlotId: string;
  queueNumber?: number;
  bookingStatus?: string;
  arrivalStatus?: string;
  arrivedAt?: string | null;
  requestStatus?: string;
  status?: string;
  lotId?: string;
  createdAt?: string;
  updatedAt?: string;
}

export const createProcurementRequest = (p: {
  requestId: string;
  farmerId: string;
  cropCode: string;
  farmerArea?: string;
  expectedQuantityKg: number;
  autoAssign?: boolean;
  assignedCentreId?: string;
  assignedSlotId?: string;
}) => request<ProcurementRequest>("POST", "/procurement-requests", p);

export const getProcurementRequest = (id: string) =>
  request<ProcurementRequest>("GET", `/procurement-requests/${id}`);

export const listProcurementRequests = () =>
  request<ProcurementRequest[]>("GET", "/procurement-requests");

export const listFarmerProcurementRequests = (farmerId: string) =>
  request<ProcurementRequest[]>("GET", `/farmers/${farmerId}/procurement-requests`);

export const listCentreProcurementRequests = (centreId: string) =>
  request<ProcurementRequest[]>("GET", `/centres/${centreId}/procurement-requests`);

export interface RejectRequestPayload {
  employeeId: string;
  rejectionReason?: string;
}

export const rejectProcurementRequest = (requestId: string, p: RejectRequestPayload) =>
  request<ProcurementRequest>("POST", `/procurement-requests/${requestId}/reject`, p);

// ─── Arrival ────────────────────────────────────────────────────────────────────

export interface ArrivalResult {
  requestId: string;
  lotId: string;
  status: string;
  arrivedAt?: string;
}

export const markArrival = (requestId: string, p: { farmerId: string; employeeId: string }) =>
  request<ArrivalResult>("POST", `/procurement-requests/${requestId}/arrival`, p);

// ─── Lots ───────────────────────────────────────────────────────────────────────

export interface Lot {
  lotId: string;
  requestId: string;
  farmerId: string;
  cropCode: string;
  centreId: string;
  status: string;
}

export const getLot = (id: string) => request<Lot>("GET", `/lots/${id}`);
export const getLotByRequest = (requestId: string) =>
  request<Lot>("GET", `/procurement-requests/${requestId}/lot`);

// ─── Quality Checks ─────────────────────────────────────────────────────────────

export interface QCAttempt {
  qcAttemptId: string;
  lotId: string;
  attemptNumber: number;
  employeeId: string;
  tests: Record<string, number>;
  performedAt: string;
}

export interface QCEvaluation {
  evaluationId: string;
  qcAttemptId: string;
  lotId: string;
  cropCode: string;
  grade: string;
  decision: string;
  pricePerKg: number;
  rulebookId: string;
  rulebookVersion: number;
  testResults: Record<string, unknown>;
}

export const submitQualityCheck = (lotId: string, p: { employeeId: string; tests: Record<string, number> }) =>
  request<QCAttempt>("POST", `/lots/${lotId}/quality-checks`, p);

export const evaluateQC = (qcAttemptId: string) =>
  request<QCEvaluation>("POST", `/quality-checks/${qcAttemptId}/evaluate`);

export const getQCEvaluation = (qcAttemptId: string) =>
  request<QCEvaluation>("GET", `/quality-checks/${qcAttemptId}/evaluation`);

export const listQCAttempts = (lotId: string) =>
  request<QCAttempt[]>("GET", `/lots/${lotId}/quality-checks`);

// ─── Weighments ─────────────────────────────────────────────────────────────────

export interface Weighment {
  weighmentId: string;
  lotId: string;
  employeeId: string;
  grossWeightKg: number;
  tareWeightKg: number;
  netWeightKg: number;
}

export const createWeighment = (lotId: string, p: { employeeId: string; grossWeightKg: number; tareWeightKg: number }) =>
  request<Weighment>("POST", `/lots/${lotId}/weighments`, p);

// ─── Government Procurement ─────────────────────────────────────────────────────

export interface GovProcurement {
  procurementId: string;
  lotId: string;
  farmerId: string;
  cropCode: string;
  centreId: string;
  weighmentId: string;
  qcAttemptId: string;
  qualityGrade: string;
  pricePerKg: number;
  procurementQuantityKg: number;
  grossAmount: number;
}

export const createGovProcurement = (lotId: string, p: {
  weighmentId: string;
  procurementQuantityKg: number;
  qcAttemptId: string;
  employeeId: string;
}) => request<GovProcurement>("POST", `/lots/${lotId}/procurement`, p);

export const getProcurementForLot = (lotId: string) =>
  request<GovProcurement>("GET", `/lots/${lotId}/procurement`);

export const getProcurement = (procurementId: string) =>
  request<GovProcurement>("GET", `/procurements/${procurementId}`);

// ─── Payments ───────────────────────────────────────────────────────────────────

export interface Payment {
  paymentId: string;
  procurementId: string;
  farmerId: string;
  payableAmount: number;
  paymentStatus: string;
  paymentMethod?: string;
  paymentReference?: string;
  createdAt?: string;
}

export const createPayment = (procurementId: string, p: { employeeId: string }) =>
  request<Payment>("POST", `/procurements/${procurementId}/payment`, p);

export const getPaymentForProcurement = (procurementId: string) =>
  request<Payment>("GET", `/procurements/${procurementId}/payment`);

export const getPayment = (paymentId: string) =>
  request<Payment>("GET", `/payments/${paymentId}`);

export const updatePaymentStatus = (paymentId: string, p: {
  employeeId: string;
  paymentStatus: string;
  paymentMethod?: string;
  paymentReference?: string;
}) => request<Payment>("PATCH", `/payments/${paymentId}/status`, p);

// ─── Rulebooks ──────────────────────────────────────────────────────────────────

export interface Rulebook {
  cropCode: string;
  version: number;
  environment: string;
  source: string;
  pricing: Record<string, { pricePerKg: number }>;
  gradeThresholds: Record<string, Record<string, number>>;
}

export const getRulebook = (cropCode: string) =>
  request<Rulebook>("GET", `/rulebooks/${cropCode}`);

// ─── Composed Aggregations (Derived purely from existing backend endpoints) ─────

export interface PaymentHistoryItem {
  paymentId: string;
  procurementId: string;
  lotId: string;
  requestId: string;
  cropCode: string;
  quantityKg: number;
  payableAmount: number;
  paymentStatus: string;
  paymentMethod?: string;
  paymentReference?: string;
  createdAt?: string;
}

export async function getFarmerPaymentHistory(farmerId: string): Promise<PaymentHistoryItem[]> {
  try {
    const requests = await listFarmerProcurementRequests(farmerId);
    const history: PaymentHistoryItem[] = [];

    for (const req of requests) {
      if (!req.lotId) continue;
      try {
        const proc = await getProcurementForLot(req.lotId);
        if (!proc || !proc.procurementId) continue;
        try {
          const pay = await getPaymentForProcurement(proc.procurementId);
          if (pay && pay.paymentId) {
            history.push({
              paymentId: pay.paymentId,
              procurementId: proc.procurementId,
              lotId: proc.lotId,
              requestId: req.requestId,
              cropCode: proc.cropCode || req.cropCode,
              quantityKg: Number(proc.procurementQuantityKg) || 0,
              payableAmount: Number(pay.payableAmount ?? proc.grossAmount) || 0,
              paymentStatus: pay.paymentStatus,
              paymentMethod: pay.paymentMethod,
              paymentReference: pay.paymentReference,
              createdAt: pay.createdAt,
            });
          }
        } catch {
          // No payment recorded yet for this procurement
        }
      } catch {
        // No procurement recorded yet for this lot
      }
    }

    // Sort newest first
    return history.sort((a, b) => {
      if (a.paymentId && b.paymentId) return b.paymentId.localeCompare(a.paymentId);
      return 0;
    });
  } catch {
    return [];
  }
}

export interface GovernmentMetrics {
  totalProcurements: number;
  totalQuantityKg: number;
  totalQuantityMT: number;
  totalGrossAmount: number;
  totalPaymentsSettled: number;
  totalPaymentsAmount: number;
  totalFarmersServed: number;
  activeCentresCount: number;
  commodityMix: { cropCode: string; count: number; quantityKg: number; percent: number }[];
  centreComparison: { centreId: string; centreName: string; procurementsCount: number; totalQuantityKg: number }[];
}

export async function getGovernmentMetrics(): Promise<GovernmentMetrics> {
  const centres = await listCentres();
  const activeCentres = centres.filter(c => c.status === "ACTIVE");

  let totalProcurements = 0;
  let totalQuantityKg = 0;
  let totalGrossAmount = 0;
  let totalPaymentsSettled = 0;
  let totalPaymentsAmount = 0;
  const uniqueFarmers = new Set<string>();
  const cropStats: Record<string, { count: number; quantityKg: number }> = {};
  const centreComparison: { centreId: string; centreName: string; procurementsCount: number; totalQuantityKg: number }[] = [];

  for (const centre of activeCentres) {
    let centreProcCount = 0;
    let centreQty = 0;
    try {
      const requests = await listCentreProcurementRequests(centre.centreId);
      for (const req of requests) {
        if (!req.lotId) continue;
        try {
          const proc = await getProcurementForLot(req.lotId);
          if (!proc || !proc.procurementId) continue;

          totalProcurements++;
          centreProcCount++;
          const qty = Number(proc.procurementQuantityKg) || 0;
          const gross = Number(proc.grossAmount) || 0;
          totalQuantityKg += qty;
          centreQty += qty;
          totalGrossAmount += gross;

          if (proc.farmerId) uniqueFarmers.add(proc.farmerId);
          const crop = proc.cropCode || req.cropCode || "UNKNOWN";
          if (!cropStats[crop]) cropStats[crop] = { count: 0, quantityKg: 0 };
          cropStats[crop].count++;
          cropStats[crop].quantityKg += qty;

          try {
            const pay = await getPaymentForProcurement(proc.procurementId);
            if (pay) {
              if (pay.paymentStatus === "PAID") {
                totalPaymentsSettled++;
                totalPaymentsAmount += Number(pay.payableAmount) || 0;
              }
            }
          } catch {
            // No payment yet
          }
        } catch {
          // No procurement yet
        }
      }
    } catch {
      // Centre requests listing failed
    }

    centreComparison.push({
      centreId: centre.centreId,
      centreName: centre.centreName,
      procurementsCount: centreProcCount,
      totalQuantityKg: centreQty,
    });
  }

  const commodityMix = Object.entries(cropStats).map(([cropCode, s]) => ({
    cropCode,
    count: s.count,
    quantityKg: s.quantityKg,
    percent: totalQuantityKg > 0 ? Math.round((s.quantityKg / totalQuantityKg) * 100) : 0,
  }));

  return {
    totalProcurements,
    totalQuantityKg,
    totalQuantityMT: Number((totalQuantityKg / 1000).toFixed(2)),
    totalGrossAmount,
    totalPaymentsSettled,
    totalPaymentsAmount,
    totalFarmersServed: uniqueFarmers.size,
    activeCentresCount: activeCentres.length,
    commodityMix,
    centreComparison,
  };
}

export interface QueueItem {
  requestId: string;
  queueNumber: number;
  farmerId: string;
  cropCode: string;
  farmerArea?: string;
  expectedQuantityKg: number;
  assignedCentreId: string;
  assignedSlotId: string;
  bookingStatus: string;
  arrivalStatus: string;
  arrivedAt?: string | null;
  requestStatus: string;
  lotId?: string;
  createdAt: string;
  currentProcessingStatus: string;
  isProcessNextCandidate: boolean;
  qcGrade?: string | null;
  qcDecision?: string | null;
  qcAttemptId?: string | null;
  weighmentId?: string | null;
  procurementId?: string | null;
  canReject?: boolean;
}

export interface OfficerCommandMetrics {
  centreId: string;
  farmersToday: number;
  farmersTodayDetail: string;
  processedToday: number;
  processedTodayDetail: string;
  inQueue: number;
  inQueueDetail: string;
  averageWait: string;
  averageWaitDetail: string;
  isAverageWaitReal: boolean;
  capacity: string;
  capacityDetail: string;
  isCapacityReal: boolean;
  queueItems: QueueItem[];
}

export async function getOfficerCommandMetrics(centreId: string): Promise<OfficerCommandMetrics> {
  try {
    const [requests, slots, centre] = await Promise.all([
      listCentreProcurementRequests(centreId),
      listCentreSlots(centreId),
      getCentre(centreId),
    ]);

    const isToday = (dateStr?: string | null) => {
      if (!dateStr) return false;
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return false;
      const now = new Date();
      const isLocalToday =
        d.getFullYear() === now.getFullYear() &&
        d.getMonth() === now.getMonth() &&
        d.getDate() === now.getDate();
      const isUtcToday =
        d.getUTCFullYear() === now.getUTCFullYear() &&
        d.getUTCMonth() === now.getUTCMonth() &&
        d.getUTCDate() === now.getUTCDate();
      return isLocalToday || isUtcToday;
    };

    // 1. Farmers Today: strictly count today's actual physical arrivals (arrivedAt is today)
    const arrivedToday = requests.filter(
      (r) => r.arrivalStatus === "ARRIVED" && !!r.arrivedAt && isToday(r.arrivedAt)
    );
    const uniqueFarmersToday = new Set(arrivedToday.map((r) => r.farmerId));
    const farmersTodayCount = arrivedToday.length;
    const farmersTodayDetail =
      farmersTodayCount > 0
        ? `${farmersTodayCount} arrival(s) · ${uniqueFarmersToday.size} farmer(s)`
        : "No arrivals today";

    // 2. Processed Today, completed lots, and Wait Duration calculation:
    const completedLotIds = new Set<string>();
    let processedTodayCount = 0;
    const waitDurationsSec: number[] = [];

    const lotsWithRequests = requests.filter((r) => !!r.lotId);
    await Promise.all(
      lotsWithRequests.map(async (req) => {
        if (!req.lotId) return;
        try {
          const proc = await getProcurementForLot(req.lotId);
          if (proc && proc.procurementId) {
            completedLotIds.add(req.lotId);
            const procDate =
              (proc as unknown as { procuredAt?: string; createdAt?: string }).procuredAt ||
              (proc as unknown as { procuredAt?: string; createdAt?: string }).createdAt;
            if (isToday(procDate)) {
              processedTodayCount++;
            }
          }
        } catch {
          // No procurement yet for this lot
        }
      })
    );

    // Calculate operational waiting time from physical arrival to first operational event (QC) for today's arrived requests
    await Promise.all(
      lotsWithRequests.map(async (req) => {
        if (req.lotId && req.arrivalStatus === "ARRIVED" && req.arrivedAt && isToday(req.arrivedAt)) {
          try {
            const qcs = await listQCAttempts(req.lotId);
            if (qcs && qcs.length > 0 && qcs[0].performedAt) {
              const arrMs = new Date(req.arrivedAt).getTime();
              const qcMs = new Date(qcs[0].performedAt).getTime();
              const diffSec = (qcMs - arrMs) / 1000;
              if (diffSec >= 0 && diffSec < 86400 * 7) {
                waitDurationsSec.push(diffSec);
              }
            }
          } catch {
            // QC listing failed
          }
        }
      })
    );

    const processedTodayDetail =
      processedTodayCount > 0
        ? `${processedTodayCount} completed today`
        : "0 completed today";

    // 3. Build Active Queue Items:
    // Exclude cancelled, completed, and rejected requests
    const activeRequests = requests.filter(
      (r) =>
        r.bookingStatus !== "CANCELLED" &&
        r.requestStatus !== "CANCELLED" &&
        r.requestStatus !== "COMPLETED" &&
        r.requestStatus !== "REJECTED" &&
        (r.status ? r.status !== "CANCELLED" && r.status !== "COMPLETED" && r.status !== "REJECTED" : true) &&
        (!r.lotId || !completedLotIds.has(r.lotId))
    );

    // Fetch QC and weighment status for each active request to determine current processing stage
    const queueItems: QueueItem[] = await Promise.all(
      activeRequests.map(async (req) => {
        let currentStatus = "Awaiting Gate Arrival";
        let qcAttemptId: string | null = null;
        let qcGrade: string | null = null;
        let qcDecision: string | null = null;
        let weighmentId: string | null = null;
        let procurementId: string | null = null;
        let isGradeF = false;

        if (req.arrivalStatus === "ARRIVED") {
          currentStatus = "Arrived · Ready for QC";
          if (req.lotId) {
            try {
              const qcs = await listQCAttempts(req.lotId);
              if (qcs && qcs.length > 0) {
                const latestQc = qcs[qcs.length - 1];
                qcAttemptId = latestQc.qcAttemptId;
                try {
                  const evalRes = await getQCEvaluation(latestQc.qcAttemptId);
                  if (evalRes) {
                    qcGrade = evalRes.grade;
                    qcDecision = evalRes.decision;
                    if (evalRes.grade === "F" || evalRes.decision === "FAIL") {
                      currentStatus = "QC Failed (Grade F) · Action Needed";
                      isGradeF = true;
                    } else {
                      currentStatus = `QC Passed (Grade ${evalRes.grade}) · Ready for Weighment`;
                    }
                  } else {
                    currentStatus = "QC In Progress";
                  }
                } catch {
                  currentStatus = "QC Recorded";
                }
              }
            } catch {
              // Failed to fetch QC
            }

            if (!isGradeF) {
              try {
                const weights = await request<Weighment[]>("GET", `/lots/${req.lotId}/weighments`).catch(() => []);
                if (weights && weights.length > 0) {
                  const latestWeight = weights[weights.length - 1];
                  weighmentId = latestWeight.weighmentId;
                  currentStatus = "Weighed · Ready for Procurement";
                }
              } catch {
                // Failed to fetch weighments
              }
            }
          }
        }

        return {
          requestId: req.requestId,
          queueNumber: Number(req.queueNumber) || 1,
          farmerId: req.farmerId,
          cropCode: req.cropCode,
          farmerArea: req.farmerArea,
          expectedQuantityKg: Number(req.expectedQuantityKg) || 0,
          assignedCentreId: req.assignedCentreId,
          assignedSlotId: req.assignedSlotId,
          bookingStatus: req.bookingStatus ?? "CONFIRMED",
          arrivalStatus: req.arrivalStatus ?? "NOT_ARRIVED",
          arrivedAt: req.arrivedAt,
          requestStatus: req.requestStatus ?? "SCHEDULED",
          lotId: req.lotId,
          createdAt: req.createdAt ?? new Date().toISOString(),
          currentProcessingStatus: currentStatus,
          isProcessNextCandidate: false,
          qcGrade,
          qcDecision,
          qcAttemptId,
          weighmentId,
          procurementId,
          canReject: isGradeF || req.arrivalStatus === "ARRIVED",
        };
      })
    );

    // Sort queue by deterministic tie-breakers:
    // 1. queueNumber ascending
    // 2. assignedSlotId ascending
    // 3. createdAt ascending
    // 4. requestId ascending
    queueItems.sort((a, b) => {
      if (a.queueNumber !== b.queueNumber) return a.queueNumber - b.queueNumber;
      if (a.assignedSlotId !== b.assignedSlotId) return a.assignedSlotId.localeCompare(b.assignedSlotId);
      const timeA = new Date(a.createdAt).getTime();
      const timeB = new Date(b.createdAt).getTime();
      if (timeA !== timeB) return timeA - timeB;
      return a.requestId.localeCompare(b.requestId);
    });

    // Identify the SINGLE Process Next candidate:
    // Earliest arrived, non-terminal request that is NOT blocked by Grade F
    let candidateAssigned = false;
    for (const item of queueItems) {
      if (
        item.arrivalStatus === "ARRIVED" &&
        item.qcGrade !== "F" &&
        !candidateAssigned
      ) {
        item.isProcessNextCandidate = true;
        candidateAssigned = true;
      }
    }

    const inQueueCount = queueItems.length;
    const inQueueDetail =
      inQueueCount > 0
        ? `${inQueueCount} in active queue`
        : "Queue is clear";

    // 4. Average Wait:
    let averageWait = "—";
    let averageWaitDetail = "No arrival-to-QC events today";
    let isAverageWaitReal = false;

    if (waitDurationsSec.length > 0) {
      const avgSec = Math.round(
        waitDurationsSec.reduce((a, b) => a + b, 0) / waitDurationsSec.length
      );
      averageWait = avgSec < 60 ? `${avgSec}s` : `${Math.round(avgSec / 60)} min`;
      averageWaitDetail = `Avg. Arrival → 1st Action (QC): ${avgSec < 60 ? `${avgSec}s` : `${Math.round(avgSec / 60)} min`} (${waitDurationsSec.length} today)`;
      isAverageWaitReal = true;
    }

    // 5. Capacity:
    let totalSlotCapacityKg = 0;
    let totalAllocatedKg = 0;
    let totalRemainingKg = 0;

    for (const s of slots) {
      const cap = Number(s.capacityKg) || 0;
      const alloc = Number(s.allocatedKg) || 0;
      const rem = Number(s.remainingCapacityKg) || (cap - alloc);
      totalSlotCapacityKg += cap;
      totalAllocatedKg += alloc;
      totalRemainingKg += rem;
    }

    const allocatedMT = (totalAllocatedKg / 1000).toFixed(1);
    const capacityMT = (totalSlotCapacityKg / 1000).toFixed(0);
    const remainingMT = (totalRemainingKg / 1000).toFixed(1);
    const percentAllocated =
      totalSlotCapacityKg > 0
        ? ((totalAllocatedKg / totalSlotCapacityKg) * 100).toFixed(1)
        : "0.0";

    const capacityDisplay = totalSlotCapacityKg > 0 ? `${allocatedMT} / ${capacityMT} MT` : "—";
    const capacityDetail =
      totalSlotCapacityKg > 0
        ? `${percentAllocated}% allocated · ${remainingMT} MT free`
        : centre
        ? `Daily cap: ${Number(centre.dailyProcurementCapacityKg) / 1000} MT`
        : "Capacity data loading";

    return {
      centreId,
      farmersToday: farmersTodayCount,
      farmersTodayDetail,
      processedToday: processedTodayCount,
      processedTodayDetail,
      inQueue: inQueueCount,
      inQueueDetail,
      averageWait,
      averageWaitDetail,
      isAverageWaitReal,
      capacity: capacityDisplay,
      capacityDetail,
      isCapacityReal: totalSlotCapacityKg > 0,
      queueItems,
    };
  } catch (err) {
    console.error("Failed to load officer command metrics:", err);
    return {
      centreId,
      farmersToday: 0,
      farmersTodayDetail: "Error loading",
      processedToday: 0,
      processedTodayDetail: "Error loading",
      inQueue: 0,
      inQueueDetail: "Error loading",
      averageWait: "Placeholder",
      averageWaitDetail: "Demo / Placeholder — backend aggregate unavailable",
      isAverageWaitReal: false,
      capacity: "—",
      capacityDetail: "Error loading",
      isCapacityReal: false,
      queueItems: [],
    };
  }
}
