import type {
  PurchaseActionResponse,
  PurchaseCostUpsertPayload,
  PurchaseReceiptConfirmPayload,
  PurchaseReceiptRejectPayload,
  PurchaseRequestActionPayload,
  PurchaseResponse,
  PurchaseScanInvoicePayload,
} from "~/types/purchase";

export const PURCHASE_API_BASE = "/api/v1/backstage/purchase/";

export const PURCHASE_API_ENDPOINTS = {
  projection: PURCHASE_API_BASE,
  scanInvoice: `${PURCHASE_API_BASE}receipts/scan-invoice/`,
  confirmReceipt: `${PURCHASE_API_BASE}receipts/confirm/`,
  rejectReceipt: `${PURCHASE_API_BASE}receipts/reject/`,
  upsertCost: `${PURCHASE_API_BASE}costs/`,
  requestApprove: (materialSku: string) =>
    `${PURCHASE_API_BASE}requests/${encodeURIComponent(materialSku)}/approve/`,
  requestSend: (materialSku: string) =>
    `${PURCHASE_API_BASE}requests/${encodeURIComponent(materialSku)}/send/`,
} as const;

type FetchOptions = {
  credentials: "include";
  headers?: ReturnType<typeof useRequestHeaders>;
};

function fetchOptions(): FetchOptions {
  const headers = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;
  return { credentials: "include", headers };
}

export function usePurchaseApi() {
  async function fetchProjection() {
    return $fetch<PurchaseResponse>(PURCHASE_API_ENDPOINTS.projection, fetchOptions());
  }

  async function scanInvoice(payload: PurchaseScanInvoicePayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.scanInvoice, {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function confirmReceipt(payload: PurchaseReceiptConfirmPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.confirmReceipt, {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function rejectReceipt(payload: PurchaseReceiptRejectPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.rejectReceipt, {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function approveRequest(payload: PurchaseRequestActionPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.requestApprove(payload.materialSku), {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function sendRequest(payload: PurchaseRequestActionPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.requestSend(payload.materialSku), {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function upsertCost(payload: PurchaseCostUpsertPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.upsertCost, {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  return {
    endpoints: PURCHASE_API_ENDPOINTS,
    fetchProjection,
    scanInvoice,
    confirmReceipt,
    rejectReceipt,
    approveRequest,
    sendRequest,
    upsertCost,
  };
}
