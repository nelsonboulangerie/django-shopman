import { gestorRoutePermission } from "~/presentation/gestorSections";
import { useOperatorResourceKey } from "./useOperatorResourceKey";

/**
 * A tela de Ajustes aberta é da conta de quem está operando? A mesma pergunta da
 * antessala (`?perm=`), feita uma vez por tela e por pessoa. Responde `denied` só
 * quando o servidor disse não: carregando ou falhando, a página monta e trata a própria
 * leitura (falha de rede continua sendo falha de rede).
 */
export function useGestorRouteAccess() {
  const route = useRoute();
  const rule = computed(() => gestorRoutePermission(route.path));
  const { data: session } = useNuxtData<{ operator?: { id: number } }>("operator-session");
  const operatorId = computed(() => session.value?.operator?.id ?? null);
  const base = useOperatorResourceKey("route-access");
  const { data } = useFetch<{ authorized?: boolean }>("/api/v1/backstage/operator/session/", {
    key: computed(() => `${base}:${rule.value?.perm ?? "none"}`),
    query: computed(() => ({ perm: rule.value?.perm ?? "" })),
    server: false,
    immediate: Boolean(rule.value),
    watch: [rule, operatorId],
  });
  const denied = computed(
    () => Boolean(rule.value) && data.value?.authorized === false,
  );
  return { denied, what: computed(() => rule.value?.what ?? "") };
}
