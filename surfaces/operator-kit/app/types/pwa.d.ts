declare module "virtual:pwa-register/vue" {
  import type { Ref } from "vue";

  export function useRegisterSW(options?: {
    immediate?: boolean;
    /**
     * Chamado com o `ServiceWorkerRegistration` assim que o registro conclui. É o
     * único caminho para `registration.update()` — a sonda que descobre versão nova
     * sem depender de navegação de documento.
     */
    onRegisteredSW?: (swScriptUrl: string, registration: ServiceWorkerRegistration | undefined) => void;
  }): {
    needRefresh: Ref<boolean>;
    offlineReady: Ref<boolean>;
    updateServiceWorker: (reloadPage?: boolean) => Promise<void>;
  };
}

interface Navigator {
  clearAppBadge?: () => Promise<void>;
  setAppBadge?: (contents?: number) => Promise<void>;
  userAgentData?: { platform?: string };
}
