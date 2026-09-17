import { onBeforeUnmount, onMounted, watch, type Ref } from "vue";

import { deviceActivityClock } from "../../../operator-kit/app/utils/deviceActivity";
import { isIdleBeyond } from "~/utils/operatorLock";

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
 * O PDV trava pela ociosidade do APARELHO, não pela dele.
 *
 * Travar é `logout()` da sessão de operador, e essa sessão é UMA só para todos os
 * apps do domínio-pai (Gestor, KDS, Central, Produção…) no mesmo navegador. Medir
 * só o que acontece no PDV derrubava o Gestor em uso ao lado a cada minuto. A regra
 * (decisão do Pablo, 17/09/2026): trava só quando NENHUM app de operador foi tocado
 * por `auto_lock_seconds`. O "último toque" é o maior entre a atividade local e o
 * relógio do aparelho (`operator-kit/app/utils/deviceActivity.ts`), cookie no
 * domínio-pai que todo app do kit alimenta — e que também coordena abas do PDV.
 *
 * Com o PDV fora da vista o cadeado não dispara (aba esquecida não derruba
 * ninguém); no instante em que ele volta à vista, antes de qualquer toque, a
 * ociosidade do aparelho é conferida e o cadeado desce se o prazo passou.
 */
export function usePosAutoLock(opts: {
  locked: Ref<boolean>;
  lock: () => void | Promise<void>;
  autoLockSeconds: () => number;
  /** Checkout ou Pix em curso renova a atividade compartilhada entre abas. */
  holdWhen?: () => boolean;
}) {
  let lastActivity = Date.now();
  let cleanup: (() => void) | null = null;

  function sharedActivity(): number {
    // O relógio já ignora instante no futuro: relógio forjado ou ajustado para
    // trás não desliga o cadeado para sempre. Sem cookie, vale a atividade local.
    const device = deviceActivityClock()?.read();
    if (device) lastActivity = Math.max(lastActivity, device);
    return lastActivity;
  }

  function markActivity(force = false) {
    lastActivity = Date.now();
    // O throttle mora no relógio (5 s entre escritas, contra um limiar de 60 s):
    // pointermove em rajada não reescreve o cookie a cada evento.
    deviceActivityClock()?.mark(force);
  }

  async function lockIfIdle() {
    if (opts.locked.value || opts.holdWhen?.() || pageHidden()) return;
    if (!isIdleBeyond(sharedActivity(), Date.now(), opts.autoLockSeconds() ?? 60)) return;
    // Reancora o aparelho antes do POST: outra aba que adquirir a trava logo
    // depois não repete o logout enquanto a leitura da sessão é renovada.
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
