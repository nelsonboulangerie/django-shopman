import { onBeforeUnmount, onMounted, watch, type Ref } from "vue";

import { isIdleBeyond } from "~/utils/operatorLock";

const ACTIVITY_KEY = "shopman:pos:last-activity";
const LOCK_NAME = "shopman:pos:auto-lock";

/** O documento está fora da vista (aba em segundo plano, PWA minimizado)? */
function pageHidden(): boolean {
  try {
    return typeof document !== "undefined" && document.visibilityState === "hidden";
  } catch {
    return false;
  }
}

/**
 * O timer pertence à estação: uma aba ociosa não derruba outra em atendimento.
 *
 * Travar é `logout()` da sessão de operador, e essa sessão é UMA só para todos os
 * apps do domínio-pai (Gestor, KDS, Central, Produção…) no mesmo navegador. A
 * ociosidade, porém, só é medida pelo que acontece no PDV. Por isso o cadeado não
 * dispara com o PDV fora da vista: uma aba esquecida em segundo plano derrubava,
 * a cada minuto, o Gestor em uso ativo ao lado. A proteção do próprio PDV não
 * afrouxa — no instante em que ele volta à vista, antes de qualquer toque, a
 * ociosidade é conferida e o cadeado desce se o prazo passou.
 */
export function usePosAutoLock(opts: {
  locked: Ref<boolean>;
  lock: () => void | Promise<void>;
  autoLockSeconds: () => number;
  /** Checkout ou Pix em curso renova a atividade compartilhada entre abas. */
  holdWhen?: () => boolean;
}) {
  let lastActivity = Date.now();
  let lastPublished = 0;
  let cleanup: (() => void) | null = null;

  function sharedActivity(): number {
    try {
      const value = Number(window.localStorage.getItem(ACTIVITY_KEY));
      // Relógio ajustado para trás não deve desativar o cadeado para sempre.
      if (Number.isFinite(value) && value > 0 && value <= Date.now()) lastActivity = Math.max(lastActivity, value);
    } catch { /* Storage indisponível: o timer local continua protegendo a estação. */ }
    return lastActivity;
  }

  function markActivity(force = false) {
    lastActivity = Date.now();
    // Pointermove pode disparar dezenas de vezes por segundo. Um segundo é
    // suficiente para compartilhar atividade com o timer, que roda a cada cinco.
    if (!force && lastActivity - lastPublished < 1000) return;
    try {
      window.localStorage.setItem(ACTIVITY_KEY, String(lastActivity));
      lastPublished = lastActivity;
    } catch { /* Navegação sem storage mantém o timer local. */ }
  }

  async function lockIfIdle() {
    if (opts.locked.value || opts.holdWhen?.() || pageHidden()) return;
    if (!isIdleBeyond(sharedActivity(), Date.now(), opts.autoLockSeconds() ?? 60)) return;
    // Reancora antes do POST: outra aba que adquirir a trava logo depois não
    // repete o logout enquanto a leitura da sessão ainda está sendo renovada.
    markActivity(true);
    await opts.lock();
  }

  function checkIdle() {
    if (opts.holdWhen?.()) {
      markActivity(true);
      return;
    }
    if (pageHidden()) return;
    if (opts.locked.value || !isIdleBeyond(sharedActivity(), Date.now(), opts.autoLockSeconds() ?? 60)) return;
    // Web Locks serializa abas em processos diferentes. Sem a API, reler e
    // publicar antes do POST ainda evita duplicações no caso habitual.
    if (navigator.locks?.request) {
      void navigator.locks.request(LOCK_NAME, { ifAvailable: true }, async (lock) => {
        if (lock) await lockIfIdle();
      }).catch(() => lockIfIdle());
    } else {
      void lockIfIdle();
    }
  }

  onMounted(() => {
    markActivity(true);
    const onActivity = () => markActivity();
    const events: Array<keyof WindowEventMap> = ["pointerdown", "keydown", "wheel", "pointermove"];
    events.forEach((event) => window.addEventListener(event, onActivity, { passive: true }));
    const stopWatch = watch(opts.locked, (locked, wasLocked) => {
      if (!locked && wasLocked) markActivity(true);
    });
    // Voltou à vista: confere já, sem esperar o próximo tique de 5 s — o primeiro
    // toque ao retornar não pode renovar a atividade de uma estação já vencida.
    const onVisibility = () => { if (!pageHidden()) checkIdle(); };
    document.addEventListener("visibilitychange", onVisibility);
    const id = window.setInterval(checkIdle, 5000);
    cleanup = () => {
      events.forEach((event) => window.removeEventListener(event, onActivity));
      document.removeEventListener("visibilitychange", onVisibility);
      window.clearInterval(id);
      stopWatch();
    };
  });

  onBeforeUnmount(() => cleanup?.());
}
