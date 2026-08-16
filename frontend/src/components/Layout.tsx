import { NavLink, Outlet } from 'react-router-dom'

const NAV = [
  { to: '/', label: 'Dashboard', icon: '>' },
  { to: '/catalog', label: 'Catalog', icon: '#' },
  { to: '/market', label: 'Market Data', icon: '$' },
  { to: '/valuations', label: 'Valuations', icon: '~' },
  { to: '/signals', label: 'Signals', icon: '!' },
  { to: '/consensus', label: 'Consensus', icon: '%' },
  { to: '/risk', label: 'Risk', icon: '^' },
  { to: '/portfolio', label: 'Portfolio', icon: '&' },
  { to: '/alerts', label: 'Alerts', icon: '*' },
  { to: '/backtest', label: 'Backtest', icon: '?' },
]

export default function Layout() {
  return (
    <>
      <aside className="w-52 shrink-0 bg-term-surface border-r border-term-border flex flex-col">
        <div className="p-4 border-b border-term-border">
          <div className="text-term-cyan font-bold text-sm tracking-wider">AATP</div>
          <div className="text-term-muted text-[10px] mt-0.5">Alternative Asset Trading Platform</div>
        </div>
        <nav className="flex-1 py-2">
          {NAV.map(n => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-2 px-4 py-2 text-xs transition-colors ${
                  isActive
                    ? 'text-term-cyan bg-term-hover border-r-2 border-term-cyan'
                    : 'text-term-muted hover:text-term-text hover:bg-term-hover'
                }`
              }
            >
              <span className="w-4 text-center opacity-50">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-term-border text-[10px] text-term-muted">
          v0.1.0
        </div>
      </aside>
      <main className="flex-1 overflow-auto bg-term-bg">
        <div className="p-6">
          <Outlet />
        </div>
      </main>
    </>
  )
}
