import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { usd, pct, num, date, pnlColor } from '../api/format'
import Card from '../components/Card'
import Badge from '../components/Badge'
import Loading, { ErrorMessage } from '../components/Loading'

export default function Valuations() {
  const queryClient = useQueryClient()
  const models = useQuery({ queryKey: ['models-all'], queryFn: () => api.getModels({ limit: 200 }) })

  const refresh = useMutation({
    mutationFn: api.refreshFairValues,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['fairvalue'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-term-text">Valuations</h1>
        <button
          onClick={() => refresh.mutate()}
          disabled={refresh.isPending}
          className="px-3 py-1.5 text-xs bg-term-cyan/10 text-term-cyan border border-term-cyan/30 rounded hover:bg-term-cyan/20 disabled:opacity-50"
        >
          {refresh.isPending ? 'Refreshing...' : 'Refresh Fair Values'}
        </button>
      </div>

      {models.isLoading ? <Loading /> : models.error ? <ErrorMessage message={models.error instanceof Error ? models.error.message : 'Failed to load models'} /> : (
        <div className="space-y-4">
          {models.data?.items.map(m => (
            <ModelFairValue key={m.id} modelId={m.id} modelName={`${m.name} ${m.variant || ''}`} />
          ))}
        </div>
      )}
    </div>
  )
}

function ModelFairValue({ modelId, modelName }: { modelId: string; modelName: string }) {
  const fv = useQuery({
    queryKey: ['fairvalue', modelId],
    queryFn: () => api.getFairValue(modelId),
    retry: false,
  })

  if (fv.isLoading) return null
  if (fv.error) return (
    <Card>
      <div className="flex items-center justify-between">
        <span className="text-xs text-term-text font-medium">{modelName}</span>
        <span className="text-[10px] text-term-muted">No valuation</span>
      </div>
    </Card>
  )

  const d = fv.data!
  return (
    <Card>
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="text-xs text-term-cyan font-medium">{modelName}</span>
          {d.appreciation_stage && <Badge text={d.appreciation_stage} variant="green" />}
        </div>
        <span className="text-[10px] text-term-muted">As of {date(d.valuation_date)}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-2">
        <div>
          <div className="text-[10px] text-term-muted">Low</div>
          <div className="text-xs text-term-red font-bold">{usd(d.fair_value_low)}</div>
        </div>
        <div>
          <div className="text-[10px] text-term-muted">Mid</div>
          <div className="text-xs text-term-cyan font-bold">{usd(d.fair_value_mid)}</div>
        </div>
        <div>
          <div className="text-[10px] text-term-muted">High</div>
          <div className="text-xs text-term-green font-bold">{usd(d.fair_value_high)}</div>
        </div>
        <div>
          <div className="text-[10px] text-term-muted">Confidence</div>
          <div className="text-xs text-term-yellow">{pct(parseFloat(d.confidence_score) * 100, 0)}</div>
        </div>
        <div>
          <div className="text-[10px] text-term-muted">Comparables</div>
          <div className="text-xs">{num(d.comparable_count)} / {d.comparable_window_months}mo</div>
        </div>
        <div>
          <div className="text-[10px] text-term-muted">30d</div>
          <div className={`text-xs ${pnlColor(d.appreciation_rate_30d) === 'green' ? 'text-term-green' : pnlColor(d.appreciation_rate_30d) === 'red' ? 'text-term-red' : 'text-term-muted'}`}>{pct(d.appreciation_rate_30d)}</div>
        </div>
        <div>
          <div className="text-[10px] text-term-muted">90d</div>
          <div className={`text-xs ${pnlColor(d.appreciation_rate_90d) === 'green' ? 'text-term-green' : pnlColor(d.appreciation_rate_90d) === 'red' ? 'text-term-red' : 'text-term-muted'}`}>{pct(d.appreciation_rate_90d)}</div>
        </div>
        <div>
          <div className="text-[10px] text-term-muted">365d</div>
          <div className={`text-xs ${pnlColor(d.appreciation_rate_365d) === 'green' ? 'text-term-green' : pnlColor(d.appreciation_rate_365d) === 'red' ? 'text-term-red' : 'text-term-muted'}`}>{pct(d.appreciation_rate_365d)}</div>
        </div>
      </div>
      {d.methodology && <div className="text-[10px] text-term-muted mt-2">Method: {d.methodology}</div>}
      {d.warnings && Object.keys(d.warnings).length > 0 && (
        <div className="text-[10px] text-term-yellow mt-1">Warnings: {JSON.stringify(d.warnings)}</div>
      )}
    </Card>
  )
}
