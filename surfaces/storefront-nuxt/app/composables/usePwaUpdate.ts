import type { Ref } from 'vue'

// Porte do `operator-kit/app/composables/usePwaUpdate.ts`. O registro do service
// worker mora no plugin `pwaRegistration.client.ts`, não num componente: antes era o
// toast de atualização quem registrava o SW, e a tela de erro (`error.vue`), que não
// monta o toast, ficava sem registro e sem oferta de atualizar.
export interface PwaUpdateRegistration {
  needRefresh: Readonly<Ref<boolean>>
  updateServiceWorker: (reloadPage?: boolean) => Promise<void>
  /**
   * Pergunta ao servidor se existe `sw.js` novo. Sem esta chamada o navegador só
   * olha em navegação de documento, e um app instalado que fica dias aberto nunca
   * faz uma. Devolve `false` quando não há registro (SSR, navegador sem SW, sonda
   * recusada) em vez de estourar.
   */
  checkForUpdate: () => Promise<boolean>
}

let registration: PwaUpdateRegistration | null = null

/** Ligação interna usada somente pelo plugin de registro do service worker. */
export function bindPwaUpdateRegistration (next: PwaUpdateRegistration | null) {
  registration = next
}

export function usePwaUpdate () {
  const needRefresh = computed(() => registration?.needRefresh.value || false)

  // `skipWaiting` só por este caminho: `updateServiceWorker(true)` manda a mensagem
  // `SKIP_WAITING` ao worker em espera e recarrega quando ele assume. O gate
  // `tools/pwa-gate/check.mjs` exige que o worker só pule a espera por mensagem.
  async function update (): Promise<boolean> {
    if (!registration) return false
    try {
      await registration.updateServiceWorker(true)
      return true
    } catch {
      return false
    }
  }

  async function checkForUpdate (): Promise<boolean> {
    if (!registration) return false
    try {
      return await registration.checkForUpdate()
    } catch {
      return false
    }
  }

  return { needRefresh, update, checkForUpdate }
}
