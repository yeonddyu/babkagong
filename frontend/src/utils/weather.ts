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

// 날씨 반응형 마스코트 상태. weatherMood 와 같은 기준을 쓰되, 비는 두 가지로 나눈다:
//   rain       : 예보의 강수형태(PTY)가 비·소나기 등 → "비 예보"
//   rain-maybe : 강수형태는 '없음'인데 강수확률만 기준 이상 → "비 올 수도" (실제로 온다는 뜻이 아님)
// 값은 모두 기상청 단기예보(방문 시각 예보)이며 실측이 아니다.
export type MascotState = 'idle' | 'neutral' | 'rain' | 'rain-maybe' | 'snow' | 'cold' | 'hot' | 'clear' | 'mild'

export function mascotState(w: Record<string, any> | null | undefined, hasResult: boolean): MascotState {
  if (!hasResult) return 'idle'
  const mood = weatherMood(w)
  if (!mood) return 'neutral'
  if (mood === 'rain') {
    const pty = w!.precipitation_type as string | null
    return pty && pty !== '없음' ? 'rain' : 'rain-maybe'
  }
  return mood === 'cloudy' ? 'mild' : mood
}

export function mascotLine(state: MascotState, w: Record<string, any> | null | undefined): string {
  const pop = w?.precipitation_probability as number | null | undefined
  switch (state) {
    case 'idle': return '어디서 먹을지 말해 주면, 그 시각 날씨도 같이 볼게요'
    case 'neutral': return '날씨 정보를 확인할 수 없어요'
    case 'rain': return `${w?.precipitation_type ?? '비'} 예보가 있어요. 우산 챙겨 가요!`
    case 'rain-maybe': return `강수확률 ${pop}%예요. 비가 올 수도 있어요`
    case 'snow': return '눈 예보가 있어요. 길 미끄러우니 조심해요!'
    case 'cold': return '쌀쌀한 예보예요. 따뜻한 국물 한 그릇 어때요?'
    case 'hot': return '더운 예보예요. 시원한 카페에서 쉬어 가요'
    case 'clear': return '맑은 예보예요. 밥 먹고 걷기 좋겠어요'
    case 'mild': return `${w?.sky ?? '구름'} 예보지만 다니기엔 무난해요`
  }
}
