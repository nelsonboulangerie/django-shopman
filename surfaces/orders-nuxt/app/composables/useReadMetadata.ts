import type { ReadMetadata } from "~/types/readMetadata";

/** Only a successful canonical read advances this clock; SSE open does not. */
export function useReadMetadata<T extends ReadMetadata>(data: Ref<T | null | undefined>, error: Ref<unknown>, scope?: Ref<string>) {
  const last = shallowRef<ReadMetadata | null>(null);
  if (scope) watch(scope, () => { last.value = null; }, { flush: "sync" });
  watch([data, error], ([value, failure]) => {
    if (value && !failure) {
      last.value = Number.isFinite(Date.parse(value.generated_at ?? ""))
        ? { generated_at: value.generated_at, contract_version: value.contract_version }
        : null;
    }
  }, { immediate: true, flush: "sync" });
  return computed(() => last.value);
}
