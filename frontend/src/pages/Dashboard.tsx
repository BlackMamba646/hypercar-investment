import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { usd, pct, num, pnlColor, severityColor, scoreColor, datetime } from '../api/format'
import StatCard from '../components/StatCard'
import Card from '../components/Card'
import Badge from '../components/Badge'
import Loading, { ErrorMessage } from '../components/Loading'
import { useNavigate } from 'react-router-dom'

export default function Dashboard() {
  const navigate = useNavigate()
  const pnl = useQuery({ queryKey: ['pnl'], queryFn: api.getPortfolioPnl })
  const opportunities = useQuery({ queryKey: ['opportunities'], queryFn: () => api.getOpportunities({ limit: 5 }) })
  const alerts = useQuery({ queryKey: ['alerts-unread'], queryFn: () => api.getAlerts({ is_read: false, limit: 5 }) })
  const positions = useQuery({ queryKey: ['positions-open'], queryFn: () => api.getPositions({ status: 'open', limit: 5 }) })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-term-text">Dashboard</h1>
        <span className="text-[10px] text-term-muted">AATP Terminal</span>
      </div>

      {/* Portfolio Summary */}
      {pnl.isLoading ? <Loading /> : pnl.data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <StatCard label="Total Market Value" value={usd(pnl.data.total_market_value_usd)} color="cyan" />
          <StatCard label="Cost Basis" value={usd(pnl.data.total_cost_basis_usd)} color="muted" />
          <StatCard label="Unrealised P&L" value={usd(pnl.data.total_unrealised_pnl_usd)} color={pnlColor(pnl.data.total_unrealised_pnl_usd)} />
          <StatCard label="Realised P&L" value={usd(pnl.data.total_realised_pnl_usd)} color={pnlColor(pnl.data.total_realised_pnl_usd)} />
          <StatCard label="Portfolio IRR" value={pnl.data.portfolio_irr ? pct(pnl.data.portfolio_irr) : '—'} color={pnlColor(pnl.data.portfolio_irr)} />
          <StatCard label="Open Positions" value={num(pnl.data.open_positions_count)} color="cyan" />
          <StatCard label="Capital Deployed" value={usd(pnl.data.capital_deployed_usd)} color="muted" />
          <StatCard label="Available Capital" value={usd(pnl.data.available_capital_usd)} color="green" />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Top Opportunities */}
        <Card title="Top Opportunities" action={<button onClick={() => navigate('/signals')} className="text-[10px] text-term-cyan hover:underline">View all</button>}>
          {opportunities.isLoading ? <Loading /> : opportunities.error ? <ErrorMessage message={opportunities.error instanceof Error ? opportunities.error.message : 'Failed to load'} /> : (
            <div className="space-y-2">
              {(opportunities.data?.length ?? 0) === 0 ? (
                <div className="text-term-muted text-xs py-4 text-center">No opportunities scored yet</div>
              ) : opportunities.data?.map(o => (
                <div key={o.id} className="flex items-center justify-between py-1.5 border-b border-term-border last:border-0">
                  <div>
                    <span className="text-xs text-term-text">{o.asset_model_id.slice(0, 8)}...</span>
                    <div className="flex gap-2 mt-0.5">
                      <Badge text={o.status} variant={scoreColor(parseFloat(o.composite_score))} />
                      <span className="text-[10px] text-term-muted">{o.signal_count} signals</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`text-sm font-bold ${parseFloat(o.composite_score) >= 4 ? 'text-term-green' : parseFloat(o.composite_score) >= 2 ? 'text-term-yellow' : 'text-term-muted'}`}>
                      {parseFloat(o.composite_score).toFixed(1)}
                    </div>
                    {o.cost_adjusted_return_pct && (
                      <div className="text-[10px] text-term-muted">{pct(o.cost_adjusted_return_pct)} return</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Alerts */}
        <Card title="Recent Alerts" action={<button onClick={() => navigate('/alerts')} className="text-[10px] text-term-cyan hover:underline">View all</button>}>
          {alerts.isLoading ? <Loading /> : alerts.error ? <ErrorMessage message={alerts.error instanceof Error ? alerts.error.message : 'Failed to load'} /> : (
            <div className="space-y-2">
              {(alerts.data?.length ?? 0) === 0 ? (
                <div className="text-term-muted text-xs py-4 text-center">No unread alerts</div>
              ) : alerts.data?.map(a => (
                <div key={a.id} className="flex items-start gap-2 py-1.5 border-b border-term-border last:border-0">
                  <Badge text={a.severity} variant={severityColor(a.severity)} />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs text-term-text truncate">{a.title}</div>
                    <div className="text-[10px] text-term-muted">{datetime(a.created_at)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Open Positions */}
        <Card title="Open Positions" className="lg:col-span-2" action={<button onClick={() => navigate('/portfolio')} className="text-[10px] text-term-cyan hover:underline">View all</button>}>
          {positions.isLoading ? <Loading /> : positions.error ? <ErrorMessage message={positions.error instanceof Error ? positions.error.message : 'Failed to load'} /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-term-border">
                    <th className="text-left py-1.5 text-[10px] text-term-muted uppercase">Description</th>
                    <th className="text-right py-1.5 text-[10px] text-term-muted uppercase">Acquisition</th>
                    <th className="text-right py-1.5 text-[10px] text-term-muted uppercase">Fair Value</th>
                    <th className="text-right py-1.5 text-[10px] text-term-muted uppercase">P&L</th>
                    <th className="text-right py-1.5 text-[10px] text-term-muted uppercase">IRR</th>
                  </tr>
                </thead>
                <tbody>
                  {(positions.data?.length ?? 0) === 0 ? (
                    <tr><td colSpan={5} className="py-4 text-center text-term-muted">No open positions</td></tr>
                  ) : positions.data?.map(p => (
                    <tr key={p.id} className="border-b border-term-border hover:bg-term-hover cursor-pointer" onClick={() => navigate(`/portfolio/${p.id}`)}>
                      <td className="py-1.5 text-term-text">{p.description}</td>
                      <td className="py-1.5 text-right">{usd(p.acquisition_price_usd)}</td>
                      <td className="py-1.5 text-right text-term-cyan">{usd(p.current_fair_value_usd)}</td>
                      <td className={`py-1.5 text-right ${pnlColor(p.unrealised_pnl) === 'green' ? 'text-term-green' : pnlColor(p.unrealised_pnl) === 'red' ? 'text-term-red' : 'text-term-muted'}`}>
                        {usd(p.unrealised_pnl)}
                      </td>
                      <td className="py-1.5 text-right">{p.irr ? pct(p.irr) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}
