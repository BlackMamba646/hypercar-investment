import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { usd, pct, num, date, datetime, pnlColor, scoreColor } from '../api/format'
import Card from '../components/Card'
import StatCard from '../components/StatCard'
import Badge from '../components/Badge'
import Loading, { ErrorMessage } from '../components/Loading'

export default function CatalogDetail() {
  const { modelId } = useParams<{ modelId: string }>()
  const model = useQuery({ queryKey: ['model', modelId], queryFn: () => api.getModel(modelId!), enabled: !!modelId })
  const fairValue = useQuery({ queryKey: ['fairvalue', modelId], queryFn: () => api.getFairValue(modelId!), enabled: !!modelId })
  const signals = useQuery({ queryKey: ['signals', modelId], queryFn: () => api.getSignals(modelId!), enabled: !!modelId })
  const consensus = useQuery({ queryKey: ['consensus', modelId], queryFn: () => api.getConsensus(modelId!), enabled: !!modelId })
  const transactions = useQuery({ queryKey: ['transactions-model', modelId], queryFn: () => api.getTransactionsForModel(modelId!), enabled: !!modelId })

  if (model.isLoading) return <Loading />
  if (model.error) return <ErrorMessage message="Model not found" />
  const m = model.data!

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold text-term-text">{m.name} {m.variant || ''}</h1>
        <div className="flex gap-2 mt-1">
          {m.is_open_top && <Badge text="Open Top" variant="cyan" />}
          {m.is_limited_edition && <Badge text="Limited Edition" variant="yellow" />}
          {m.is_invitation_only && <Badge text="Invitation Only" variant="purple" />}
          {m.appreciation_stage && <Badge text={m.appreciation_stage} variant="green" />}
        </div>
      </div>

      {/* Model Details */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Production Years" value={m.production_year_start ? `${m.production_year_start}–${m.production_year_end || 'present'}` : '—'} color="muted" />
        <StatCard label="Total Produced" value={num(m.total_produced)} color="yellow" />
        <StatCard label="Liquid Supply" value={num(m.estimated_liquid_supply)} color="cyan" />
        <StatCard label="Scarcity Multiplier" value={m.variant_scarcity_multiplier ? `${m.variant_scarcity_multiplier}x` : '—'} color="orange" />
        <StatCard label="Engine" value={[m.engine_type, m.engine_config].filter(Boolean).join(' ') || '—'} color="muted" />
        <StatCard label="MSRP at Launch" value={m.msrp_at_launch ? `${usd(m.msrp_at_launch)}` : '—'} color="muted" />
        <StatCard label="Destroyed" value={num(m.known_destroyed)} color="red" />
        <StatCard label="Museum Held" value={num(m.known_museum_held)} color="muted" />
      </div>

      {/* Fair Value */}
      <Card title="Fair Value">
        {fairValue.isLoading ? <Loading /> : fairValue.error ? (
          <div className="text-term-muted text-xs">No fair value available</div>
        ) : fairValue.data && (
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <StatCard label="Low" value={usd(fairValue.data.fair_value_low)} color="red" />
              <StatCard label="Mid" value={usd(fairValue.data.fair_value_mid)} color="cyan" />
              <StatCard label="High" value={usd(fairValue.data.fair_value_high)} color="green" />
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard label="Confidence" value={pct(parseFloat(fairValue.data.confidence_score) * 100, 0)} color="yellow" />
              <StatCard label="Comparables" value={num(fairValue.data.comparable_count)} color="muted" />
              <StatCard label="Window" value={`${fairValue.data.comparable_window_months}mo`} color="muted" />
              <StatCard label="Stage" value={fairValue.data.appreciation_stage || '—'} color="green" />
              <StatCard label="30d Rate" value={pct(fairValue.data.appreciation_rate_30d)} color={pnlColor(fairValue.data.appreciation_rate_30d)} />
              <StatCard label="90d Rate" value={pct(fairValue.data.appreciation_rate_90d)} color={pnlColor(fairValue.data.appreciation_rate_90d)} />
              <StatCard label="365d Rate" value={pct(fairValue.data.appreciation_rate_365d)} color={pnlColor(fairValue.data.appreciation_rate_365d)} />
              <StatCard label="Valuation Date" value={date(fairValue.data.valuation_date)} color="muted" />
            </div>
            {fairValue.data.methodology && (
              <div className="text-[10px] text-term-muted">Methodology: {fairValue.data.methodology}</div>
            )}
            {fairValue.data.warnings && Object.keys(fairValue.data.warnings).length > 0 && (
              <div className="text-[10px] text-term-yellow">Warnings: {JSON.stringify(fairValue.data.warnings)}</div>
            )}
          </div>
        )}
      </Card>

      {/* Active Signals */}
      <Card title="Active Signals">
        {signals.isLoading ? <Loading /> : signals.error ? (
          <div className="text-term-muted text-xs">No signals available</div>
        ) : (
          <div className="space-y-2">
            {(signals.data?.length ?? 0) === 0 ? (
              <div className="text-term-muted text-xs text-center py-4">No active signals</div>
            ) : signals.data?.map(s => (
              <div key={s.id} className="border border-term-border rounded p-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge text={s.signal_type} variant="cyan" />
                    <span className={`text-xs font-bold ${s.direction > 0 ? 'text-term-green' : s.direction < 0 ? 'text-term-red' : 'text-term-muted'}`}>
                      {s.direction > 0 ? 'BULLISH' : s.direction < 0 ? 'BEARISH' : 'NEUTRAL'}
                    </span>
                  </div>
                  <div className="text-right">
                    <div className="text-xs text-term-text">Strength: {parseFloat(s.strength).toFixed(2)}</div>
                    <div className="text-[10px] text-term-muted">Conf: {pct(parseFloat(s.confidence) * 100, 0)}</div>
                  </div>
                </div>
                <div className="text-xs text-term-muted mt-1">{s.description}</div>
                <div className="flex items-center gap-3 mt-1 text-[10px] text-term-muted">
                  <span>{datetime(s.generated_at)}</span>
                  {s.transaction_count && <span>{s.transaction_count} txns</span>}
                  {s.expires_at && <span>Expires: {date(s.expires_at)}</span>}
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Consensus */}
      <Card title="Consensus Score">
        {consensus.isLoading ? <Loading /> : consensus.error ? (
          <div className="text-term-muted text-xs">No consensus score available</div>
        ) : consensus.data && (
          <div className="space-y-3">
            <div className="flex items-center gap-4">
              <div className={`text-2xl font-bold ${scoreColor(consensus.data.aggregate_score) === 'green' ? 'text-term-green' : scoreColor(consensus.data.aggregate_score) === 'yellow' ? 'text-term-yellow' : scoreColor(consensus.data.aggregate_score) === 'red' ? 'text-term-red' : 'text-term-muted'}`}>
                {consensus.data.aggregate_score}
              </div>
              <div>
                <Badge text={consensus.data.actionable ? 'ACTIONABLE' : consensus.data.status} variant={consensus.data.actionable ? 'green' : 'muted'} />
                {consensus.data.has_veto && <Badge text={`VETO: ${consensus.data.veto_model}`} variant="red" />}
              </div>
            </div>
            {consensus.data.disagreement_summary && (
              <div className="text-[10px] text-term-yellow">Disagreement: {consensus.data.disagreement_summary}</div>
            )}
            {consensus.data.veto_reason && (
              <div className="text-[10px] text-term-red">Veto reason: {consensus.data.veto_reason}</div>
            )}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {consensus.data.model_scores.map(ms => (
                <div key={ms.id} className="border border-term-border rounded p-2">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-term-muted uppercase">{ms.model_type}</span>
                    <span className={`text-sm font-bold ${ms.score > 0 ? 'text-term-green' : ms.score < 0 ? 'text-term-red' : 'text-term-muted'}`}>{ms.score > 0 ? '+' : ''}{ms.score}</span>
                  </div>
                  <div className="text-[10px] text-term-muted mt-1 truncate">{ms.rationale}</div>
                  <div className="text-[10px] text-term-muted">Conf: {pct(parseFloat(ms.confidence) * 100, 0)}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* Recent Transactions */}
      <Card title="Recent Transactions">
        {transactions.isLoading ? <Loading /> : transactions.error ? (
          <div className="text-term-muted text-xs">No transactions available</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-term-border">
                  <th className="text-left py-1.5 text-[10px] text-term-muted uppercase">Date</th>
                  <th className="text-left py-1.5 text-[10px] text-term-muted uppercase">Source</th>
                  <th className="text-left py-1.5 text-[10px] text-term-muted uppercase">Type</th>
                  <th className="text-right py-1.5 text-[10px] text-term-muted uppercase">Total USD</th>
                  <th className="text-right py-1.5 text-[10px] text-term-muted uppercase">Normalised</th>
                  <th className="text-left py-1.5 text-[10px] text-term-muted uppercase">Condition</th>
                </tr>
              </thead>
              <tbody>
                {(transactions.data?.length ?? 0) === 0 ? (
                  <tr><td colSpan={6} className="py-4 text-center text-term-muted">No transactions</td></tr>
                ) : transactions.data?.slice(0, 20).map(t => (
                  <tr key={t.id} className="border-b border-term-border">
                    <td className="py-1.5">{date(t.transaction_date)}</td>
                    <td className="py-1.5"><Badge text={t.source} variant="muted" /></td>
                    <td className="py-1.5">{t.transaction_type}</td>
                    <td className="py-1.5 text-right text-term-cyan">{usd(t.total_price_usd)}</td>
                    <td className="py-1.5 text-right text-term-green">{usd(t.normalised_price_usd)}</td>
                    <td className="py-1.5">{t.condition_grade ? <Badge text={t.condition_grade} variant="yellow" /> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}
