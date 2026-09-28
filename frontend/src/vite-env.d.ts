/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  /** "true" enables the local-only X-Demo-User identity (dev server only). */
  readonly VITE_DEMO_AUTH?: string
  /** Default demo user key: asha | ravi | meera | buyer | supplier. */
  readonly VITE_DEMO_USER?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
