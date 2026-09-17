import { computed, onBeforeUnmount, onMounted, readonly, ref, watch, type Ref } from "vue";

import {
  applyIdleUpdate,
  idleUpdateBlocker,
  shouldCheckForUpdate,
  idleReloadPathAllowed,
  PWA_UPDATE_CHECK_MS,
  PWA_UPDATE_IDLE_MS,
} from "../presentation/pwaRuntime";
import {
  markPwaUpdateApplied,
  reportPwaUpdateApplied,
  type PwaUpdateReport,
} from "../utils/pwaUpdateReport";
import { usePwaUpdate } from "./usePwaUpdate";

/** Toque humano: o mesmo vocabulário do auto-lock do PDV e do kiosk. */
const ACTIVITY_EVENTS = ["pointerdown", "pointermove", "keydown", "wheel", "touchstart"] as const;

export interface PwaAutoUpdateOptions {
  /** Identidade do app no log (`operatorPwa.app`): pos, kds, production… */
  app: string;
  /** Versão rodando AGORA (`public.appVersion`), para o relatório nomear as duas pontas. */
  appVersion: string;
  /** Rotas em que recarregar sozinho é seguro. Vazio = só o aviso, nunca automático. */
  allowedPaths: () => readonly string[];
  /** Caminho atual da superfície. */
  path: () => string;
  /** Razões publicadas pela tela para não recarregar agora (`useOperatorReloadHold`). */
  holds?: () => readonly string[];
  enabled?: boolean;
  idleMs?: number;
  checkIntervalMs?: number;
  /** Fronteira de rede, injetável no teste. */
  report?: (toVersion: string) => Promise<PwaUpdateReport | null>;
}

/**
 * SONDAR e APLICAR a versão nova do app instalado, sem interromper operação.
 *
 * Sondar: `registration.update()` a cada 30 min e ao voltar do segundo plano / ganhar
 * foco / reconectar. Sem isso o navegador só procura `sw.js` novo em navegação de
 * documento, e o PDV instalado no desktop passou dias com o bundle de antes dos
 * deploys de 17/09 (#783, #789) porque ninguém nunca fechou a janela.
 *
 * Aplicar: só quando a superfície prova que é seguro — rota na lista do app, nenhuma
 * razão de `useOperatorReloadHold` de pé (no PDV: venda, pagamento ou comanda aberta)
 * e ociosidade de verdade. Enquanto não for seguro, quem decide é o operador pelo
 * aviso (`OperatorPwaUpdatePrompt`), que segue no ar exatamente como antes.
 */
export function usePwaAutoUpdate(options: PwaAutoUpdateOptions) {
  const enabled = options.enabled !== false;
  const idleMs = Math.max(1_000, options.idleMs ?? PWA_UPDATE_IDLE_MS);
  const checkIntervalMs = Math.max(60_000, options.checkIntervalMs ?? PWA_UPDATE_CHECK_MS);
  const holdsOf = options.holds || (() => []);
  const report = options.report || ((toVersion: string) => reportPwaUpdateApplied(toVersion));

  const pwa = usePwaUpdate();
  const applying = ref(false);
  const idle = ref(false);
  const lastCheckAt = ref(0);
  const lastReport = ref<PwaUpdateReport | null>(null);

  const holds = computed(() => holdsOf());
  const path = computed(() => options.path());
  const allowedPaths = computed(() => options.allowedPaths());
  const safeToReload = computed(() => idleReloadPathAllowed(allowedPaths.value, path.value));
  /** Por que a versão em espera ainda não entrou — texto do relatório, não da tela. */
  const blocker = computed(() => idleUpdateBlocker({
    idle: idle.value,
    needsRefresh: pwa.needRefresh.value,
    applying: applying.value,
    safeToReload: safeToReload.value,
    holds: holds.value,
  }));

  let idleTimer: ReturnType<typeof setTimeout> | null = null;
  let checkTimer: ReturnType<typeof setInterval> | null = null;
  let cleanup: (() => void) | null = null;

  function visible(): boolean {
    try {
      return typeof document === "undefined" || document.visibilityState !== "hidden";
    } catch {
      return true;
    }
  }

  function online(): boolean {
    try {
      return typeof navigator === "undefined" || navigator.onLine !== false;
    } catch {
      return true;
    }
  }

  /** Sonda o servidor, respeitando o piso entre chamadas. `force` pula o piso. */
  async function checkNow(force = false): Promise<boolean> {
    if (!enabled) return false;
    const now = Date.now();
    if (!force && !shouldCheckForUpdate({ now, lastCheckAt: lastCheckAt.value, online: online(), visible: visible() })) {
      return false;
    }
    lastCheckAt.value = now;
    return pwa.checkForUpdate();
  }

  async function applyNow(): Promise<boolean> {
    return applyIdleUpdate({
      allowedPaths: allowedPaths.value,
      path: path.value,
      idle: idle.value,
      needsRefresh: pwa.needRefresh.value,
      applying: applying.value,
      holds: holds.value,
    }, async () => {
      applying.value = true;
      // A marca vai ao disco ANTES do reload: depois dele não existe mais este
      // processo para contar que a troca aconteceu.
      markPwaUpdateApplied({ app: options.app, trigger: "idle", from_version: options.appVersion });
      const accepted = await pwa.update();
      if (!accepted) applying.value = false;
      return accepted;
    });
  }

  function clearIdleTimer() {
    if (idleTimer) clearTimeout(idleTimer);
    idleTimer = null;
  }

  function markActive() {
    if (!enabled) return;
    clearIdleTimer();
    idle.value = false;
    idleTimer = setTimeout(() => {
      idle.value = true;
      void applyNow();
    }, idleMs);
  }

  onMounted(() => {
    // O boot depois da troca é o único momento em que as DUAS versões são
    // conhecidas — a de antes veio do disco, a de agora é esta. Relata e apaga.
    void report(options.appVersion).then((sent) => {
      lastReport.value = sent;
    }).catch(() => {});

    if (!enabled) return;
    for (const event of ACTIVITY_EVENTS) window.addEventListener(event, markActive, { passive: true });
    // Voltar do segundo plano é o gatilho que importa no desktop do dono: a janela
    // fica dias aberta e só é olhada de novo quando alguém troca de app.
    const onVisibility = () => { if (visible()) void checkNow(); };
    const onFocus = () => void checkNow();
    const onOnline = () => void checkNow(true);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("focus", onFocus);
    window.addEventListener("online", onOnline);
    checkTimer = setInterval(() => void checkNow(true), checkIntervalMs);
    markActive();
    // Sonda de boot: o app que acabou de abrir pergunta uma vez, sem esperar 30 min.
    void checkNow(true);

    cleanup = () => {
      for (const event of ACTIVITY_EVENTS) window.removeEventListener(event, markActive);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("online", onOnline);
      if (checkTimer) clearInterval(checkTimer);
      checkTimer = null;
      clearIdleTimer();
    };
  });

  onBeforeUnmount(() => cleanup?.());

  // O worker pode terminar de baixar com a superfície JÁ ociosa (kiosk parado), e aí
  // não há próximo evento de atividade para disparar o callback. A tela também pode
  // largar a última razão de hold sem ninguém tocar em nada. Esta observação fecha
  // as duas janelas.
  watch(
    [pwa.needRefresh, holds, safeToReload, idle] as const,
    () => void applyNow(),
    { flush: "post" },
  );

  return {
    needRefresh: pwa.needRefresh,
    applying: readonly(applying) as Readonly<Ref<boolean>>,
    idle: readonly(idle) as Readonly<Ref<boolean>>,
    blocker,
    lastCheckAt: readonly(lastCheckAt) as Readonly<Ref<number>>,
    lastReport: readonly(lastReport) as Readonly<Ref<PwaUpdateReport | null>>,
    checkNow,
    applyNow,
    markActive,
  };
}
