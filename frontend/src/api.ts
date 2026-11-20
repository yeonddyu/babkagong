// 백엔드 API 호출. 오류는 사용자에게 보여줄 수 있는 문장만 노출한다 (NF3002).
import type { Area, ChatResponse, Conflict, Health, Plan, RunEvent, StationItem } from './types'

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...init })
  } catch {
    throw new ApiError(0, 'NETWORK', '서버에 연결할 수 없어요. 백엔드가 실행 중인지 확인해 주세요.')
  }
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    const detail = body?.detail
    const message = typeof detail?.message === 'string' ? detail.message : '요청을 처리하지 못했어요.'
    throw new ApiError(res.status, detail?.code ?? 'ERROR', message)
  }
  return body as T
}

// F3019: 실행 이벤트를 실시간으로 받는 SSE 스트림 (POST 라 EventSource 대신 fetch 스트림으로 읽음)
async function chatStream(message: string, sessionId: string | null, area: Area | null,
                          onProgress: (e: RunEvent) => void): Promise<ChatResponse> {
  let res: Response
  try {
    res = await fetch('/api/chat/stream', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ message, session_id: sessionId, area }) })
  } catch {
    throw new ApiError(0, 'NETWORK', '서버에 연결할 수 없어요. 백엔드가 실행 중인지 확인해 주세요.')
  }
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null)
    throw new ApiError(res.status, body?.detail?.code ?? 'ERROR', body?.detail?.message ?? '요청을 처리하지 못했어요.')
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })
    let idx
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, idx)
      buffer = buffer.slice(idx + 2)
      const event = /^event: (.*)$/m.exec(block)?.[1]
      const data = JSON.parse(/^data: (.*)$/m.exec(block)?.[1] ?? 'null')
      if (event === 'progress') onProgress(data as RunEvent)
      else if (event === 'result') return data as ChatResponse
      else if (event === 'error') throw new ApiError(500, data?.code ?? 'ERROR', data?.message ?? '요청을 처리하지 못했어요.')
    }
    if (done) throw new ApiError(0, 'STREAM', '응답이 중간에 끊겼어요. 다시 시도해 주세요.')
  }
}

export const api = {
  chatStream,
  health: () => request<Health>('/api/health'),
  stations: () => request<{ stations: StationItem[]; complete: boolean }>('/api/stations'),
  chat: (message: string, sessionId: string | null, area: Area | null) =>
    request<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_id: sessionId, area }),
    }),
  listPlans: (date?: string) => request<{ plans: Plan[] }>(`/api/plans${date ? `?date=${date}` : ''}`),
  getPlan: (id: number) => request<Plan>(`/api/plans/${id}`),
  createPlan: (data: Partial<Plan>) =>
    request<{ plan: Plan; conflicts: Conflict[] }>('/api/plans', { method: 'POST', body: JSON.stringify(data) }),
  updatePlan: (id: number, data: Partial<Plan>) =>
    request<{ plan: Plan; conflicts: Conflict[] }>(`/api/plans/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deletePlan: (id: number) => request<{ deleted: boolean }>(`/api/plans/${id}`, { method: 'DELETE' }),
}
