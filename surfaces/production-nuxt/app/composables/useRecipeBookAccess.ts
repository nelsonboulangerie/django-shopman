// Sonda de acesso do inventário de receitas: decide se a entrada "Receitas"
// aparece no rail e se os botões de escrita aparecem nas telas. A régua vive no
// backend (ler = backstage.operate_production; escrever = shop.manage_production;
// leitura automática = credencial do provedor configurada) — em vez de duplicar a
// regra aqui, a nav consulta GET recipes/access/ (mesmo padrão do useReportsAccess).
// 403/erro = some, sem alarde: é um operador de chão, não uma falha.
import type { AccessResponse } from "~/types/recipeBook";

export function useRecipeBookAccess() {
  const { data, error, pending } = useFetch<AccessResponse>("/api/v1/backstage/recipes/access/", {
    key: "recipe-book-access",
    server: true,
  });

  const access = computed(() => (error.value ? null : (data.value?.access ?? null)));
  const canView = computed(() => !!access.value?.can_view);
  const canEdit = computed(() => !!access.value?.can_edit);
  const captureAvailable = computed(() => !!access.value?.capture_available);

  return { access, canView, canEdit, captureAvailable, pending };
}
