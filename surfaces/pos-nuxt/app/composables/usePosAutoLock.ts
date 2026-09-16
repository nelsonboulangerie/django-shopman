import { onBeforeUnmount, onMounted, watch, type Ref } from "vue";

import { isIdleBeyond } from "~/utils/operatorLock";

const ACTIVITY_KEY = "shopman:pos:last-activity";
const LOCK_NAME = "shopman:pos:auto-lock";

/** O timer pertence à estação: uma aba ociosa não derruba outra em atendimento. */
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
    if (opts.locked.value || opts.holdWhen?.()) return;
    if (!isIdleBeyond(sharedActivity(), Date.now(), opts.autoLockSeconds() ?? 60)) return;
    // Reancora antes do POST: outra aba que adquirir a trava logo depois não
    // repete o logout enquanto a leitura da sessão ainda está sendo renovada.
    markActivity(true);
    await opts.lock();
  }

  onMounted(() => {
    markActivity(true);
    const onActivity = () => markActivity();
    const events: Array<keyof WindowEventMap> = ["pointerdown", "keydown", "wheel", "pointermove"];
    events.forEach((event) => window.addEventListener(event, onActivity, { passive: true }));
    const stopWatch = watch(opts.locked, (locked, wasLocked) => {
      if (!locked && wasLocked) markActivity(true);
    });
    const id = window.setInterval(() => {
      if (opts.holdWhen?.()) {
        markActivity(true);
        return;
      }
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
    }, 5000);
    cleanup = () => {
      events.forEach((event) => window.removeEventListener(event, onActivity));
      window.clearInterval(id);
      stopWatch();
    };
  });

  onBeforeUnmount(() => cleanup?.());
}
