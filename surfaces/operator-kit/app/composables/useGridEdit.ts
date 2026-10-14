import { computed, shallowRef } from "vue";

export interface GridChange<T> {
  key: string;
  value: T;
}

/**
 * Buffer de edição do tabelão: rascunho por célula, pilha de DESFAZER e a lista
 * de mudanças para salvar tudo numa ida. Não conhece domínio: guarda valores.
 */
export function useGridEdit<T>() {
  // shallowRef: o ref profundamente reativo desembrulharia T em UnwrapRef<T>,
  // e o rascunho deixaria de ser exatamente Record<string, T>.
  const draft = shallowRef<Record<string, T>>({});
  const history = shallowRef<{ key: string; previous: T | undefined }[]>([]);

  function set(key: string, value: T) {
    if (draft.value[key] === value) return;
    history.value = [...history.value, { key, previous: draft.value[key] }];
    draft.value = { ...draft.value, [key]: value };
  }

  function remove(key: string) {
    if (!(key in draft.value)) return;
    history.value = [...history.value, { key, previous: draft.value[key] }];
    const next = { ...draft.value };
    delete next[key];
    draft.value = next;
  }

  /** Desfaz a ÚLTIMA edição, uma a uma (a pilha é do operador, não da tela). */
  function undo() {
    const last = history.value.at(-1);
    if (!last) return;
    history.value = history.value.slice(0, -1);
    const next = { ...draft.value };
    const previous = last.previous;
    if (previous === undefined) delete next[last.key];
    else next[last.key] = previous;
    draft.value = next;
  }

  function clear() {
    draft.value = {};
    history.value = [];
  }

  const dirty = computed(() => Object.keys(draft.value).length);
  const canUndo = computed(() => history.value.length > 0);
  const changes = computed<GridChange<T>[]>(() =>
    Object.entries(draft.value).map(([key, value]) => ({ key, value })),
  );

  return { draft, dirty, canUndo, changes, set, remove, undo, clear };
}
