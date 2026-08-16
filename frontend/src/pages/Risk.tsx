import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { pct } from '../api/format'
import Card from '../components/Card'
import StatCard from '../components/StatCard'
import Loading, { ErrorMessage } from '../components/Loading'
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer } from 'recharts'

export default function Risk() {
  const portfolioRisk = useQuery({ queryKey: ['portfolio-risk'], queryFn: api.getPortfolioRisk })
  const positions = useQuery({ queryKey: ['positions-open'], queryFn: () => api.getPositions({ status: 'open', limit: 200 }) })

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-bold text-term-text">Risk Dashboard</h1>

      {/* Portfolio Risk */}
      <Card title="Portfolio Risk Snapshot">
        {portfolioRisk.isLoading ? <Loading /> : portfolioRisk.error ? (
          <div className="text-term-muted text-xs">No portfolio risk data available</div>
        ) : portfolioRisk.data && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard label="Max Manufacturer Exposure" value={pct(portfolioRisk.data.max_manufacturer_exposure_pct)} color={parseFloat(portfolioRisk.data.max_manufacturer_exposure_pct) > 40 ? 'red' : 'green'} />
              <StatCard label="Illiquid (90d)" value={pct(portfolioRisk.data.total_illiquid_90d_pct)} color={parseFloat(portfolioRisk.data.total_illiquid_90d_pct) > 50 ? 'red' : 'yellow'} />
              <StatCard label="Snapshot Date" value={portfolioRisk.data.snapshot_date} color="muted" />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <ConcentrationCard title="Manufacturer Concentration" data={portfolioRisk.data.manufacturer_concentration} />
              <ConcentrationCard title="Era Concentration" data={portfolioRisk.data.era_concentration} />
              <ConcentrationCard title="Type Concentration" data={portfolioRisk.data.type_concentration} />
            </div>

            {/* Scenario Analysis */}
            <Card title="Scenario Analysis">
              <div className="space-y-2">
                {Object.entries(portfolioRisk.data.scenario_analysis).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between border-b border-term-border py-1.5 last:border-0">
                    <span className="text-xs text-term-text">{k}</span>
                    <span className="text-xs text-term-muted">{JSON.stringify(v)}</span>
                  </div>
                ))}
              </div>
            </Card>

            {/* Narrative */}
            <div className="text-xs text-term-muted bg-term-bg border border-term-border rounded p-3">
              {portfolioRisk.data.narrative}
            </div>

            {portfolioRisk.data.warnings && Object.keys(portfolioRisk.data.warnings).length > 0 && (
              <div className="text-xs text-term-yellow bg-term-yellow/5 border border-term-yellow/20 rounded p-3">
                Warnings: {JSON.stringify(portfolioRisk.data.warnings)}
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Position Risk */}
      <Card title="Position Risk Assessments">
        {positions.isLoading ? <Loading /> : positions.error ? <ErrorMessage message={positions.error instanceof Error ? positions.error.message : 'Failed to load positions'} /> : (
          <div className="space-y-3">
            {(positions.data?.length ?? 0) === 0 ? (
              <div className="text-term-muted text-xs text-center py-4">No open positions</div>
            ) : positions.data?.map(p => (
              <PositionRisk key={p.id} positionId={p.id} description={p.description} />
            ))}
          </div>
        )}
      </Card>
    </div>
  )
}

function ConcentrationCard({ title, data }: { title: string; data: Record<string, unknown> }) {
  return (
    <div className="border border-term-border rounded p-3">
      <div className="text-[10px] text-term-muted uppercase tracking-wider mb-2">{title}</div>
      {Object.entries(data).map(([k, v]) => (
        <div key={k} className="flex items-center justify-between text-xs py-0.5">
          <span className="text-term-text">{k}</span>
          <span className="text-term-cyan">{typeof v === 'number' ? pct(v) : String(v)}</span>
        </div>
      ))}
    </div>
  )
}

function PositionRisk({ positionId, description }: { positionId: string; description: string }) {
  const risk = useQuery({
    queryKey: ['risk', positionId],
    queryFn: () => api.getPositionRisk(positionId),
    retry: false,
  })

  if (risk.isLoading) return null
  if (risk.error) return (
    <div className="border border-term-border rounded p-3">
      <span className="text-xs text-term-text">{description}</span>
      <span className="text-[10px] text-term-muted ml-2">No risk assessment</span>
    </div>
  )

  const d = risk.data!
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
    <div className="border border-term-border rounded p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-term-cyan font-medium">{description}</span>
        <span className={`text-sm font-bold ${composite > 0.7 ? 'text-term-red' : composite > 0.4 ? 'text-term-yellow' : 'text-term-green'}`}>
          Risk: {(composite * 100).toFixed(0)}%
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
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
          <div className="text-[10px] text-term-muted mt-2 pt-2 border-t border-term-border">{d.risk_explanation}</div>
          {d.recommendations && Object.keys(d.recommendations).length > 0 && (
            <div className="text-[10px] text-term-cyan">Recommendations: {JSON.stringify(d.recommendations)}</div>
          )}
        </div>
      </div>
    </div>
  )
}
