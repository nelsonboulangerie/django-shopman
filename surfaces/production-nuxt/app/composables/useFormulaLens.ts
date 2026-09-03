// Prévia da lente no editor. A conta (porcentagem do padeiro, hidratação, partes,
// mistura final, BOM, avisos) é do SERVIDOR — POST recipes/lens/ com a fórmula em
// edição, com debounce de 300 ms para o padeiro digitar sem disparar um pedido por
// tecla. Respostas fora de ordem são descartadas (só a última fórmula vale).
// `standardize(basisG)` chama POST recipes/standardize/ e devolve a fórmula
// escalada + a lente; quem decide substituir a fórmula em edição é a tela (ela
// guarda o antes como referência).
import type { Ref } from "vue";
import type { Formula, FormulaLensProjection, LensResponse, StandardizeResponse } from "~/types/recipeBook";
import { HOUSE_BASIS_G } from "~/presentation/recipeBook";

export const LENS_DEBOUNCE_MS = 300;

export function useFormulaLens(formula: Ref<Formula>, kind: Ref<string>) {
  const lens = ref<FormulaLensProjection | null>(null);
  const pending = ref(false);
  const error = ref("");
  const standardizing = ref(false);

  let timer: ReturnType<typeof setTimeout> | null = null;
  let sequence = 0;

  async function compute(): Promise<void> {
    const ticket = ++sequence;
    pending.value = true;
    try {
      const response = await $fetch<LensResponse>("/api/v1/backstage/recipes/lens/", {
        method: "POST",
        body: { formula: formula.value, kind: kind.value },
      });
      if (ticket !== sequence) return;
      lens.value = response.lens;
      error.value = "";
    } catch (err) {
      if (ticket !== sequence) return;
      error.value = httpErrorMessage(err, "Não foi possível calcular a prévia.");
    } finally {
      if (ticket === sequence) pending.value = false;
    }
  }

  function schedule(): void {
    if (timer) clearTimeout(timer);
    pending.value = true;
    timer = setTimeout(() => {
      timer = null;
      void compute();
    }, LENS_DEBOUNCE_MS);
  }

  watch([formula, kind], schedule, { deep: true, immediate: true });

  onBeforeUnmount(() => {
    if (timer) clearTimeout(timer);
  });

  async function standardize(basisG: number = HOUSE_BASIS_G): Promise<Formula | null> {
    if (standardizing.value) return null;
    standardizing.value = true;
    try {
      const response = await $fetch<StandardizeResponse>("/api/v1/backstage/recipes/standardize/", {
        method: "POST",
        body: { formula: formula.value, basis_g: basisG },
      });
      lens.value = response.lens;
      error.value = "";
      return response.formula;
    } catch (err) {
      useSonner.error(httpErrorMessage(err, "Não foi possível padronizar a fórmula."));
      return null;
    } finally {
      standardizing.value = false;
    }
  }

  return { lens, pending, error, standardizing, standardize, recompute: compute };
}
