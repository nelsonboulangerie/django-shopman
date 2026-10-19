import { useOperatorResourceKey } from "./useOperatorResourceKey";
import { useReadMetadata } from "./useReadMetadata";
import type {
  CustomerGroupDetailResponse,
  CustomerGroupListResponse,
  CustomerGroupMembersPayload,
  CustomerGroupMembersResponse,
  CustomerGroupMutationPayload,
  CustomerGroupMutationResponse,
} from "~/types/customerGroups";

const BASE = "/api/v1/backstage/customers/groups";

export function useCustomerGroups() {
  const { data, pending, error, refresh } = useFetch<CustomerGroupListResponse>(`${BASE}/`, {
    key: useOperatorResourceKey("customers:groups"),
    dedupe: "defer",
    onResponseError: operatorSessionOnError,
  });
  return {
    groups: computed(() => data.value?.groups ?? null),
    pending,
    error,
    refresh,
    readMetadata: useReadMetadata(data, error),
  };
}

export function fetchCustomerGroup(ref: string) {
  return $fetch<CustomerGroupDetailResponse>(`${BASE}/${encodeURIComponent(ref)}/`);
}

export function createCustomerGroup(payload: CustomerGroupMutationPayload, idempotencyKey: string) {
  return $fetch<CustomerGroupMutationResponse>(`${BASE}/`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: payload,
  });
}

export function updateCustomerGroup(
  ref: string,
  payload: CustomerGroupMutationPayload,
  idempotencyKey: string,
) {
  return $fetch<CustomerGroupMutationResponse>(`${BASE}/${encodeURIComponent(ref)}/`, {
    method: "PATCH",
    headers: { "Idempotency-Key": idempotencyKey },
    body: payload,
  });
}

/**
 * Põe ou tira vários clientes de um grupo numa ida. A mesma chave de intenção
 * repete a mesma resposta; o servidor ignora quem já estava como o gesto pede.
 */
export function changeCustomerGroupMembers(
  ref: string,
  payload: CustomerGroupMembersPayload,
  idempotencyKey: string,
) {
  return $fetch<CustomerGroupMembersResponse>(`${BASE}/${encodeURIComponent(ref)}/members/`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: payload,
  });
}
