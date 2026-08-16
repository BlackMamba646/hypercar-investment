import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { pct, scoreColor } from '../api/format'
import Card from '../components/Card'
import Badge from '../components/Badge'
import Loading, { ErrorMessage } from '../components/Loading'
import { useNavigate } from 'react-router-dom'

export default function Consensus() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const models = useQuery({ queryKey: ['models-all'], queryFn: () => api.getModels({ limit: 200 }) })

  const runConsensus = useMutation({
    mutationFn: api.runConsensus,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['consensus'] }),
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-term-text">Consensus Engine</h1>
        <button
          onClick={() => runConsensus.mutate()}
          disabled={runConsensus.isPending}
          className="px-3 py-1.5 text-xs bg-term-cyan/10 text-term-cyan border border-term-cyan/30 rounded hover:bg-term-cyan/20 disabled:opacity-50"
        >
          {runConsensus.isPending ? 'Running...' : 'Run Consensus Scan'}
        </button>
      </div>

      {/* Model Scores Legend */}
      <Card title="Scoring Models">
        <div className="flex gap-4 flex-wrap text-[10px]">
          {['momentum', 'fundamental_value', 'liquidity', 'sentiment', 'macro', 'rules'].map(m => (
            <span key={m} className="text-term-muted"><Badge text={m} variant="purple" /> -2 to +2</span>
          ))}
          <span className="text-term-yellow">Veto at -2 | Actionable at +4 aggregate</span>
        </div>
      </Card>

      {models.isLoading ? <Loading /> : models.error ? <ErrorMessage message={models.error instanceof Error ? models.error.message : 'Failed to load'} /> : (
        <div className="space-y-3">
          {models.data?.items.map(m => (
            <ModelConsensus key={m.id} modelId={m.id} modelName={`${m.name} ${m.variant || ''}`} onNavigate={() => navigate(`/catalog/${m.id}`)} />
          ))}
        </div>
      )}
    </div>
  )
}

function ModelConsensus({ modelId, modelName, onNavigate }: { modelId: string; modelName: string; onNavigate: () => void }) {
  const c = useQuery({
    queryKey: ['consensus', modelId],
    queryFn: () => api.getConsensus(modelId),
    retry: false,
  })

  if (c.isLoading) return null
  if (c.error) return (
    <Card>
      <div className="flex items-center justify-between cursor-pointer" onClick={onNavigate}>
        <span className="text-xs text-term-text">{modelName}</span>
        <span className="text-[10px] text-term-muted">No consensus</span>
      </div>
    </Card>
  )

  const d = c.data!
  const sc = scoreColor(d.aggregate_score)

  return (
    <Card>
      <div className="flex items-center justify-between mb-2 cursor-pointer" onClick={onNavigate}>
        <div className="flex items-center gap-3">
          <span className={`text-xl font-bold ${sc === 'green' ? 'text-term-green' : sc === 'yellow' ? 'text-term-yellow' : sc === 'red' ? 'text-term-red' : 'text-term-muted'}`}>
            {d.aggregate_score > 0 ? '+' : ''}{d.aggregate_score}
          </span>
          <span className="text-xs text-term-cyan font-medium">{modelName}</span>
          <Badge text={d.actionable ? 'ACTIONABLE' : d.status} variant={d.actionable ? 'green' : d.status === 'watchlist' ? 'cyan' : 'muted'} />
          {d.has_veto && <Badge text={`VETO: ${d.veto_model}`} variant="red" />}
        </div>
      </div>

      {d.disagreement_summary && (
        <div className="text-[10px] text-term-yellow mb-2">Disagreement: {d.disagreement_summary}</div>
      )}
      {d.veto_reason && (
        <div className="text-[10px] text-term-red mb-2">Veto reason: {d.veto_reason}</div>
      )}

      <div className="flex gap-2 flex-wrap">
        {d.model_scores.map(ms => (
          <div key={ms.id} className="border border-term-border rounded px-3 py-1.5 min-w-[120px]">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[10px] text-term-muted uppercase">{ms.model_type}</span>
              <span className={`text-sm font-bold ${ms.score > 0 ? 'text-term-green' : ms.score < 0 ? 'text-term-red' : 'text-term-muted'}`}>
                {ms.score > 0 ? '+' : ''}{ms.score}
              </span>
            </div>
            <div className="text-[10px] text-term-muted truncate max-w-[150px]" title={ms.rationale}>{ms.rationale}</div>
            <div className="text-[10px] text-term-muted">Conf: {pct(parseFloat(ms.confidence) * 100, 0)}</div>
          </div>
        ))}
      </div>
    </Card>
  )
}
