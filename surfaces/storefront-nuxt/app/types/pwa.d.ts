declare module 'virtual:pwa-register/vue' {
  import type { Ref } from 'vue'

  export function useRegisterSW(options?: { immediate?: boolean }): {
    needRefresh: Ref<boolean>
    offlineReady: Ref<boolean>
    updateServiceWorker: (reloadPage?: boolean) => Promise<void>
  }
}
