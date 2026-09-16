import { computed, type Ref } from "vue";

export interface PwaUpdateRegistration {
  needRefresh: Readonly<Ref<boolean>>;
  updateServiceWorker: (reloadPage?: boolean) => Promise<void>;
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

  return { needRefresh, update };
}
