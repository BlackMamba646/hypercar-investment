import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { usd, pct, date, pnlColor, statusColor } from '../api/format'
import Card from '../components/Card'
import StatCard from '../components/StatCard'
import Badge from '../components/Badge'
import Loading, { ErrorMessage } from '../components/Loading'
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer } from 'recharts'

export default function PortfolioDetail() {
  const { positionId } = useParams<{ positionId: string }>()
  const position = useQuery({ queryKey: ['position', positionId], queryFn: () => api.getPosition(positionId!), enabled: !!positionId })
  const risk = useQuery({ queryKey: ['risk', positionId], queryFn: () => api.getPositionRisk(positionId!), enabled: !!positionId, retry: false })

  if (position.isLoading) return <Loading />
  if (position.error) return <ErrorMessage message="Position not found" />
  const p = position.data!

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold text-term-text">{p.description}</h1>
        <div className="flex gap-2 mt-1">
          <Badge text={p.status} variant={statusColor(p.status)} />
          <Badge text={p.asset_class} variant="purple" />
          {p.identifier && <span className="text-[10px] text-term-muted">ID: {p.identifier}</span>}
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Acquisition Price" value={usd(p.acquisition_price_usd)} color="muted" />
        <StatCard label="Current Fair Value" value={usd(p.current_fair_value_usd)} color="cyan" />
        <StatCard label="Unrealised P&L" value={usd(p.unrealised_pnl)} color={pnlColor(p.unrealised_pnl)} />
        <StatCard label="IRR" value={p.irr ? pct(p.irr) : '—'} color={pnlColor(p.irr)} />
        <StatCard label="Total Cost Basis" value={usd(p.total_cost_basis)} color="muted" />
        <StatCard label="Realised P&L" value={usd(p.realised_pnl)} color={pnlColor(p.realised_pnl)} />
      </div>

      {/* Asset Details */}
      <Card title="Asset Details">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2 text-xs">
          <Detail label="Year" value={p.year} />
          <Detail label="Exterior Colour" value={p.colour_exterior} />
          <Detail label="Interior Colour" value={p.colour_interior} />
          <Detail label="Mileage at Acquisition" value={p.mileage_at_acquisition != null ? `${p.mileage_at_acquisition} mi` : null} />
          <Detail label="Identifier (VIN)" value={p.identifier} />
          <Detail label="Asset Class" value={p.asset_class} />
        </div>
      </Card>

      {/* Acquisition Details */}
      <Card title="Acquisition">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2 text-xs">
          <Detail label="Date" value={date(p.acquisition_date)} />
          <Detail label="Price" value={`${usd(p.acquisition_price)} ${p.acquisition_currency}`} />
          <Detail label="Price (USD)" value={usd(p.acquisition_price_usd)} />
          <Detail label="Channel" value={p.acquisition_channel} />
        </div>
      </Card>

      {/* Exit Details (if exited) */}
      {p.exit_date && (
        <Card title="Exit">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2 text-xs">
            <Detail label="Date" value={date(p.exit_date)} />
            <Detail label="Price (USD)" value={usd(p.exit_price_usd)} />
            <Detail label="Channel" value={p.exit_channel} />
          </div>
        </Card>
      )}

      {/* Valuation */}
      <Card title="Current Valuation">
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
          <Detail label="Fair Value (USD)" value={usd(p.current_fair_value_usd)} />
          <Detail label="Fair Value Date" value={date(p.fair_value_date)} />
        </div>
      </Card>

      {/* Risk Assessment */}
      <Card title="Risk Assessment">
        {risk.isLoading ? <Loading /> : risk.error ? (
          <div className="text-term-muted text-xs">No risk assessment available</div>
        ) : risk.data && (() => {
          const d = risk.data
          const radarData = [
            { dim: 'Liquidity', score: parseFloat(d.liquidity_risk_score) },
            { dim: 'Concentration', score: parseFloat(d.concentration_risk_score) },
            { dim: 'Physical', score: parseFloat(d.physical_risk_score) },
            { dim: 'Counterparty', score: parseFloat(d.counterparty_risk_score) },
            { dim: 'Spec', score: parseFloat(d.spec_risk_score) },
            { dim: 'Provenance', score: parseFloat(d.provenance_risk_score) },
          ]
          const composite = parseFloat(d.composite_risk_score)

          return (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <span className={`text-lg font-bold ${composite > 0.7 ? 'text-term-red' : composite > 0.4 ? 'text-term-yellow' : 'text-term-green'}`}>
                  Composite: {(composite * 100).toFixed(0)}%
                </span>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="h-48">
                  <ResponsiveContainer width="100%" height="100%">
                    <RadarChart data={radarData}>
                      <PolarGrid stroke="#1e1e2e" />
                      <PolarAngleAxis dataKey="dim" tick={{ fill: '#6b6b80', fontSize: 10 }} />
                      <PolarRadiusAxis domain={[0, 1]} tick={false} axisLine={false} />
                      <Radar dataKey="score" stroke="#00d4ff" fill="#00d4ff" fillOpacity={0.15} />
                    </RadarChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-1">
                  {radarData.map(r => (
                    <div key={r.dim} className="flex items-center justify-between text-xs">
                      <span className="text-term-muted">{r.dim}</span>
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-1.5 bg-term-border rounded overflow-hidden">
                          <div className={`h-full rounded ${r.score > 0.7 ? 'bg-term-red' : r.score > 0.4 ? 'bg-term-yellow' : 'bg-term-green'}`} style={{ width: `${r.score * 100}%` }} />
                        </div>
                        <span className="w-8 text-right">{(r.score * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="text-xs text-term-muted">{d.risk_explanation}</div>
              {d.risk_factors && Object.keys(d.risk_factors).length > 0 && (
                <div className="text-[10px] text-term-muted">Factors: {JSON.stringify(d.risk_factors)}</div>
              )}
              {d.recommendations && Object.keys(d.recommendations).length > 0 && (
                <div className="text-[10px] text-term-cyan">Recommendations: {JSON.stringify(d.recommendations)}</div>
              )}
            </div>
          )
        })()}
      </Card>

      {/* Notes */}
      {p.notes && (
        <Card title="Notes">
          <div className="text-xs text-term-muted">{p.notes}</div>
        </Card>
      )}
    </div>
  )
}

function Detail({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <div className="text-[10px] text-term-muted uppercase">{label}</div>
      <div className="text-term-text">{value != null && value !== '' ? String(value) : '—'}</div>
    </div>
  )
}
