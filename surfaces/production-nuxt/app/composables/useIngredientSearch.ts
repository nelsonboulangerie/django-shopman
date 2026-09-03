// Busca de insumos para casar um ingrediente — GET recipes/ingredients/?q=.
// As opções são os `Material` do Buyman e as saídas de RecipeEntry com fórmula
// (partes). Debounce curto: o padeiro digita "far" e a lista já aparece; respostas
// fora de ordem são descartadas.
import type { IngredientOptionProjection, IngredientsResponse } from "~/types/recipeBook";

export const INGREDIENT_SEARCH_DEBOUNCE_MS = 250;
export const INGREDIENT_SEARCH_MIN_CHARS = 2;

export function useIngredientSearch() {
  const term = ref("");
  const options = ref<IngredientOptionProjection[]>([]);
  const pending = ref(false);
  const error = ref("");

  let timer: ReturnType<typeof setTimeout> | null = null;
  let sequence = 0;

  async function run(q: string): Promise<IngredientOptionProjection[]> {
    const ticket = ++sequence;
    pending.value = true;
    try {
      const response = await $fetch<IngredientsResponse>("/api/v1/backstage/recipes/ingredients/", {
        query: { q },
      });
      if (ticket !== sequence) return [];
      options.value = response.options ?? [];
      error.value = "";
      return options.value;
    } catch (err) {
      if (ticket !== sequence) return [];
      options.value = [];
      error.value = httpErrorMessage(err, "Não foi possível buscar insumos.");
      return [];
    } finally {
      if (ticket === sequence) pending.value = false;
    }
  }

  /** Agenda a busca (debounce). Termo curto limpa a lista sem pedir nada. */
  function search(q: string): void {
    term.value = q;
    if (timer) clearTimeout(timer);
    const trimmed = q.trim();
    if (trimmed.length < INGREDIENT_SEARCH_MIN_CHARS) {
      sequence++;
      options.value = [];
      pending.value = false;
      return;
    }
    pending.value = true;
    timer = setTimeout(() => {
      timer = null;
      void run(trimmed);
    }, INGREDIENT_SEARCH_DEBOUNCE_MS);
  }

  function reset(): void {
    if (timer) clearTimeout(timer);
    timer = null;
    sequence++;
    term.value = "";
    options.value = [];
    pending.value = false;
    error.value = "";
  }

  onBeforeUnmount(() => {
    if (timer) clearTimeout(timer);
  });

  return { term, options, pending, error, search, reset };
}
