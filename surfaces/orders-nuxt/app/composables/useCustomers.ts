import { useOperatorResourceKey } from "./useOperatorResourceKey";
import { useReadMetadata } from "./useReadMetadata";
import type { CustomerListQuery } from "~/presentation/customers";
import type {
  CustomerDetailResponse,
  CustomerListResponse,
  MergeAuditListResponse,
  MergePreviewResponse,
  MergeResponse,
} from "~/types/customers";

// Clientes do Gestor — leitura por projection, escrita pelo MergeService (via
// /api/v1/backstage/customers/*). Permissão: `shop.manage_customers`.
const BASE = "/api/v1/backstage/customers";

export function useCustomerList(query: Ref<CustomerListQuery>) {
  const { data, pending, error, refresh } = useFetch<CustomerListResponse>(`${BASE}/`, {
    key: useOperatorResourceKey("customers:list"),
    query: computed(() => ({ q: query.value.q || undefined, filter: query.value.filter, page: query.value.page })),
    dedupe: "defer",
    onResponseError: operatorSessionOnError,
  });
  const readMetadata = useReadMetadata(data, error);
  // A última lista confirmada fica na tela enquanto a próxima página carrega.
  const lastConfirmed = shallowRef(data.value?.list ?? null);
  watch(data, (value) => { if (value?.list) lastConfirmed.value = value.list; }, { flush: "sync" });
  const list = computed(() => data.value?.list ?? lastConfirmed.value);
  return { list, pending, error, refresh, readMetadata };
}

export function useCustomerDetail(ref_: Ref<string>) {
  const { data, pending, error, refresh } = useFetch<CustomerDetailResponse>(() => `${BASE}/${encodeURIComponent(ref_.value)}/`, {
    key: useOperatorResourceKey(`customers:detail:${ref_.value}`),
    dedupe: "defer",
    onResponseError: operatorSessionOnError,
  });
  const readMetadata = useReadMetadata(data, error);
  const customer = computed(() => data.value?.customer ?? null);
  return { customer, pending, error, refresh, readMetadata };
}

/** Busca curta para o "Unificar com…": a mesma lista, primeira página. */
export async function searchCustomers(q: string) {
  const response = await $fetch<CustomerListResponse>(`${BASE}/`, { query: { q } });
  return response.list.items;
}

export function fetchMergePreview(sourceRef: string, targetRef: string) {
  return $fetch<MergePreviewResponse>(`${BASE}/merge/preview/`, {
    query: { source_ref: sourceRef, target_ref: targetRef },
  });
}

export function postMerge(sourceRef: string, targetRef: string) {
  return $fetch<MergeResponse>(`${BASE}/merge/`, {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: { source_ref: sourceRef, target_ref: targetRef },
  });
}

export function useCustomerMerges() {
  const { data, pending, error, refresh } = useFetch<MergeAuditListResponse>(`${BASE}/merges/`, {
    key: useOperatorResourceKey("customers:merges"),
    dedupe: "defer",
    onResponseError: operatorSessionOnError,
  });
  const readMetadata = useReadMetadata(data, error);
  const merges = computed(() => data.value?.merges ?? null);
  const busyId = ref("");
  const message = ref("");

  async function undo(auditId: string): Promise<boolean> {
    if (busyId.value) return false;
    busyId.value = auditId;
    message.value = "";
    try {
      await $fetch(`${BASE}/merges/${encodeURIComponent(auditId)}/undo/`, {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
      });
      return true;
    } catch (failure) {
      message.value = httpErrorMessage(failure, "Não foi possível desfazer a unificação.");
      return false;
    } finally {
      busyId.value = "";
      try { await refresh(); } catch { /* a leitura falha em silêncio; o erro dela aparece no aviso da tela */ }
    }
  }

  return { merges, pending, error, refresh, readMetadata, undo, busyId, message };
}
