import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Catalog from './pages/Catalog'
import CatalogDetail from './pages/CatalogDetail'
import MarketData from './pages/MarketData'
import Valuations from './pages/Valuations'
import Signals from './pages/Signals'
import Consensus from './pages/Consensus'
import Risk from './pages/Risk'
import Portfolio from './pages/Portfolio'
import PortfolioDetail from './pages/PortfolioDetail'
import Alerts from './pages/Alerts'
import Backtest from './pages/Backtest'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/catalog" element={<Catalog />} />
        <Route path="/catalog/:modelId" element={<CatalogDetail />} />
        <Route path="/market" element={<MarketData />} />
        <Route path="/valuations" element={<Valuations />} />
        <Route path="/signals" element={<Signals />} />
        <Route path="/consensus" element={<Consensus />} />
        <Route path="/risk" element={<Risk />} />
        <Route path="/portfolio" element={<Portfolio />} />
        <Route path="/portfolio/:positionId" element={<PortfolioDetail />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/backtest" element={<Backtest />} />
      </Route>
    </Routes>
  )
}
