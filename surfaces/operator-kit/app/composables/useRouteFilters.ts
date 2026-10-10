import type { MaybeRefOrGetter } from "vue";

import { filtersFromQuery, mergeFilterQuery } from "../presentation/filterBar";
import type { ActiveFilters, FilterDimension } from "../types/filters";

/**
 * O recorte da `FilterBar` guardado na URL (plano SUITE-UX: "tudo na URL").
 *
 * Devolve um `computed` gravável para o `v-model` da barra: ler parseia a query da
 * rota; gravar troca só as chaves das dimensões (período, busca e aba ficam) com
 * `router.replace`, para o voltar do navegador não virar um desfazer de filtro.
 * `resetKeys` (ex.: `["page"]`) some a cada troca de recorte.
 *
 * ```ts
 * const filters = useRouteFilters(dimensions, { resetKeys: ["page"] });
 * // <FilterBar v-model="filters" :dimensions="dimensions" />
 * ```
 */
export function useRouteFilters(
  dimensions: MaybeRefOrGetter<FilterDimension[]>,
  options: { resetKeys?: readonly string[] } = {},
) {
  const route = useRoute();
  const router = useRouter();
  return computed<ActiveFilters>({
    get: () => filtersFromQuery(toValue(dimensions), route.query),
    set: (filters) => {
      router.replace({ query: mergeFilterQuery(route.query, toValue(dimensions), filters, options.resetKeys) });
    },
  });
}
