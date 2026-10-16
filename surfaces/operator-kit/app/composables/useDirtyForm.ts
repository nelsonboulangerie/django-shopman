import { computed, ref, toValue, type MaybeRefOrGetter } from "vue";

import { changedFieldKeys, cloneFormValues, type FormValues } from "../presentation/formShell";

// O estado sujo de um cadastro: o operador mexeu no que ainda não foi salvo?
//
//   const { dirty, changedKeys, capture } = useDirtyForm(() => ({
//     ...form, intent: intent.value, accepted: [...accepted.value],
//   }));
//   // ao abrir/limpar o formulário:
//   capture();
//
// `capture()` tira o RETRATO do que está em tela naquele instante (a abertura,
// depois de um descarte ou de um carregamento vindo do servidor). A partir dali,
// qualquer diferença é "não salvo". Quem carrega dado do servidor e quer que ele
// nasça limpo chama `capture()` de novo quando o dado assentar.
//
// Só o retrato é comparado; o formulário em si continua sendo do chamador.
export function useDirtyForm<T extends FormValues>(source: MaybeRefOrGetter<T>) {
  const baseline = ref<T | null>(null);

  function snapshot(): T {
    return cloneFormValues(toValue(source));
  }

  /** Fixa o retrato do que está em tela agora. */
  function capture() {
    baseline.value = snapshot();
  }

  const changedKeys = computed(() =>
    baseline.value === null ? [] : changedFieldKeys(baseline.value, snapshot()),
  );
  const dirty = computed(() => changedKeys.value.length > 0);

  return { baseline, dirty, changedKeys, capture };
}
