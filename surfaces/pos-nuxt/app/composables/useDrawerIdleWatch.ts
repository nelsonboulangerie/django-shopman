import type { ComputedRef } from "vue";

import type { DrawerState } from "~/composables/useCounterAgent";
import type { Action } from "~/types/pos";
import { actionHref } from "~/utils/posIntent";

interface DrawerIdleWatchDeps {
  drawer: { canKick: ComputedRef<boolean>; readState: () => Promise<DrawerState> };
  actions: ComputedRef<Action[]>;
  action: {
    call: <T = unknown>(path: string, opts?: { body?: Record<string, unknown> }) => Promise<T>;
  };
  /** Minutos até virar aviso. `0` desliga. Vem da projeção (regra do dono). */
  minutes: ComputedRef<number>;
  /** A trava já está na tela? Então quem cuida da gaveta é ela, não isto. */
  blocked: ComputedRef<boolean>;
}

/**
 * Cadência calma, de propósito. A trava resolve o instante da venda em 400ms;
 * aqui o alvo é a hora morta, e um minuto de atraso num aviso de "a gaveta está
 * aberta há 3 minutos" não muda nada. Sondar rápido só gastaria bateria e
 * encheria o log da estação.
 */
const IDLE_POLL_MS = 60_000;

/**
 * O olho da hora morta.
 *
 * A trava dura resolve o momento da venda: com a gaveta aberta, o balcão não
 * anda. Mas ela só age quando **alguém tenta vender** — e é justamente na hora
 * sem movimento que uma gaveta aberta passa despercebida. Sem isto, dava para
 * deixar a gaveta aberta a tarde inteira e só encontrar a trava na próxima
 * venda, que talvez só viesse muito depois.
 *
 * Não trava nada, e isso é decisão: o balcão parado não tem fila para atender,
 * mas também não tem ninguém olhando a tela — travar aqui só produziria um PDV
 * travado que ninguém vê. O produto é o aviso ao gerente e a linha no livro.
 *
 * Um episódio rende UM aviso. A contagem zera quando a gaveta fecha, e só então
 * um novo episódio pode avisar de novo — senão o mesmo esquecimento viraria um
 * alerta por minuto e o gerente aprenderia a ignorar todos.
 */
export function useDrawerIdleWatch({ drawer, actions, action, minutes, blocked }: DrawerIdleWatchDeps) {
  let openSince = 0;
  let reported = false;
  let timer: ReturnType<typeof setInterval> | null = null;

  async function tick(): Promise<void> {
    if (!import.meta.client || !drawer.canKick.value) return;
    const limit = minutes.value;
    if (limit <= 0) return;
    // Com a trava na tela, o episódio já tem dono (e já é medido em ms lá).
    if (blocked.value) return;

    const state = await drawer.readState();
    if (!state.known || !state.open) {
      openSince = 0;
      reported = false;
      return;
    }
    if (!openSince) {
      openSince = Date.now();
      return;
    }
    if (reported) return;
    const elapsedMin = Math.floor((Date.now() - openSince) / 60_000);
    if (elapsedMin < limit) return;
    reported = true;
    try {
      await action.call(
        actionHref(actions.value, "drawer_left_open", "/api/v1/backstage/pos/cash/drawer-left-open/"),
        { body: { minutes: elapsedMin } },
      );
    } catch {
      // Aviso que não saiu não pode derrubar a tela do balcão.
    }
  }

  onMounted(() => {
    timer = setInterval(() => void tick(), IDLE_POLL_MS);
  });
  onBeforeUnmount(() => {
    if (timer) clearInterval(timer);
    timer = null;
  });

  return { tick };
}
