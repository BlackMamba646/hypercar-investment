import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { pct, num, date, scoreColor } from '../api/format'
import Card from '../components/Card'
import Badge from '../components/Badge'
import Loading, { ErrorMessage } from '../components/Loading'
import { useNavigate } from 'react-router-dom'

export default function Signals() {
  const navigate = useNavigate()
  const opportunities = useQuery({ queryKey: ['opportunities-all'], queryFn: () => api.getOpportunities({ limit: 200 }) })

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-bold text-term-text">Signals & Opportunities</h1>

      <Card title="Opportunity Scanner">
        {opportunities.isLoading ? <Loading /> : opportunities.error ? <ErrorMessage message={opportunities.error instanceof Error ? opportunities.error.message : 'Failed to load opportunities'} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs whitespace-nowrap">
              <thead>
                <tr className="border-b border-term-border bg-term-surface">
                  {['Model ID', 'Score', 'Status', 'Signals', 'Liquidity', 'Cost-Adj Return', 'Days to Catalyst', 'Rule Flags', 'Scored At'].map(h => (
                    <th key={h} className="px-3 py-1.5 text-left text-[10px] text-term-muted uppercase tracking-wider font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(opportunities.data?.length ?? 0) === 0 ? (
                  <tr><td colSpan={9} className="px-3 py-8 text-center text-term-muted">No opportunities scored</td></tr>
                ) : opportunities.data?.map((o, i) => (
                  <tr
                    key={o.id}
                    className={`border-b border-term-border hover:bg-term-hover cursor-pointer ${i % 2 ? 'bg-term-surface/30' : ''}`}
                    onClick={() => navigate(`/catalog/${o.asset_model_id}`)}
                  >
                    <td className="px-3 py-2 text-term-cyan">{o.asset_model_id.slice(0, 8)}...</td>
                    <td className="px-3 py-2">
                      <span className={`text-sm font-bold ${
                        scoreColor(parseFloat(o.composite_score)) === 'green' ? 'text-term-green' :
                        scoreColor(parseFloat(o.composite_score)) === 'yellow' ? 'text-term-yellow' :
                        scoreColor(parseFloat(o.composite_score)) === 'red' ? 'text-term-red' : 'text-term-muted'
                      }`}>
                        {parseFloat(o.composite_score).toFixed(1)}
                      </span>
                    </td>
                    <td className="px-3 py-2"><Badge text={o.status} variant={o.status === 'actionable' ? 'green' : o.status === 'watchlist' ? 'cyan' : 'muted'} /></td>
                    <td className="px-3 py-2">{num(o.signal_count)}</td>
                    <td className="px-3 py-2">{o.liquidity_score ? parseFloat(o.liquidity_score).toFixed(2) : '—'}</td>
                    <td className="px-3 py-2">{pct(o.cost_adjusted_return_pct)}</td>
                    <td className="px-3 py-2">{o.time_to_catalyst_days != null ? `${o.time_to_catalyst_days}d` : '—'}</td>
                    <td className="px-3 py-2">{o.rule_flags ? Object.keys(o.rule_flags).length : 0} flags</td>
                    <td className="px-3 py-2 text-term-muted">{date(o.scored_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Signal Breakdown Legend */}
      <Card title="Signal Types Reference">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[
            { type: 'momentum', desc: 'Price momentum and trend strength' },
            { type: 'dealer_auction_spread', desc: 'Dealer vs auction price divergence' },
            { type: 'catalyst', desc: 'Event-driven catalysts (import eligibility, etc.)' },
            { type: 'volume_spike', desc: 'Unusual transaction volume' },
            { type: 'comparable_appreciation', desc: 'Cross-model appreciation signals' },
            { type: 'pattern_match', desc: 'Historical pattern recognition' },
          ].map(s => (
            <div key={s.type} className="border border-term-border rounded p-2">
              <Badge text={s.type} variant="cyan" />
              <div className="text-[10px] text-term-muted mt-1">{s.desc}</div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  )
}
