// 날씨 분위기 판정 — 백엔드 정책(backend/app/agent/policy.py)과 같은 기준 (밥카공 초기 정책, 기상청 공식 기준 아님)
export const COLD_TEMP_C = 5
export const HOT_TEMP_C = 28
export const RAIN_POP_PERCENT = 60

export type Mood = 'rain' | 'snow' | 'cold' | 'hot' | 'clear' | 'cloudy'

export function weatherMood(w: Record<string, any> | null | undefined): Mood | null {
  if (!w) return null
  const pty = w.precipitation_type as string | null
  const pop = w.precipitation_probability as number | null
  const temp = w.temperature_c as number | null
  if (pty === '눈') return 'snow'
  if ((pty && pty !== '없음') || (pop != null && pop >= RAIN_POP_PERCENT)) return 'rain'
  if (temp != null && temp <= COLD_TEMP_C) return 'cold'
  if (temp != null && temp >= HOT_TEMP_C) return 'hot'
  if (w.sky === '맑음') return 'clear'
  if (w.sky == null && temp == null && pop == null) return null
  return 'cloudy'
}
