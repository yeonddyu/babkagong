// 백엔드 응답 타입 (docs/api_spec.md)

export type Area = '강남역' | '역삼역'

export interface Check {
  criterion: string
  result: 'pass' | 'fail' | 'unknown'
  value: string
  basis: string
  hard: boolean
}

export interface Cafe {
  name: string
  source: string
  source_id: string
  road_address: string | null
  address: string | null
  latitude: number | null
  longitude: number | null
  distance_m: number | null
  distance_basis: string | null
  estimated_walk_minutes: number | null
  place_url: string | null
  phone: string | null
}

export interface Recommendation {
  name: string
  source: string
  source_id: string
  address: string | null
  area: string | null
  latitude: number | null
  longitude: number | null
  category: string | null
  food_type: string | null
  distance_m: number | null
  estimated_walk_minutes: number | null
  matched_menus: { name: string; price_krw: number | null }[]
  sample_menus?: { name: string; price_krw: number | null }[]
  business_hours: string | null
  checks: Check[]
  score: number
  score_reasons: string[]
  unverified: string[]
  cafes: Cafe[]
  cafe_notice: string | null
}

export interface RunEvent {
  session_id: string
  run_id: string
  seq: number
  type: string
  stage: string | null
  payload: Record<string, any>
  timestamp: string
}

export interface ChatResponse {
  session_id: string
  run_id: string
  intent: string
  intent_reason: string
  decided_by: 'llm' | 'rule'
  message: string
  message_by: 'template' | 'llm'
  conditions: Record<string, any>
  clarify: boolean
  weather: Record<string, any> | null
  weather_policy: string[]
  recommendations: Recommendation[]
  excluded: { name: string; source: string; source_id: string; reason: string }[]
  criteria: string[]
  evidence: { seq: number; tool: string; label: string; ok: boolean; error_code: string | null; summary: string; duration_ms: number; reused: boolean }[]
  replans: { count: number; reason: string; strategy: string; detail: string }[]
  stop_reason: string | null
  suggestions: string[]
  notices: string[]
  disclaimer: string | null
  saved_plan: Plan | null
  plan_conflicts: Conflict[]
  more?: boolean
  events: RunEvent[]
  elapsed_ms: number
}

export interface Plan {
  id: number
  title: string
  plan_date: string
  start_time: string
  end_time: string
  area: Area | null
  restaurant_name: string
  restaurant_source: string | null
  restaurant_source_id: string | null
  restaurant_address: string | null
  cafe_name: string | null
  cafe_source: string | null
  cafe_source_id: string | null
  cafe_address: string | null
  cafe_url: string | null
  memo: string | null
  session_id: string | null
  created_at: string
  updated_at: string
}

export interface Conflict {
  id: number
  title: string
  plan_date: string
  start_time: string
  end_time: string
}

export interface Health {
  status: 'ok'
  api_keys: Record<string, boolean>
  llm: { available: boolean; provider: string; model: string | null; note: string | null }
  tools: string[]
  max_replans: number
}
