/// <reference types="vite/client" />
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, any>
  export default component
}

interface ImportMetaEnv {
  readonly VITE_KAKAO_MAP_KEY?: string
  readonly VITE_KAKAO_JS_KEY?: string
}
interface ImportMeta {
  readonly env: ImportMetaEnv
}
