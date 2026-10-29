import type {
  PurchaseActionResponse,
  PurchaseContactPatchPayload,
  PurchaseContactUpsertPayload,
  PurchaseConversionDeclarePayload,
  PurchaseConversionPatchPayload,
  PurchaseCostBatchPayload,
  PurchaseCostUpsertPayload,
  PurchaseMaterialDuplicatePayload,
  PurchaseMaterialPatchPayload,
  PurchaseMaterialUpsertPayload,
  PurchaseMinStockPayload,
  PurchaseCountActionResponse,
  PurchaseCountConfirmPayload,
  PurchaseCountResponse,
  PurchaseReceiptConfirmPayload,
  PurchaseReceiptRejectPayload,
  PurchaseRequestActionPayload,
  PurchaseRequestSendPayload,
  PurchaseOpeningPayload,
  PurchaseResponse,
  PurchaseSalePayload,
  PurchaseScanInvoicePayload,
  PurchaseSupplierDuplicatePayload,
  PurchaseSupplierPatchPayload,
  PurchaseSupplierUpsertPayload,
} from "~/types/purchase";

export const PURCHASE_API_BASE = "/api/v1/backstage/purchase/";

export const PURCHASE_API_ENDPOINTS = {
  projection: PURCHASE_API_BASE,
  scanInvoice: `${PURCHASE_API_BASE}receipts/scan-invoice/`,
  confirmReceipt: `${PURCHASE_API_BASE}receipts/confirm/`,
  rejectReceipt: `${PURCHASE_API_BASE}receipts/reject/`,
  receiptVolumes: `${PURCHASE_API_BASE}receipts/volumes/`,
  upsertCost: `${PURCHASE_API_BASE}costs/`,
  upsertCostBatch: `${PURCHASE_API_BASE}costs/batch/`,
  setMinStock: `${PURCHASE_API_BASE}materials/min-stock/`,
  setOpening: (materialSku: string) =>
    `${PURCHASE_API_BASE}materials/${encodeURIComponent(materialSku)}/opening/`,
  setSale: (materialSku: string) =>
    `${PURCHASE_API_BASE}materials/${encodeURIComponent(materialSku)}/sale/`,
  declareConversion: `${PURCHASE_API_BASE}conversions/`,
  updateConversion: (conversionId: string) =>
    `${PURCHASE_API_BASE}conversions/${encodeURIComponent(conversionId)}/`,
  createMaterial: `${PURCHASE_API_BASE}materials/`,
  updateMaterial: (materialSku: string) =>
    `${PURCHASE_API_BASE}materials/${encodeURIComponent(materialSku)}/`,
  duplicateMaterial: (materialSku: string) =>
    `${PURCHASE_API_BASE}materials/${encodeURIComponent(materialSku)}/duplicate/`,
  createSupplier: `${PURCHASE_API_BASE}suppliers/`,
  updateSupplier: (ref: string) => `${PURCHASE_API_BASE}suppliers/${encodeURIComponent(ref)}/`,
  duplicateSupplier: (ref: string) =>
    `${PURCHASE_API_BASE}suppliers/${encodeURIComponent(ref)}/duplicate/`,
  createSupplierContact: (ref: string) =>
    `${PURCHASE_API_BASE}suppliers/${encodeURIComponent(ref)}/contacts/`,
  updateContact: (contactId: string) => `${PURCHASE_API_BASE}contacts/${encodeURIComponent(contactId)}/`,
  count: `${PURCHASE_API_BASE}count/`,
  countConfirm: `${PURCHASE_API_BASE}count/confirm/`,
  requestSend: (materialSku: string) =>
    `${PURCHASE_API_BASE}requests/${encodeURIComponent(materialSku)}/send/`,
  requestCancel: (materialSku: string) =>
    `${PURCHASE_API_BASE}requests/${encodeURIComponent(materialSku)}/cancel/`,
} as const;

type FetchOptions = {
  credentials: "include";
  headers?: ReturnType<typeof useRequestHeaders>;
};

function fetchOptions(): FetchOptions {
  const headers = import.meta.server ? useRequestHeaders(["cookie"]) : undefined;
  return { credentials: "include", headers };
}

function mutationOptions(idempotencyKey: string) {
  const options = fetchOptions();
  return {
    ...options,
    headers: { ...(options.headers ?? {}), "Idempotency-Key": idempotencyKey },
  };
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

  /** "Contei N volumes" no servidor: outro dispositivo com a mesma NF não pede de novo. */
  async function saveReceiptVolumes(payload: { invoiceAccessKey: string; counted: number | null }) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.receiptVolumes, {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function sendRequest(payload: PurchaseRequestSendPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.requestSend(payload.materialSku), {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function cancelRequest(payload: PurchaseRequestActionPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.requestCancel(payload.materialSku), {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function declareConversion(payload: PurchaseConversionDeclarePayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.declareConversion, {
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

  async function upsertCostBatch(payload: PurchaseCostBatchPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.upsertCostBatch, {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function setMinStock(payload: PurchaseMinStockPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.setMinStock, {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function setOpening(materialSku: string, payload: PurchaseOpeningPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.setOpening(materialSku), {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function setSale(materialSku: string, payload: PurchaseSalePayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.setSale(materialSku), {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function fetchCount() {
    return $fetch<PurchaseCountResponse>(PURCHASE_API_ENDPOINTS.count, fetchOptions());
  }

  async function confirmCount(payload: PurchaseCountConfirmPayload) {
    return $fetch<PurchaseCountActionResponse>(PURCHASE_API_ENDPOINTS.countConfirm, {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  // ── Cadastro da Base ──────────────────────────────────────────────────────
  async function createMaterial(payload: PurchaseMaterialUpsertPayload, idempotencyKey: string) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.createMaterial, {
      ...mutationOptions(idempotencyKey),
      method: "POST",
      body: payload,
    });
  }

  async function updateMaterial(materialSku: string, payload: PurchaseMaterialPatchPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.updateMaterial(materialSku), {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function duplicateMaterial(
    materialSku: string,
    payload: PurchaseMaterialDuplicatePayload,
    idempotencyKey: string,
  ) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.duplicateMaterial(materialSku), {
      ...mutationOptions(idempotencyKey),
      method: "POST",
      body: payload,
    });
  }

  async function createSupplier(payload: PurchaseSupplierUpsertPayload, idempotencyKey: string) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.createSupplier, {
      ...mutationOptions(idempotencyKey),
      method: "POST",
      body: payload,
    });
  }

  async function updateSupplier(ref: string, payload: PurchaseSupplierPatchPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.updateSupplier(ref), {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function duplicateSupplier(
    ref: string,
    payload: PurchaseSupplierDuplicatePayload,
    idempotencyKey: string,
  ) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.duplicateSupplier(ref), {
      ...mutationOptions(idempotencyKey),
      method: "POST",
      body: payload,
    });
  }

  async function createSupplierContact(
    ref: string,
    payload: PurchaseContactUpsertPayload,
    idempotencyKey: string,
  ) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.createSupplierContact(ref), {
      ...mutationOptions(idempotencyKey),
      method: "POST",
      body: payload,
    });
  }

  async function updateContact(contactId: string, payload: PurchaseContactPatchPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.updateContact(contactId), {
      ...fetchOptions(),
      method: "POST",
      body: payload,
    });
  }

  async function updateConversion(conversionId: string, payload: PurchaseConversionPatchPayload) {
    return $fetch<PurchaseActionResponse>(PURCHASE_API_ENDPOINTS.updateConversion(conversionId), {
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
    saveReceiptVolumes,
    sendRequest,
    cancelRequest,
    upsertCost,
    upsertCostBatch,
    setMinStock,
    setSale,
    setOpening,
    declareConversion,
    updateConversion,
    createMaterial,
    updateMaterial,
    duplicateMaterial,
    createSupplier,
    updateSupplier,
    duplicateSupplier,
    createSupplierContact,
    updateContact,
    fetchCount,
    confirmCount,
  };
}
