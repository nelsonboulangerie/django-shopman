import { computed, ref } from "vue";

export interface PendingActionOptions<Args extends unknown[]> {
  /** Trava por chave (uma linha, um pedido) em vez de uma trava só. */
  key?: (...args: Args) => string;
}

/**
 * Clique nunca inerte — todo botão de ação assíncrona declara que está em andamento.
 *
 * Contrato na seção "Clique nunca inerte" do README do kit. A loja tem cópia
 * espelhada (`storefront-nuxt/app/composables/usePendingAction.ts`).
 *
 * - `pending` fica verdadeiro do clique até a promessa assentar (sucesso ou erro).
 *   O botão mostra isso (`aria-busy`, spinner `line-md:loading-loop`, que é
 *   empacotado) e fica desabilitado SÓ durante o pendente.
 * - Toque repetido enquanto pende é ignorado (devolve `undefined`): a ação nunca
 *   dispara duas vezes. Com `key`, a trava é por chave.
 * - O erro sobe para quem chamou, como sem o composable.
 */
export function usePendingAction<Args extends unknown[], Result>(
  action: (...args: Args) => Promise<Result> | Result,
  options: PendingActionOptions<Args> = {},
) {
  const running = ref<string[]>([]);
  const pending = computed(() => running.value.length > 0);

  function isPending(key = ""): boolean {
    return running.value.includes(key);
  }

  async function run(...args: Args): Promise<Result | undefined> {
    const key = options.key ? options.key(...args) : "";
    if (running.value.includes(key)) return undefined;
    running.value = [...running.value, key];
    try {
      return await action(...args);
    } finally {
      running.value = running.value.filter((item) => item !== key);
    }
  }

  return { run, pending, isPending };
}
