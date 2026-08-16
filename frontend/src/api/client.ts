import type {
  Manufacturer, AssetModel, AssetModelList,
  Transaction, TransactionList,
  FairValue, Signal, OpportunityScore,
  ConsensusScore, RiskAssessment, PortfolioRiskSnapshot,
  Position, PortfolioSnapshot, Alert, BacktestRun,
} from './types'

const BASE = '/api/v1'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function patch<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export const api = {
  // Catalog
  getManufacturers: () => get<Manufacturer[]>('/manufacturers'),
  getModels: (params?: { manufacturer_id?: string; skip?: number; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.manufacturer_id) q.set('manufacturer_id', params.manufacturer_id)
    if (params?.skip) q.set('skip', String(params.skip))
    if (params?.limit) q.set('limit', String(params.limit))
    const qs = q.toString()
    return get<AssetModelList>(`/models${qs ? `?${qs}` : ''}`)
  },
  getModel: (id: string) => get<AssetModel>(`/models/${id}`),

  // Market Data
  getTransactions: (params?: { model_id?: string; skip?: number; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.model_id) q.set('model_id', params.model_id)
    if (params?.skip) q.set('skip', String(params.skip))
    if (params?.limit) q.set('limit', String(params.limit))
    const qs = q.toString()
    return get<TransactionList>(`/transactions${qs ? `?${qs}` : ''}`)
  },
  getTransactionsForModel: (modelId: string) => get<Transaction[]>(`/transactions/${modelId}`),

  // Valuation
  getFairValue: (modelId: string) => get<FairValue>(`/fair-values/${modelId}`),
  refreshFairValues: () => post<{ message: string }>('/fair-values/refresh'),

  // Signals
  getSignals: (modelId: string) => get<Signal[]>(`/signals/${modelId}`),
  getOpportunities: (params?: { skip?: number; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.skip) q.set('skip', String(params.skip))
    if (params?.limit) q.set('limit', String(params.limit))
    const qs = q.toString()
    return get<OpportunityScore[]>(`/opportunities${qs ? `?${qs}` : ''}`)
  },

  // Consensus
  getConsensus: (modelId: string) => get<ConsensusScore>(`/consensus/${modelId}`),
  runConsensus: () => post<{ message: string }>('/consensus/run'),

  // Risk
  getPositionRisk: (positionId: string) => get<RiskAssessment>(`/risk/positions/${positionId}`),
  getPortfolioRisk: () => get<PortfolioRiskSnapshot>('/risk/portfolio'),

  // Ledger
  getPositions: (params?: { status?: string; skip?: number; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.status) q.set('status', params.status)
    if (params?.skip) q.set('skip', String(params.skip))
    if (params?.limit) q.set('limit', String(params.limit))
    const qs = q.toString()
    return get<Position[]>(`/positions${qs ? `?${qs}` : ''}`)
  },
  getPosition: (id: string) => get<Position>(`/positions/${id}`),
  createPosition: (data: Record<string, unknown>) => post<Position>('/positions', data),
  getPortfolioPnl: () => get<PortfolioSnapshot>('/pnl'),

  // Alerts
  getAlerts: (params?: { alert_type?: string; severity?: string; is_read?: boolean; skip?: number; limit?: number }) => {
    const q = new URLSearchParams()
    if (params?.alert_type) q.set('alert_type', params.alert_type)
    if (params?.severity) q.set('severity', params.severity)
    if (params?.is_read !== undefined) q.set('is_read', String(params.is_read))
    if (params?.skip) q.set('skip', String(params.skip))
    if (params?.limit) q.set('limit', String(params.limit))
    const qs = q.toString()
    return get<Alert[]>(`/alerts${qs ? `?${qs}` : ''}`)
  },
  markAlertRead: (id: string) => patch<Alert>(`/alerts/${id}/read`),

  // Backtest
  createBacktest: (data: Record<string, unknown>) => post<BacktestRun>('/backtest', data),
  getBacktestRun: (id: string) => get<BacktestRun>(`/backtest/${id}`),

  // Pipeline (not under /api/v1, uses /api/pipeline directly)
  runPipeline: async () => {
    const res = await fetch('/api/pipeline/run', { method: 'POST' })
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return res.json() as Promise<{ status: string; message?: string }>
  },
  getPipelineStatus: async () => {
    const res = await fetch('/api/pipeline/status')
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
    return res.json() as Promise<{ running: boolean; transactions: number }>
  },
}
