// 카카오 지도 JavaScript SDK 로더. 키(VITE_KAKAO_MAP_KEY)는 브라우저에 노출되는 공개용 키이며
// 카카오 앱의 Web 플랫폼에 등록된 도메인에서만 동작한다. 키가 없거나 로딩에 실패하면 null.
/* eslint-disable @typescript-eslint/no-explicit-any */

let loading: Promise<any | null> | null = null

export function kakaoMapKey(): string | undefined {
  // 지시서 예시 이름(VITE_KAKAO_JS_KEY)과 기존 이름(VITE_KAKAO_MAP_KEY) 모두 허용
  const key = (import.meta.env.VITE_KAKAO_MAP_KEY || import.meta.env.VITE_KAKAO_JS_KEY) as string | undefined
  return key && key.trim() ? key.trim() : undefined
}

export function loadKakaoMaps(timeoutMs = 8000): Promise<any | null> {
  const w = window as any
  if (w.kakao?.maps?.LatLng) return Promise.resolve(w.kakao)
  const key = kakaoMapKey()
  if (!key) return Promise.resolve(null)
  if (loading) return loading
  loading = new Promise((resolve) => {
    const timer = setTimeout(() => resolve(null), timeoutMs)
    const script = document.createElement('script')
    script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(key)}&autoload=false`
    script.async = true
    script.onload = () => {
      try {
        w.kakao.maps.load(() => { clearTimeout(timer); resolve(w.kakao) })
      } catch {
        clearTimeout(timer)
        resolve(null)
      }
    }
    script.onerror = () => { clearTimeout(timer); resolve(null) }
    document.head.appendChild(script)
  })
  return loading
}

/** 두 좌표의 직선거리(m) */
export function haversineM(a: [number, number], b: [number, number]): number {
  const R = 6371008.8
  const rad = Math.PI / 180
  const dLat = (b[0] - a[0]) * rad
  const dLng = (b[1] - a[1]) * rad
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

// 응답에 기준점(origin)이 없을 때 쓰는 기본 두 역 좌표 (백엔드 app/datasets/stations.py BUILTIN 과 같은 값)
export const STATIONS: Record<string, [number, number]> = {
  강남역: [37.497952, 127.027619],
  역삼역: [37.500622, 127.036456],
}
