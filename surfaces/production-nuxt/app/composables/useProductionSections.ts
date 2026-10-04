import { phoneSections, productionSections, toolSections } from "~/presentation/productionSections";

/** O que a tela da Qualidade conta ao rail (o selo de lotes para confirmar). Fora
 *  dela o selo some, em vez de mentir com um número velho. */
export function useProductionRail() {
  return useState<{ qualityPending: number }>("production-rail", () => ({ qualityPending: 0 }));
}

// As seções do rail e da barra do polegar. Timers vêm do localStorage (o servidor não
// os conhece): o primeiro render do cliente bate com o SSR (zero) e só depois de montar
// mostra o real, como o botão de Timers fazia no cabeçalho.
export function useProductionSections() {
  const { allowed: reportsAllowed } = useReportsAccess();
  const { canView: recipesAllowed } = useRecipeBookAccess();
  const floorTimers = useFloorTimers();
  const rail = useProductionRail();
  const hydrated = ref(false);
  onMounted(() => {
    hydrated.value = true;
  });

  const input = computed(() => ({
    timersActive: hydrated.value ? floorTimers.activeCount.value : 0,
    timersRinging: hydrated.value ? floorTimers.ringingCount.value : 0,
    qualityPending: rail.value.qualityPending,
    canViewRecipes: recipesAllowed.value,
    canViewReports: reportsAllowed.value,
  }));
  const sections = computed(() => productionSections(input.value));
  const phone = computed(() => phoneSections(input.value));
  const tools = computed(() => toolSections(input.value));
  return { sections, phone, tools, input };
}
