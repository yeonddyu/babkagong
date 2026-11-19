// 백엔드 API 호출. 오류는 사용자에게 보여줄 수 있는 문장만 노출한다 (NF3002).
import type { Area, ChatResponse, Conflict, Health, Plan } from './types'

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

export const api = {
  health: () => request<Health>('/api/health'),
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
