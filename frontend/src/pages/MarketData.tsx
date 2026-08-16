import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import { usd, num, date, pct } from '../api/format'
import Card from '../components/Card'
import Badge from '../components/Badge'
import Loading, { ErrorMessage } from '../components/Loading'

export default function MarketData() {
  const [page, setPage] = useState(0)
  const [modelFilter, setModelFilter] = useState('')
  const limit = 50

  const transactions = useQuery({
    queryKey: ['transactions', page, modelFilter],
    queryFn: () => api.getTransactions({ skip: page * limit, limit, model_id: modelFilter || undefined }),
  })
  const models = useQuery({ queryKey: ['models-all'], queryFn: () => api.getModels({ limit: 200 }) })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-term-text">Market Data</h1>
        <span className="text-[10px] text-term-muted">{transactions.data?.total ?? 0} transactions</span>
      </div>

      <Card>
        <div className="flex gap-3 mb-3">
          <select
            value={modelFilter}
            onChange={e => { setModelFilter(e.target.value); setPage(0) }}
            className="bg-term-bg border border-term-border rounded px-2 py-1 text-xs text-term-text"
          >
            <option value="">All Models</option>
            {models.data?.items.map(m => (
              <option key={m.id} value={m.id}>{m.name} {m.variant || ''}</option>
            ))}
          </select>
        </div>

        {transactions.isLoading ? <Loading /> : transactions.error ? <ErrorMessage message={transactions.error instanceof Error ? transactions.error.message : 'Failed to load transactions'} /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs whitespace-nowrap">
              <thead>
                <tr className="border-b border-term-border bg-term-surface">
                  {['Date', 'Source', 'Type', 'Year', 'Hammer', 'Premium', 'Total', 'Currency', 'Total USD', 'Normalised USD', 'Mileage', 'Ext Colour', 'Int Colour', 'Colour Tier', 'Condition', 'Country', 'Auction House', 'Dealer', 'Mileage Adj', 'Colour Adj', 'Options Adj', 'Geo Adj', 'Provenance Adj', 'Condition Adj'].map(h => (
                    <th key={h} className="px-2 py-1.5 text-left text-[10px] text-term-muted uppercase tracking-wider font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(transactions.data?.items.length ?? 0) === 0 ? (
                  <tr><td colSpan={24} className="px-2 py-8 text-center text-term-muted">No transactions</td></tr>
                ) : transactions.data?.items.map((t, i) => (
                  <tr key={t.id} className={`border-b border-term-border hover:bg-term-hover ${i % 2 ? 'bg-term-surface/30' : ''}`}>
                    <td className="px-2 py-1.5">{date(t.transaction_date)}</td>
                    <td className="px-2 py-1.5"><Badge text={t.source} variant="muted" /></td>
                    <td className="px-2 py-1.5"><Badge text={t.transaction_type} variant={t.transaction_type === 'auction_sold' ? 'green' : t.transaction_type === 'auction_not_sold' ? 'red' : 'muted'} /></td>
                    <td className="px-2 py-1.5">{t.year ?? '—'}</td>
                    <td className="px-2 py-1.5 text-right">{usd(t.hammer_price)}</td>
                    <td className="px-2 py-1.5 text-right">{usd(t.buyer_premium)}</td>
                    <td className="px-2 py-1.5 text-right">{usd(t.total_price)}</td>
                    <td className="px-2 py-1.5">{t.currency}</td>
                    <td className="px-2 py-1.5 text-right text-term-cyan">{usd(t.total_price_usd)}</td>
                    <td className="px-2 py-1.5 text-right text-term-green">{usd(t.normalised_price_usd)}</td>
                    <td className="px-2 py-1.5 text-right">{t.mileage != null ? `${num(t.mileage)} ${t.mileage_unit || 'mi'}` : '—'}</td>
                    <td className="px-2 py-1.5">{t.colour_exterior ?? '—'}</td>
                    <td className="px-2 py-1.5">{t.colour_interior ?? '—'}</td>
                    <td className="px-2 py-1.5">{t.colour_tier != null ? `T${t.colour_tier}` : '—'}</td>
                    <td className="px-2 py-1.5">{t.condition_grade ? <Badge text={t.condition_grade} variant="yellow" /> : '—'}</td>
                    <td className="px-2 py-1.5">{t.sale_country ?? '—'}</td>
                    <td className="px-2 py-1.5">{t.auction_house ?? '—'}</td>
                    <td className="px-2 py-1.5">{t.dealer_name ?? '—'}</td>
                    <td className="px-2 py-1.5 text-right text-term-muted">{pct(t.normalised_price_usd ? 0 : null)}</td>
                    <td className="px-2 py-1.5 text-right text-term-muted">—</td>
                    <td className="px-2 py-1.5 text-right text-term-muted">—</td>
                    <td className="px-2 py-1.5 text-right text-term-muted">—</td>
                    <td className="px-2 py-1.5 text-right text-term-muted">—</td>
                    <td className="px-2 py-1.5 text-right text-term-muted">—</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        <div className="flex items-center justify-between mt-3 pt-3 border-t border-term-border">
          <button
            onClick={() => setPage(p => Math.max(0, p - 1))}
            disabled={page === 0}
            className="text-xs text-term-cyan disabled:text-term-muted disabled:cursor-not-allowed hover:underline"
          >
            &lt; Prev
          </button>
          <span className="text-[10px] text-term-muted">Page {page + 1}</span>
          <button
            onClick={() => setPage(p => p + 1)}
            disabled={(transactions.data?.items.length ?? 0) < limit}
            className="text-xs text-term-cyan disabled:text-term-muted disabled:cursor-not-allowed hover:underline"
          >
            Next &gt;
          </button>
        </div>
      </Card>
    </div>
  )
}
