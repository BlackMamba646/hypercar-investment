import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { datetime, severityColor } from '../api/format'
import Card from '../components/Card'
import Badge from '../components/Badge'
import Loading, { ErrorMessage } from '../components/Loading'

const ALERT_TYPES = ['', 'price_movement', 'catalyst', 'auction_result', 'consensus_change', 'holding_cost_warning', 'hold_period_warning', 'liquidity_warning', 'reconciliation_divergence']
const SEVERITIES = ['', 'info', 'warning', 'critical']

export default function Alerts() {
  const queryClient = useQueryClient()
  const [typeFilter, setTypeFilter] = useState('')
  const [severityFilter, setSeverityFilter] = useState('')
  const [readFilter, setReadFilter] = useState<string>('')

  const alerts = useQuery({
    queryKey: ['alerts', typeFilter, severityFilter, readFilter],
    queryFn: () => api.getAlerts({
      alert_type: typeFilter || undefined,
      severity: severityFilter || undefined,
      is_read: readFilter === '' ? undefined : readFilter === 'true',
      limit: 200,
    }),
  })

  const markRead = useMutation({
    mutationFn: api.markAlertRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  })

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-bold text-term-text">Alerts</h1>

      <Card>
        {/* Filters */}
        <div className="flex gap-3 mb-4 flex-wrap">
          <div>
            <label className="text-[10px] text-term-muted uppercase block mb-1">Type</label>
            <select
              value={typeFilter}
              onChange={e => setTypeFilter(e.target.value)}
              className="bg-term-bg border border-term-border rounded px-2 py-1 text-xs text-term-text"
            >
              {ALERT_TYPES.map(t => <option key={t} value={t}>{t || 'All Types'}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[10px] text-term-muted uppercase block mb-1">Severity</label>
            <select
              value={severityFilter}
              onChange={e => setSeverityFilter(e.target.value)}
              className="bg-term-bg border border-term-border rounded px-2 py-1 text-xs text-term-text"
            >
              {SEVERITIES.map(s => <option key={s} value={s}>{s || 'All'}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[10px] text-term-muted uppercase block mb-1">Status</label>
            <select
              value={readFilter}
              onChange={e => setReadFilter(e.target.value)}
              className="bg-term-bg border border-term-border rounded px-2 py-1 text-xs text-term-text"
            >
              <option value="">All</option>
              <option value="false">Unread</option>
              <option value="true">Read</option>
            </select>
          </div>
        </div>

        {alerts.isLoading ? <Loading /> : alerts.error ? <ErrorMessage message={alerts.error instanceof Error ? alerts.error.message : 'Failed to load alerts'} /> : (
          <div className="space-y-0">
            {(alerts.data?.length ?? 0) === 0 ? (
              <div className="text-term-muted text-xs text-center py-8">No alerts matching filters</div>
            ) : alerts.data?.map((a, i) => (
              <div
                key={a.id}
                className={`flex items-start gap-3 px-3 py-3 border-b border-term-border ${
                  !a.is_read ? 'bg-term-surface' : ''
                } ${i % 2 && a.is_read ? 'bg-term-surface/20' : ''}`}
              >
                <div className="shrink-0 mt-0.5">
                  <Badge text={a.severity} variant={severityColor(a.severity)} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-medium ${a.is_read ? 'text-term-muted' : 'text-term-text'}`}>{a.title}</span>
                    <Badge text={a.alert_type} variant="muted" />
                    {!a.is_read && <span className="w-1.5 h-1.5 rounded-full bg-term-cyan" />}
                  </div>
                  <div className="text-xs text-term-muted mt-0.5">{a.message}</div>
                  <div className="flex items-center gap-3 mt-1 text-[10px] text-term-muted">
                    <span>{datetime(a.created_at)}</span>
                    {a.asset_model_id && <span>Model: {a.asset_model_id.slice(0, 8)}...</span>}
                    {a.position_id && <span>Position: {a.position_id.slice(0, 8)}...</span>}
                    {a.read_at && <span>Read: {datetime(a.read_at)}</span>}
                  </div>
                  {a.data && Object.keys(a.data).length > 0 && (
                    <div className="text-[10px] text-term-muted mt-1 bg-term-bg rounded p-1.5 overflow-x-auto">
                      {JSON.stringify(a.data, null, 2)}
                    </div>
                  )}
                </div>
                {!a.is_read && (
                  <button
                    onClick={() => markRead.mutate(a.id)}
                    className="shrink-0 text-[10px] text-term-cyan hover:underline"
                  >
                    Mark read
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}
