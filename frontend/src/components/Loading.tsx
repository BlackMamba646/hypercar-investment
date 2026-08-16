export default function Loading() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="text-term-cyan animate-pulse">Loading...</div>
    </div>
  )
}

export function ErrorMessage({ message }: { message: string }) {
  const isConnectionError = message.includes('Failed to fetch') || message.includes('NetworkError') || message.includes('fetch')
  return (
    <div className={`border rounded p-4 text-xs ${isConnectionError ? 'border-term-yellow/30 bg-term-yellow/5 text-term-yellow' : 'border-term-red/30 bg-term-red/5 text-term-red'}`}>
      {isConnectionError ? (
        <div>
          <div className="font-medium mb-1">Backend not connected</div>
          <div className="text-term-muted">Start the API server: <span className="text-term-cyan">uvicorn aatp.api.app:app --reload --port 8000</span></div>
          <div className="text-term-muted mt-0.5">Requires PostgreSQL + Redis via: <span className="text-term-cyan">docker-compose up -d</span></div>
        </div>
      ) : message}
    </div>
  )
}
