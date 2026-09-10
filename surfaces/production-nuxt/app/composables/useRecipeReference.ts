// Valores de referência da literatura para um `kind` de receita —
// GET recipes/reference/?kind=. São referência, não regra: a tela mostra a faixa
// ao lado da métrica e o padeiro decide (§4).
import type { Ref } from "vue";
import type { ReferenceResponse } from "~/types/recipeBook";

export function useRecipeReference(kind: Ref<string>) {
  const { data, pending, error, refresh } = useFetch<ReferenceResponse>("/api/v1/backstage/recipes/reference/", {
    key: "recipe-reference",
    server: true,
    query: computed(() => ({ kind: kind.value })),
    watch: [kind],
  });

  const reference = computed(() => data.value?.reference ?? null);
  const ranges = computed(() => reference.value?.ranges ?? []);

  return { reference, ranges, pending, error, refresh };
}
