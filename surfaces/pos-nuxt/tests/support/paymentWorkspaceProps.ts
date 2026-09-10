// Fábrica de props do `PosPaymentWorkspace` para testes de componente.
//
// Extraída do `tests/components/PosPaymentWorkspace.test.ts` (que segue com a
// cópia própria por ora — há trabalho de outra frente em voo naquele arquivo;
// quando ela fechar, o arquivo passa a importar daqui). Um lugar só para o
// contrato mínimo que monta a tela: quem escreve um teste novo importa e
// sobrescreve o que o caso pede.
import type { POSCartItem, POSSaleReviewProjection } from "~/types/pos";

export function item(overrides: Partial<POSCartItem> & { sku: string; name: string }): POSCartItem {
  return { price_q: 1000, qty: 1, notes: "", ...overrides };
}

export function review(overrides: Partial<POSSaleReviewProjection> = {}): POSSaleReviewProjection {
  return {
    total_q: 1000,
    total_display: "R$ 10,00",
    subtotal_q: 1000,
    subtotal_display: "R$ 10,00",
    requires_manager_approval: false,
    ...overrides,
  } as POSSaleReviewProjection;
}

export function workspaceProps(overrides: Record<string, unknown> = {}) {
  return {
    tabDisplay: "M1",
    items: [item({ sku: "PAO", name: "Pão" })],
    hasOpenTab: true,
    fulfillmentOptions: [{ ref: "pickup", label: "Retirada", description: "", requires_address: false }],
    paymentMethods: [
      { ref: "cash", label: "Dinheiro" },
      { ref: "pix", label: "PIX" },
      { ref: "card", label: "Cartão" },
      { ref: "mixed", label: "Misto" },
    ],
    paymentCollections: [],
    checkoutContract: { capabilities: {}, receipt_channels: [] },
    addressAutocomplete: null,
    customerLookup: null,
    searchResults: [],
    searchBusy: false,
    review: review(),
    discountTypes: [],
    discountReasons: [],
    discountType: "percent",
    discountValue: "",
    discountReason: "",
    managerUsername: "",
    managerPin: "",
    managers: [],
    fulfillmentType: "pickup",
    paymentCollection: "terminal",
    paymentTenders: [],
    splitCount: 0,
    splitPaidCount: 0,
    splitNote: "",
    selectedTenderIndex: -1,
    selectedTenderMethod: "",
    paymentTotalQ: 1000,
    paymentRemainingQ: 1000,
    paymentChangeQ: 0,
    paymentCovered: false,
    customerName: "",
    customerPhone: "",
    customerTaxId: "",
    customerEmail: "",
    deliveryAddress: "",
    deliveryAddressStructured: {},
    deliveryStreetNumber: "",
    deliveryNeighborhood: "",
    deliveryComplement: "",
    deliveryInstructions: "",
    deliveryDate: "",
    deliveryTimeSlot: "",
    deliveryFeeInput: "",
    deliveryFeeQ: 0,
    deliverySlots: [],
    scheduleToday: "",
    changeForInput: "",
    orderNotes: "",
    receiptChannels: [],
    receiptEmail: "",
    saveReceiptContact: null,
    saveReceiptTaxId: null,
    loading: false,
    lookupBusy: false,
    ...overrides,
  };
}
