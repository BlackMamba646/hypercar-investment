import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { usd, pct, date, pnlColor, statusColor } from '../api/format'
import Card from '../components/Card'
import StatCard from '../components/StatCard'
import Badge from '../components/Badge'
import Loading, { ErrorMessage } from '../components/Loading'

export default function Portfolio() {
  const navigate = useNavigate()
  const [statusFilter, setStatusFilter] = useState('')
  const pnl = useQuery({ queryKey: ['pnl'], queryFn: api.getPortfolioPnl })
  const positions = useQuery({
    queryKey: ['positions', statusFilter],
    queryFn: () => api.getPositions({ status: statusFilter || undefined, limit: 200 }),
  })

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-bold text-term-text">Portfolio & Ledger</h1>

      {/* Portfolio Snapshot */}
      <Card title="Portfolio P&L Snapshot">
        {pnl.isLoading ? <Loading /> : pnl.error ? (
          <div className="text-term-muted text-xs">No portfolio snapshot available</div>
        ) : pnl.data && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard label="Total Market Value" value={usd(pnl.data.total_market_value_usd)} color="cyan" />
              <StatCard label="Total Cost Basis" value={usd(pnl.data.total_cost_basis_usd)} color="muted" />
              <StatCard label="Unrealised P&L" value={usd(pnl.data.total_unrealised_pnl_usd)} color={pnlColor(pnl.data.total_unrealised_pnl_usd)} />
              <StatCard label="Realised P&L" value={usd(pnl.data.total_realised_pnl_usd)} color={pnlColor(pnl.data.total_realised_pnl_usd)} />
              <StatCard label="Portfolio IRR" value={pnl.data.portfolio_irr ? pct(pnl.data.portfolio_irr) : '—'} color={pnlColor(pnl.data.portfolio_irr)} />
              <StatCard label="Open Positions" value={pnl.data.open_positions_count} color="cyan" />
              <StatCard label="Capital Deployed" value={usd(pnl.data.capital_deployed_usd)} color="muted" />
              <StatCard label="Available Capital" value={usd(pnl.data.available_capital_usd)} color="green" />
            </div>
            {/* Position Breakdown */}
            {pnl.data.position_breakdown && Object.keys(pnl.data.position_breakdown).length > 0 && (
              <div className="border border-term-border rounded p-3">
                <div className="text-[10px] text-term-muted uppercase tracking-wider mb-2">Position Breakdown</div>
                {Object.entries(pnl.data.position_breakdown).map(([k, v]) => (
                  <div key={k} className="flex items-center justify-between text-xs py-0.5">
                    <span className="text-term-text">{k}</span>
                    <span className="text-term-cyan">{JSON.stringify(v)}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="text-[10px] text-term-muted">Snapshot: {date(pnl.data.snapshot_date)}</div>
          </div>
        )}
      </Card>

      {/* Positions */}
      <Card title="Positions">
        <div className="flex gap-2 mb-3">
          {['', 'open', 'pending_exit', 'exited'].map(s => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-2 py-1 text-[10px] rounded border ${
                statusFilter === s
                  ? 'bg-term-cyan/10 text-term-cyan border-term-cyan/30'
                  : 'text-term-muted border-term-border hover:bg-term-hover'
              }`}
            >
              {s || 'All'}
            </button>
          ))}
        </div>

        {positions.isLoading ? <Loading /> : positions.error ? <ErrorMessage message={positions.error instanceof Error ? positions.error.message : 'Failed to load positions'} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs whitespace-nowrap">
              <thead>
                <tr className="border-b border-term-border bg-term-surface">
                  {['Description', 'Status', 'Year', 'Ext Colour', 'Int Colour', 'Mileage', 'Acq Date', 'Acq Price', 'Channel', 'Fair Value', 'Cost Basis', 'Unrealised P&L', 'Realised P&L', 'IRR', 'Exit Date', 'Exit Price', 'Exit Channel', 'Identifier'].map(h => (
                    <th key={h} className="px-2 py-1.5 text-left text-[10px] text-term-muted uppercase tracking-wider font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(positions.data?.length ?? 0) === 0 ? (
                  <tr><td colSpan={18} className="px-2 py-8 text-center text-term-muted">No positions</td></tr>
                ) : positions.data?.map((p, i) => (
                  <tr
                    key={p.id}
                    className={`border-b border-term-border hover:bg-term-hover cursor-pointer ${i % 2 ? 'bg-term-surface/30' : ''}`}
                    onClick={() => navigate(`/portfolio/${p.id}`)}
                  >
                    <td className="px-2 py-1.5 text-term-text font-medium max-w-[200px] truncate">{p.description}</td>
                    <td className="px-2 py-1.5"><Badge text={p.status} variant={statusColor(p.status)} /></td>
                    <td className="px-2 py-1.5">{p.year ?? '—'}</td>
                    <td className="px-2 py-1.5">{p.colour_exterior ?? '—'}</td>
                    <td className="px-2 py-1.5">{p.colour_interior ?? '—'}</td>
                    <td className="px-2 py-1.5">{p.mileage_at_acquisition != null ? `${p.mileage_at_acquisition} mi` : '—'}</td>
                    <td className="px-2 py-1.5">{date(p.acquisition_date)}</td>
                    <td className="px-2 py-1.5 text-right">{usd(p.acquisition_price_usd)}</td>
                    <td className="px-2 py-1.5">{p.acquisition_channel}</td>
                    <td className="px-2 py-1.5 text-right text-term-cyan">{usd(p.current_fair_value_usd)}</td>
                    <td className="px-2 py-1.5 text-right">{usd(p.total_cost_basis)}</td>
                    <td className={`px-2 py-1.5 text-right ${pnlColor(p.unrealised_pnl) === 'green' ? 'text-term-green' : pnlColor(p.unrealised_pnl) === 'red' ? 'text-term-red' : 'text-term-muted'}`}>{usd(p.unrealised_pnl)}</td>
                    <td className={`px-2 py-1.5 text-right ${pnlColor(p.realised_pnl) === 'green' ? 'text-term-green' : pnlColor(p.realised_pnl) === 'red' ? 'text-term-red' : 'text-term-muted'}`}>{usd(p.realised_pnl)}</td>
                    <td className="px-2 py-1.5 text-right">{p.irr ? pct(p.irr) : '—'}</td>
                    <td className="px-2 py-1.5">{date(p.exit_date)}</td>
                    <td className="px-2 py-1.5 text-right">{usd(p.exit_price_usd)}</td>
                    <td className="px-2 py-1.5">{p.exit_channel ?? '—'}</td>
                    <td className="px-2 py-1.5 text-term-muted">{p.identifier ?? '—'}</td>
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
