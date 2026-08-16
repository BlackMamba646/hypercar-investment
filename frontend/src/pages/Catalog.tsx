import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { num, usd, date } from '../api/format'
import Card from '../components/Card'
import Badge from '../components/Badge'
import Loading, { ErrorMessage } from '../components/Loading'
import DataTable from '../components/DataTable'

export default function Catalog() {
  const navigate = useNavigate()
  const [selectedMfr, setSelectedMfr] = useState<string>('')
  const manufacturers = useQuery({ queryKey: ['manufacturers'], queryFn: api.getManufacturers })
  const models = useQuery({
    queryKey: ['models', selectedMfr],
    queryFn: () => api.getModels({ manufacturer_id: selectedMfr || undefined, limit: 200 }),
  })

  return (
    <div className="space-y-6">
      <h1 className="text-lg font-bold text-term-text">Asset Catalog</h1>

      {/* Manufacturers */}
      <Card title="Manufacturers">
        {manufacturers.isLoading ? <Loading /> : manufacturers.error ? <ErrorMessage message={manufacturers.error instanceof Error ? manufacturers.error.message : 'Failed to load manufacturers'} /> : (
          <DataTable
            columns={[
              { key: 'name', header: 'Name', render: r => <span className="text-term-cyan font-medium">{r.name as string}</span> },
              { key: 'country', header: 'Country' },
              { key: 'asset_class', header: 'Asset Class', render: r => <Badge text={r.asset_class as string} variant="purple" /> },
              { key: 'prestige_score', header: 'Prestige', render: r => r.prestige_score ? <span className="text-term-yellow">{String(r.prestige_score)}</span> : <span className="text-term-muted">—</span> },
              { key: 'notes', header: 'Notes', render: r => <span className="text-term-muted truncate max-w-[200px] inline-block">{String(r.notes || '—')}</span> },
              { key: 'created_at', header: 'Added', render: r => <span className="text-term-muted">{date(r.created_at as string)}</span> },
            ]}
            data={manufacturers.data || []}
            onRowClick={(r: any) => setSelectedMfr(r.id)}
          />
        )}
      </Card>

      {/* Models */}
      <Card
        title={`Asset Models${selectedMfr ? ' (filtered)' : ''}`}
        action={selectedMfr ? <button onClick={() => setSelectedMfr('')} className="text-[10px] text-term-cyan hover:underline">Clear filter</button> : undefined}
      >
        {models.isLoading ? <Loading /> : models.error ? <ErrorMessage message={models.error instanceof Error ? models.error.message : 'Failed to load models'} /> : (
          <>
            <div className="text-[10px] text-term-muted mb-2">{models.data?.total ?? 0} models</div>
            <DataTable
              columns={[
                { key: 'name', header: 'Model', render: r => (
                  <div>
                    <span className="text-term-text font-medium">{r.name as string}</span>
                    {r.variant && <span className="text-term-muted ml-1">{r.variant as string}</span>}
                  </div>
                )},
                { key: 'production_year_start', header: 'Years', render: r => {
                  const s = r.production_year_start, e = r.production_year_end
                  return s ? <span>{String(s)}{e ? `–${e}` : '+'}</span> : <span className="text-term-muted">—</span>
                }},
                { key: 'total_produced', header: 'Produced', render: r => <span className="text-term-yellow">{num(r.total_produced as number)}</span> },
                { key: 'estimated_liquid_supply', header: 'Liquid Supply', render: r => num(r.estimated_liquid_supply as number) },
                { key: 'flags', header: 'Flags', render: r => (
                  <div className="flex gap-1">
                    {r.is_open_top && <Badge text="Open" variant="cyan" />}
                    {r.is_limited_edition && <Badge text="Ltd" variant="yellow" />}
                    {r.is_invitation_only && <Badge text="Invite" variant="purple" />}
                  </div>
                )},
                { key: 'engine_type', header: 'Engine', render: r => (
                  <span className="text-term-muted">{[r.engine_type, r.engine_config].filter(Boolean).join(' ') || '—'}</span>
                )},
                { key: 'msrp_at_launch', header: 'MSRP', render: r => r.msrp_at_launch ? <span>{usd(r.msrp_at_launch as string)} {r.msrp_currency as string}</span> : <span className="text-term-muted">—</span> },
                { key: 'variant_scarcity_multiplier', header: 'Scarcity', render: r => r.variant_scarcity_multiplier ? <span className="text-term-orange">{String(r.variant_scarcity_multiplier)}x</span> : <span className="text-term-muted">—</span> },
                { key: 'appreciation_stage', header: 'Stage', render: r => r.appreciation_stage ? <Badge text={r.appreciation_stage as string} variant="green" /> : <span className="text-term-muted">—</span> },
              ]}
              data={models.data?.items || []}
              onRowClick={(r: any) => navigate(`/catalog/${r.id}`)}
            />
          </>
        )}
      </Card>
    </div>
  )
}
