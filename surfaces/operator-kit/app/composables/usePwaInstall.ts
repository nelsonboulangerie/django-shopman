import { computed, onBeforeUnmount, onMounted, readonly, ref } from "vue";

import { isInstalledDisplay } from "../utils/displayMode";

const DEFAULT_DISMISS_DAYS = 7;

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

interface PwaInstallOptions {
  app?: string;
  dismissDays?: number;
  now?: () => number;
}

export function usePwaInstall(options: PwaInstallOptions = {}) {
  const now = options.now || Date.now;
  const dismissDays = Math.max(1, options.dismissDays ?? DEFAULT_DISMISS_DAYS);
  const storageKey = `shopman-${options.app || "operator"}-pwa-install-dismissed-until`;
  const deferredPrompt = ref<BeforeInstallPromptEvent | null>(null);
  const isStandalone = ref(false);
  const isIos = ref(false);
  const dismissedUntil = ref<number | null>(null);

  const isDismissed = computed(() => (dismissedUntil.value || 0) > now());
  const canInstall = computed(() => Boolean(deferredPrompt.value) && !isStandalone.value);

  function readEnvironment() {
    const ua = navigator.userAgent;
    isIos.value = /iPad|iPhone|iPod/.test(ua)
      || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    isStandalone.value = isInstalledDisplay();
    try {
      const stored = Number.parseInt(localStorage.getItem(storageKey) || "", 10);
      dismissedUntil.value = Number.isFinite(stored) ? stored : null;
    } catch {
      dismissedUntil.value = null;
    }
  }

  function dismiss() {
    const until = now() + dismissDays * 24 * 60 * 60 * 1_000;
    dismissedUntil.value = until;
    try {
      localStorage.setItem(storageKey, String(until));
    } catch {
      // A escolha permanece válida em memória quando a política bloqueia storage.
    }
  }

  function onBeforeInstallPrompt(event: Event) {
    event.preventDefault();
    deferredPrompt.value = event as BeforeInstallPromptEvent;
  }

  function onAppInstalled() {
    deferredPrompt.value = null;
    isStandalone.value = true;
  }

  async function install(): Promise<boolean> {
    const prompt = deferredPrompt.value;
    if (!prompt) return false;
    try {
      await prompt.prompt();
      const choice = await prompt.userChoice;
      deferredPrompt.value = null;
      if (choice.outcome === "accepted") isStandalone.value = true;
      return choice.outcome === "accepted";
    } catch {
      deferredPrompt.value = null;
      return false;
    }
  }

  onMounted(() => {
    readEnvironment();
    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onAppInstalled);
  });

  onBeforeUnmount(() => {
    window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.removeEventListener("appinstalled", onAppInstalled);
  });

  return {
    canInstall,
    install,
    isStandalone: readonly(isStandalone),
    isIos: readonly(isIos),
    dismissedUntil: readonly(dismissedUntil),
    isDismissed,
    dismiss,
  };
}
