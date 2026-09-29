import { computed, onBeforeUnmount, onMounted, readonly, ref } from "vue";

import { isInstalledDisplay } from "../utils/displayMode";
import { installPlan, readInstallEnvironment, type InstallEnvironment, type InstallPlan } from "../utils/installGuide";

/** Quanto tempo o "Agora não" segura o convite. Uma semana é o intervalo de um turno. */
const DEFAULT_DISMISS_DAYS = 7;
/** "Já instalei" é resposta definitiva; o convite não volta a interromper por um ano. */
const DONE_DISMISS_DAYS = 365;

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
}

interface PwaInstallOptions {
  app?: string;
  dismissDays?: number;
  now?: () => number;
  /** Ambiente cravado — existe para o teste cobrar um navegador sem ter um navegador. */
  environment?: InstallEnvironment;
}

export function usePwaInstall(options: PwaInstallOptions = {}) {
  const now = options.now || Date.now;
  const dismissDays = Math.max(1, options.dismissDays ?? DEFAULT_DISMISS_DAYS);
  const storageKey = `shopman-${options.app || "operator"}-pwa-install-dismissed-until`;
  const deferredPrompt = ref<BeforeInstallPromptEvent | null>(null);
  const isStandalone = ref(false);
  const dismissedUntil = ref<number | null>(null);
  const environment = ref<InstallEnvironment | null>(options.environment || null);

  const isDismissed = computed(() => (dismissedUntil.value || 0) > now());

  /**
   * O caminho real deste navegador. Enquanto o ambiente não foi lido (servidor, antes
   * do mount) o plano é `none`: o convite não pisca com uma instrução provisória.
   */
  const plan = computed<InstallPlan>(() => {
    const env = environment.value;
    if (!env) return { kind: "none", invite: false, steps: [], os: "unknown", browser: "unknown" };
    return installPlan({ ...env, canPrompt: Boolean(deferredPrompt.value) });
  });

  /** O convite sobe sozinho? Só com caminho acionável, fora do app já instalado. */
  const canInvite = computed(() => plan.value.invite && !isStandalone.value && !isDismissed.value);

  function readEnvironment() {
    environment.value = options.environment || readInstallEnvironment(Boolean(deferredPrompt.value));
    isStandalone.value = isInstalledDisplay();
    try {
      const stored = Number.parseInt(localStorage.getItem(storageKey) || "", 10);
      dismissedUntil.value = Number.isFinite(stored) ? stored : null;
    } catch {
      dismissedUntil.value = null;
    }
  }

  function dismiss(days: number = dismissDays) {
    const until = now() + Math.max(1, days) * 24 * 60 * 60 * 1_000;
    dismissedUntil.value = until;
    try {
      localStorage.setItem(storageKey, String(until));
    } catch {
      // A escolha permanece válida em memória quando a política bloqueia storage.
    }
  }

  /** "Já instalei" — quem seguiu os passos não é interrompido de novo na semana seguinte. */
  function dismissAsDone() {
    dismiss(DONE_DISMISS_DAYS);
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
    plan,
    canInvite,
    install,
    isStandalone: readonly(isStandalone),
    dismissedUntil: readonly(dismissedUntil),
    isDismissed,
    dismiss,
    dismissAsDone,
  };
}
