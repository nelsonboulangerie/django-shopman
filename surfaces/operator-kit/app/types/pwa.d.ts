declare module "virtual:pwa-register/vue" {
  import type { Ref } from "vue";

  export function useRegisterSW(options?: { immediate?: boolean }): {
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
