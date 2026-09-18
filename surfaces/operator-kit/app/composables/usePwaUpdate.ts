import { computed, type Ref } from "vue";

export interface PwaUpdateRegistration {
  needRefresh: Readonly<Ref<boolean>>;
  updateServiceWorker: (reloadPage?: boolean) => Promise<void>;
  /**
   * Pergunta ao servidor se existe `sw.js` novo. Sem esta chamada o navegador só
   * olha em navegação de documento — e um app instalado que fica dias aberto nunca
   * faz uma. Devolve `false` quando não há registro (SSR, browser sem SW, sonda
   * recusada) em vez de estourar.
   */
  checkForUpdate: () => Promise<boolean>;
}

let registration: PwaUpdateRegistration | null = null;

/** Ligação interna usada somente pelo plugin instalado pela capability opt-in. */
export function bindPwaUpdateRegistration(next: PwaUpdateRegistration | null) {
  registration = next;
}

export function usePwaUpdate() {
  const needRefresh = computed(() => registration?.needRefresh.value || false);

  async function update(): Promise<boolean> {
    if (!registration) return false;
    try {
      await registration.updateServiceWorker(true);
      return true;
    } catch {
      return false;
    }
  }

  async function checkForUpdate(): Promise<boolean> {
    if (!registration) return false;
    try {
      return await registration.checkForUpdate();
    } catch {
      return false;
    }
  }

  return { needRefresh, update, checkForUpdate };
}
