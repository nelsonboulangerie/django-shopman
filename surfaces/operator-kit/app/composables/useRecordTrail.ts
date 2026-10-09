// A trilha da lista de origem (WP-FASE2-UX-OPERADOR, K5): a lista grava a ordem que
// mostra, o detalhe lê e oferece anterior e próximo (`OperatorRecordNav`).
//
// Mora na sessão do navegador (`sessionStorage`), por chave: o detalhe recarregado ainda
// sabe de que lista veio, e outra aba começa sem trilha. Duas listas que abrem o mesmo
// detalhe (a fila e o histórico do Gestor) usam chaves diferentes, e o detalhe escolhe
// qual ler pelo caminho por onde a pessoa chegou.
//
// No servidor não há trilha: o par só aparece depois de montar, nunca diverge na
// hidratação.
import { computed, getCurrentInstance, onMounted, type ComputedRef } from "vue";

import { parseRecordTrail, recordTrailOf, type RecordTrail } from "../presentation/recordTrail";

const STORAGE_PREFIX = "operator-record-trail:";

export function useRecordTrail(key: string): {
  trail: ComputedRef<RecordTrail | null>;
  remember: (ids: readonly string[], origin: { from: string; label: string }) => void;
  load: () => void;
} {
  const trail = useState<RecordTrail | null>(`operator-record-trail-${key}`, () => null);
  const storageKey = `${STORAGE_PREFIX}${key}`;

  /** A lista grava a ordem que mostra agora, com o endereço do recorte. */
  function remember(ids: readonly string[], origin: { from: string; label: string }) {
    if (import.meta.server) return;
    const next = recordTrailOf(ids, origin.from, origin.label);
    trail.value = next;
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(next));
    } catch {
      // Sem armazenamento (janela privada, cota): a trilha vale enquanto o app vive.
    }
  }

  /** O detalhe lê a trilha guardada (depois de montar). */
  function load() {
    if (import.meta.server) return;
    try {
      const stored = parseRecordTrail(sessionStorage.getItem(storageKey));
      if (stored) trail.value = stored;
    } catch {
      // Sem armazenamento: fica a trilha do app em memória, se houver.
    }
  }

  if (getCurrentInstance()) onMounted(load);

  return { trail: computed(() => trail.value), remember, load };
}
