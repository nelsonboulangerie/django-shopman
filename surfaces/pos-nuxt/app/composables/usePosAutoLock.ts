import { onBeforeUnmount, onMounted, type Ref } from "vue";

import { isIdleBeyond } from "~/utils/operatorLock";

/**
 * Auto-lock por ociosidade — específico do PDV (kiosk de balcão compartilhado): se
 * ninguém toca a tela por `autoLockSeconds`, o operador ativo é derrubado e a tela
 * de identificação sobe. Os demais apps de operador (KDS/Gestor/Produção) são estações
 * de um operador só e não auto-travam, por isso isto vive no PDV e não no kit.
 *
 * Fica separado do lock compartilhado (`useOperatorLock`): a identificação em si
 * (PIN/crachá) é a mesma dos outros apps; só o timer de kiosk é do PDV.
 */
export function usePosAutoLock(opts: {
  locked: Ref<boolean>;
  lock: () => void | Promise<void>;
  autoLockSeconds: () => number;
}) {
  let lastActivity = Date.now();
  let cleanup: (() => void) | null = null;

  function markActivity() {
    lastActivity = Date.now();
  }

  onMounted(() => {
    // O PDV é desktop-first: rolar a grade de produtos com a rodinha do mouse é
    // trabalho, não ociosidade. Com só `pointerdown`/`keydown`, o operador que
    // procurava um item rolando a lista via a tela travar na cara dele no meio
    // da venda. `wheel` e `pointermove` fecham esse buraco.
    const events: Array<keyof WindowEventMap> = ["pointerdown", "keydown", "wheel", "pointermove"];
    events.forEach((e) => window.addEventListener(e, markActivity, { passive: true }));
    const id = window.setInterval(() => {
      if (!opts.locked.value && isIdleBeyond(lastActivity, Date.now(), opts.autoLockSeconds() ?? 60)) {
        lastActivity = Date.now(); // evita reentrância enquanto o lock propaga
        opts.lock();
      }
    }, 5000);
    cleanup = () => {
      events.forEach((e) => window.removeEventListener(e, markActivity));
      window.clearInterval(id);
    };
  });

  onBeforeUnmount(() => cleanup?.());
}
