// Comparação de duas versões (mesma receita ou receitas diferentes) —
// GET recipes/compare/?a=<ref>@<n>&b=<ref>@<n>. Os deltas por ingrediente e por
// métrica chegam prontos (display + tom); a tela só desenha.
//
// A chave é do PAR escolhido: a receita (diálogo de publicar) e a tela de Comparar usam
// este composable, e com uma chave fixa as duas dividiam o mesmo estado. A tela de
// Comparar herdava o pedido vazio da receita (`?a&b`, 400) e nunca pedia o par que a
// pessoa escolheu (achado da J-P9, #3403). Sem os dois lados não há pedido: o handler
// devolve `null` e nada sai para o servidor.
import type { Ref } from "vue";
import type { CompareResponse } from "~/types/recipeBook";

export function useRecipeCompare(a: Ref<string>, b: Ref<string>) {
  const ready = computed(() => !!a.value && !!b.value);
  const request = useRequestFetch();

  const { data, pending, error, refresh } = useAsyncData<CompareResponse | null>(
    computed(() => `recipe-compare:${a.value}|${b.value}`),
    () =>
      ready.value
        ? request<CompareResponse>("/api/v1/backstage/recipes/compare/", { query: { a: a.value, b: b.value } })
        : Promise.resolve(null),
  );

  const compare = computed(() => (ready.value ? (data.value?.compare ?? null) : null));
  const rows = computed(() => compare.value?.rows ?? []);
  const metrics = computed(() => compare.value?.metrics ?? []);

  return { ready, compare, rows, metrics, pending, error, refresh };
}
