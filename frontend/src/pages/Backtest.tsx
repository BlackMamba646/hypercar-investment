import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { pct, num, date, datetime } from '../api/format'
import Card from '../components/Card'
import StatCard from '../components/StatCard'
import Badge from '../components/Badge'
import Loading, { ErrorMessage } from '../components/Loading'

export default function Backtest() {
  const queryClient = useQueryClient()
  const [selectedRun, setSelectedRun] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({
    name: '', description: '', start_date: '', end_date: '',
    parameters: '{}', model_versions: '{}',
  })

  const createBacktest = useMutation({
    mutationFn: (data: typeof formData) => api.createBacktest({
      name: data.name,
      description: data.description || null,
      start_date: data.start_date,
      end_date: data.end_date,
      parameters: JSON.parse(data.parameters),
      model_versions: JSON.parse(data.model_versions),
    }),
    onSuccess: (run) => {
      setShowForm(false)
      setSelectedRun(run.id)
      queryClient.invalidateQueries({ queryKey: ['backtest'] })
    },
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-term-text">Backtesting</h1>
        <button
          onClick={() => setShowForm(!showForm)}
          className="px-3 py-1.5 text-xs bg-term-cyan/10 text-term-cyan border border-term-cyan/30 rounded hover:bg-term-cyan/20"
        >
          {showForm ? 'Cancel' : 'New Backtest'}
        </button>
      </div>

      {/* Create Form */}
      {showForm && (
        <Card title="Create Backtest Run">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] text-term-muted uppercase block mb-1">Name *</label>
              <input
                value={formData.name}
                onChange={e => setFormData({ ...formData, name: e.target.value })}
                className="w-full bg-term-bg border border-term-border rounded px-2 py-1.5 text-xs text-term-text"
                placeholder="Q4 2024 Signal Validation"
              />
            </div>
            <div>
              <label className="text-[10px] text-term-muted uppercase block mb-1">Description</label>
              <input
                value={formData.description}
                onChange={e => setFormData({ ...formData, description: e.target.value })}
                className="w-full bg-term-bg border border-term-border rounded px-2 py-1.5 text-xs text-term-text"
                placeholder="Testing momentum signals on Ferrari models"
              />
            </div>
            <div>
              <label className="text-[10px] text-term-muted uppercase block mb-1">Start Date *</label>
              <input
                type="date"
                value={formData.start_date}
                onChange={e => setFormData({ ...formData, start_date: e.target.value })}
                className="w-full bg-term-bg border border-term-border rounded px-2 py-1.5 text-xs text-term-text"
              />
            </div>
            <div>
              <label className="text-[10px] text-term-muted uppercase block mb-1">End Date *</label>
              <input
                type="date"
                value={formData.end_date}
                onChange={e => setFormData({ ...formData, end_date: e.target.value })}
                className="w-full bg-term-bg border border-term-border rounded px-2 py-1.5 text-xs text-term-text"
              />
            </div>
            <div>
              <label className="text-[10px] text-term-muted uppercase block mb-1">Parameters (JSON)</label>
              <textarea
                value={formData.parameters}
                onChange={e => setFormData({ ...formData, parameters: e.target.value })}
                className="w-full bg-term-bg border border-term-border rounded px-2 py-1.5 text-xs text-term-text h-20 font-mono"
              />
            </div>
            <div>
              <label className="text-[10px] text-term-muted uppercase block mb-1">Model Versions (JSON)</label>
              <textarea
                value={formData.model_versions}
                onChange={e => setFormData({ ...formData, model_versions: e.target.value })}
                className="w-full bg-term-bg border border-term-border rounded px-2 py-1.5 text-xs text-term-text h-20 font-mono"
              />
            </div>
          </div>
          <button
            onClick={() => createBacktest.mutate(formData)}
            disabled={!formData.name || !formData.start_date || !formData.end_date || createBacktest.isPending}
            className="mt-3 px-4 py-1.5 text-xs bg-term-green/10 text-term-green border border-term-green/30 rounded hover:bg-term-green/20 disabled:opacity-50"
          >
            {createBacktest.isPending ? 'Creating...' : 'Create & Run'}
          </button>
          {createBacktest.error && <div className="text-xs text-term-red mt-2">Failed to create backtest</div>}
        </Card>
      )}

      {/* Run Detail */}
      {selectedRun && <BacktestDetail runId={selectedRun} />}
    </div>
  )
}

function BacktestDetail({ runId }: { runId: string }) {
  const run = useQuery({
    queryKey: ['backtest', runId],
    queryFn: () => api.getBacktestRun(runId),
    refetchInterval: (query) => query.state.data?.status === 'pending' || query.state.data?.status === 'running' ? 5000 : false,
  })

  if (run.isLoading) return <Loading />
  if (run.error) return <ErrorMessage message="Backtest run not found" />
  const d = run.data!

  return (
    <div className="space-y-4">
      <Card title={d.name}>
        <div className="flex items-center gap-3 mb-3">
          <Badge text={d.status} variant={d.status === 'completed' ? 'green' : d.status === 'running' ? 'cyan' : d.status === 'failed' ? 'red' : 'yellow'} />
          <span className="text-xs text-term-muted">{date(d.start_date)} to {date(d.end_date)}</span>
        </div>
        {d.description && <div className="text-xs text-term-muted mb-3">{d.description}</div>}

        {/* Results */}
        {d.status === 'completed' && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <StatCard label="Opportunities Flagged" value={num(d.total_opportunities_flagged)} color="cyan" />
            <StatCard label="Actionable" value={num(d.actionable_opportunities)} color="green" />
            <StatCard label="Signal Accuracy" value={pct(d.signal_accuracy_rate ? parseFloat(d.signal_accuracy_rate) * 100 : null, 1)} color="green" />
            <StatCard label="False Positive Rate" value={pct(d.false_positive_rate ? parseFloat(d.false_positive_rate) * 100 : null, 1)} color="red" />
            <StatCard label="Avg Return" value={pct(d.avg_return_pct)} color="green" />
            <StatCard label="Median Return" value={pct(d.median_return_pct)} color="green" />
            <StatCard label="Sharpe Ratio" value={d.sharpe_ratio ?? '—'} color="cyan" />
            <StatCard label="Max Drawdown" value={pct(d.max_drawdown_pct)} color="red" />
          </div>
        )}

        {d.error_message && (
          <div className="text-xs text-term-red bg-term-red/5 border border-term-red/20 rounded p-3 mt-3">
            {d.error_message}
          </div>
        )}

        {/* Parameters */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
          <div className="border border-term-border rounded p-2">
            <div className="text-[10px] text-term-muted uppercase mb-1">Parameters</div>
            <pre className="text-[10px] text-term-text overflow-x-auto">{JSON.stringify(d.parameters, null, 2)}</pre>
          </div>
          <div className="border border-term-border rounded p-2">
            <div className="text-[10px] text-term-muted uppercase mb-1">Model Versions</div>
            <pre className="text-[10px] text-term-text overflow-x-auto">{JSON.stringify(d.model_versions, null, 2)}</pre>
          </div>
        </div>

        {d.return_distribution && Object.keys(d.return_distribution).length > 0 && (
          <div className="border border-term-border rounded p-2 mt-3">
            <div className="text-[10px] text-term-muted uppercase mb-1">Return Distribution</div>
            <pre className="text-[10px] text-term-text overflow-x-auto">{JSON.stringify(d.return_distribution, null, 2)}</pre>
          </div>
        )}

        <div className="flex gap-3 mt-3 text-[10px] text-term-muted">
          {d.started_at && <span>Started: {datetime(d.started_at)}</span>}
          {d.completed_at && <span>Completed: {datetime(d.completed_at)}</span>}
          <span>Created: {datetime(d.created_at)}</span>
        </div>
      </Card>
    </div>
  )
}
