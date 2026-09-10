// Comparação de duas versões (mesma receita ou receitas diferentes) —
// GET recipes/compare/?a=<ref>@<n>&b=<ref>@<n>. Os deltas por ingrediente e por
// métrica chegam prontos (display + tom); a tela só desenha. Sem os dois lados
// escolhidos não há o que pedir: `ready` segura a leitura da resposta.
import type { Ref } from "vue";
import type { CompareResponse } from "~/types/recipeBook";

export function useRecipeCompare(a: Ref<string>, b: Ref<string>) {
  const ready = computed(() => !!a.value && !!b.value);

  const { data, pending, error, refresh } = useFetch<CompareResponse>("/api/v1/backstage/recipes/compare/", {
    key: "recipe-compare",
    server: true,
    query: computed(() => ({ a: a.value, b: b.value })),
    immediate: ready.value,
    watch: [a, b],
  });

  const compare = computed(() => (ready.value ? (data.value?.compare ?? null) : null));
  const rows = computed(() => compare.value?.rows ?? []);
  const metrics = computed(() => compare.value?.metrics ?? []);

  return { ready, compare, rows, metrics, pending, error, refresh };
}
