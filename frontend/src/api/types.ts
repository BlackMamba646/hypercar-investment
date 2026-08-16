export interface Manufacturer {
  id: string
  name: string
  country: string | null
  asset_class: string
  prestige_score: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface AssetModel {
  id: string
  manufacturer_id: string
  asset_class: string
  name: string
  variant: string | null
  production_year_start: number | null
  production_year_end: number | null
  total_produced: number | null
  estimated_liquid_supply: number | null
  known_destroyed: number | null
  known_museum_held: number | null
  is_open_top: boolean
  is_limited_edition: boolean
  is_invitation_only: boolean
  engine_type: string | null
  engine_config: string | null
  msrp_at_launch: string | null
  msrp_currency: string | null
  homologation_type: string | null
  variant_scarcity_multiplier: string | null
  appreciation_stage: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface AssetModelList {
  items: AssetModel[]
  total: number
}

export interface Transaction {
  id: string
  provenance_id: string
  asset_model_id: string
  asset_class: string
  source: string
  external_id: string | null
  transaction_type: string
  transaction_date: string
  hammer_price: string | null
  buyer_premium: string | null
  total_price: string | null
  currency: string
  total_price_usd: string | null
  year: number | null
  mileage: number | null
  mileage_unit: string | null
  colour_exterior: string | null
  colour_interior: string | null
  colour_tier: number | null
  condition_grade: string | null
  normalised_price_usd: string | null
  sale_country: string | null
  auction_house: string | null
  dealer_name: string | null
  created_at: string
  updated_at: string
}

export interface TransactionList {
  items: Transaction[]
  total: number
}

export interface FairValue {
  id: string
  asset_model_id: string
  valuation_date: string
  currency: string
  fair_value_low: string
  fair_value_mid: string
  fair_value_high: string
  confidence_score: string
  comparable_count: number
  comparable_window_months: number
  appreciation_stage: string | null
  appreciation_rate_30d: string | null
  appreciation_rate_90d: string | null
  appreciation_rate_365d: string | null
  methodology: string | null
  warnings: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface Signal {
  id: string
  asset_model_id: string
  signal_type: string
  generated_at: string
  strength: string
  direction: number
  confidence: string
  description: string
  supporting_data: Record<string, unknown>
  transaction_count: number | null
  is_active: boolean
  expires_at: string | null
  created_at: string
  updated_at: string
}

export interface OpportunityScore {
  id: string
  asset_model_id: string
  scored_at: string
  composite_score: string
  signal_count: number
  signal_breakdown: Record<string, unknown>
  liquidity_score: string | null
  cost_adjusted_return_pct: string | null
  time_to_catalyst_days: number | null
  rule_flags: Record<string, unknown> | null
  status: string
  created_at: string
  updated_at: string
}

export interface ConsensusModelScore {
  id: string
  consensus_score_id: string
  model_type: string
  score: number
  confidence: string
  rationale: string
  supporting_data: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ConsensusScore {
  id: string
  asset_model_id: string
  scored_at: string
  aggregate_score: number
  has_veto: boolean
  veto_model: string | null
  veto_reason: string | null
  status: string
  disagreement_summary: string | null
  actionable: boolean
  model_scores: ConsensusModelScore[]
  created_at: string
  updated_at: string
}

export interface RiskAssessment {
  id: string
  position_id: string
  assessed_at: string
  liquidity_risk_score: string
  concentration_risk_score: string
  physical_risk_score: string
  counterparty_risk_score: string
  spec_risk_score: string
  provenance_risk_score: string
  composite_risk_score: string
  risk_explanation: string
  risk_factors: Record<string, unknown>
  recommendations: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface PortfolioRiskSnapshot {
  id: string
  snapshot_date: string
  manufacturer_concentration: Record<string, unknown>
  era_concentration: Record<string, unknown>
  type_concentration: Record<string, unknown>
  max_manufacturer_exposure_pct: string
  total_illiquid_90d_pct: string
  scenario_analysis: Record<string, unknown>
  warnings: Record<string, unknown> | null
  narrative: string
  created_at: string
  updated_at: string
}

export interface Position {
  id: string
  asset_model_id: string
  asset_class: string
  status: string
  identifier: string | null
  year: number | null
  description: string
  colour_exterior: string | null
  colour_interior: string | null
  mileage_at_acquisition: number | null
  acquisition_date: string
  acquisition_price: string
  acquisition_currency: string
  acquisition_price_usd: string
  acquisition_channel: string
  exit_date: string | null
  exit_price: string | null
  exit_price_usd: string | null
  exit_channel: string | null
  current_fair_value_usd: string | null
  fair_value_date: string | null
  total_cost_basis: string | null
  unrealised_pnl: string | null
  realised_pnl: string | null
  irr: string | null
  notes: string | null
  created_at: string
  updated_at: string
}

export interface PortfolioSnapshot {
  id: string
  snapshot_date: string
  total_market_value_usd: string
  total_cost_basis_usd: string
  total_unrealised_pnl_usd: string
  total_realised_pnl_usd: string
  portfolio_irr: string | null
  open_positions_count: number
  capital_deployed_usd: string
  available_capital_usd: string | null
  position_breakdown: Record<string, unknown>
  created_at: string
}

export interface Alert {
  id: string
  alert_type: string
  severity: string
  asset_model_id: string | null
  position_id: string | null
  title: string
  message: string
  data: Record<string, unknown> | null
  is_read: boolean
  read_at: string | null
  created_at: string
  updated_at: string
}

export interface BacktestRun {
  id: string
  name: string
  description: string | null
  start_date: string
  end_date: string
  parameters: Record<string, unknown>
  model_versions: Record<string, unknown>
  total_opportunities_flagged: number | null
  actionable_opportunities: number | null
  signal_accuracy_rate: string | null
  avg_return_pct: string | null
  median_return_pct: string | null
  false_positive_rate: string | null
  sharpe_ratio: string | null
  max_drawdown_pct: string | null
  return_distribution: Record<string, unknown> | null
  status: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}
