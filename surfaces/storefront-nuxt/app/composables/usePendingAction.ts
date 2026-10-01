import { computed, ref } from 'vue'

// Clique nunca inerte: todo botão de ação assíncrona declara que está em andamento.
//
// Espelho de `surfaces/operator-kit/app/composables/usePendingAction.ts` (a loja não
// estende a layer dos operadores; o padrão da casa é espelhar, como `useNextFocus`).
// Contrato na seção "Clique nunca inerte" do `surfaces/operator-kit/README.md`.
//
//   const { run: removeLine, isPending: removingLine } =
//     usePendingAction(removeLineNow, { key: line => line.sku })
//   <UiButton :loading="removingLine(line.sku)" @click="removeLine(line)" />
//
// - `pending` fica verdadeiro do clique até a promessa assentar (com sucesso ou
//   erro). O botão mostra isso com `:loading` (spinner empacotado, `aria-busy`) e
//   fica desabilitado SÓ durante o pendente.
// - Toque repetido enquanto pende é ignorado (devolve `undefined`), nunca dispara a
//   ação duas vezes. Com `key`, a trava é por chave: remover a linha A não trava a B.
// - O erro sobe para quem chamou, como sem o composable: aviso de erro é da ação.

export interface PendingActionOptions<Args extends unknown[]> {
  /** Trava por chave (uma linha, um pedido) em vez de uma trava só. */
  key?: (...args: Args) => string
}

export function usePendingAction<Args extends unknown[], Result> (
  action: (...args: Args) => Promise<Result> | Result,
  options: PendingActionOptions<Args> = {}
) {
  const running = ref<string[]>([])
  const pending = computed(() => running.value.length > 0)

  function isPending (key = ''): boolean {
    return running.value.includes(key)
  }

  async function run (...args: Args): Promise<Result | undefined> {
    const key = options.key ? options.key(...args) : ''
    if (running.value.includes(key)) return undefined
    running.value = [...running.value, key]
    try {
      return await action(...args)
    } finally {
      running.value = running.value.filter(item => item !== key)
    }
  }

  return { run, pending, isPending }
}
