/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { loadEnv, type Plugin } from 'vite'
import { fileURLToPath } from 'node:url'

/** 저장소 루트 .env 의 VITE_ 변수를 process.env 로 넘겨 Vite 가 읽게 한다 (frontend/.env.local·실제 환경변수가 우선) */
function rootEnv(): Plugin {
  return {
    name: 'babkagong-root-env',
    config(_, { mode }) {
      if (process.env.VITEST) return // 테스트는 실제 .env 에 의존하지 않는다
      const root = fileURLToPath(new URL('..', import.meta.url))
      const local = loadEnv(mode, fileURLToPath(new URL('.', import.meta.url)), 'VITE_')
      for (const [k, v] of Object.entries(loadEnv(mode, root, 'VITE_'))) {
        if (!(k in local) && process.env[k] === undefined) process.env[k] = v
      }
    },
  }
}

// 개발 서버는 /api 요청을 FastAPI(8000)로 넘긴다.
// env 는 저장소 루트(.env)와 frontend(.env.local) 를 모두 읽는다. Vite 는 VITE_ 로 시작하는 변수만
// 브라우저 코드에 넘기므로 루트 .env 의 다른 API 키는 노출되지 않는다.
export default defineConfig({
  plugins: [vue(), rootEnv()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.spec.ts'],
  },
})
