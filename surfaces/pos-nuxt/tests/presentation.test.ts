import { describe, expect, it } from "vitest";

import type {
  Action,
  POSCartItem,
  POSCashRuntimeProjection,
  POSCheckoutContractProjection,
  POSCollectionProjection,
  POSPaymentCollectionProjection,
  POSPaymentMethodProjection,
  POSPaymentResultProjection,
  POSPaymentTenderDraft,
  POSProductProjection,
  POSTabProjection,
} from "../app/types/pos";
import { findAction, hasAction, resolveAffordance } from "../app/presentation/actions";
import {
  enterTargetProduct,
  filterProducts,
  normalizeSearchText,
  orderCollections,
  productFallbackIcon,
  productFallbackStyle,
} from "../app/presentation/catalog";
import { countOpenTabs, filterTabs, filterTabsByQuery, sanitizeTabRef, sortTabs, tabCardView } from "../app/presentation/tabBoard";
import { nextFreeNumericTabRef } from "../app/utils/posTabLifecycle";
import { clampPercent, clampQty, popDigit, pushDigit } from "../app/presentation/numpad";
import {
  cashNoteLabel,
  cashNotesQ,
  cashTenderSumQ,
  changeForShortfallQ,
  collectionsForFulfillment,
  injectableMethods,
  isPaymentCovered,
  machineTenderLines,
  methodLabel,
  nonCashExcessQ,
  paymentChangeQ,
  methodShortcuts,
  paymentIcon,
  paymentDeadlineLabel,
  paymentProofView,
  paymentRemainingQ,
  qrCodeSrc,
  splitHint,
  splitShareQ,
  tenderLineView,
  tenderSumQ,
} from "../app/presentation/payment";
import {
  amountInputError,
  amountToQ,
  canRegisterMovement,
  canRequestChange,
  canSubmitCashAmount,
  changeDenominations,
  changeRequestSummary,
  denominationCountTotalQ,
  formatAmountInput,
  formatOpenedAt,
  formatRequestedAt,
  movementLabel,
  movementReasons,
  parseAmountToQ,
  requiresOpenShiftForSale,
  sessionScreenState,
} from "../app/presentation/cash";
import type { ManagerAction } from "../app/presentation/managerAuth";
import { MANAGER_ACTIONS, managerAuthReason, managerAuthTitle } from "../app/presentation/managerAuth";
import {
  availableMoveModes,
  buildMovePayload,
  canSubmitMove,
  defaultMoveTarget,
  freezesPriceOnMove,
  moveLineId,
  moveLineView,
  modeNeedsSelection,
  moveTargetOptions,
  selectedLineIds,
} from "../app/presentation/moveLines";
import {
  allLinesFired,
  pendingKitchenQty,
  fireBarView,
  firedCount,
  kitchenBadge,
  kitchenLineState,
  unfiredCount,
} from "../app/presentation/kitchen";
import { pruneSelection, selectedItems, selectionView, toggleSelected } from "../app/presentation/selection";
import { cashLandedInDrawer, receiptLineTotalQ, receiptLines, receiptPayments, type PosReceiptSnapshot } from "../app/presentation/receipt";
import type { ActionAffordance } from "../app/presentation/actions";
import { formatBRL } from "../app/utils/posIntent";

function cartItem(overrides: Partial<POSCartItem> & { sku: string }): POSCartItem {
  return {
    name: overrides.sku,
    price_q: 0,
    qty: 1,
    notes: "",
    
    ...overrides,
  };
}

function affordance(overrides: Partial<ActionAffordance> = {}): ActionAffordance {
  return {
    ref: "fire_tab",
    present: true,
    label: "Enviar itens",
    priority: "normal",
    enabled: true,
    reason: "",
    href: "",
    method: "POST",
    idempotency: "none",
    confirmation: {},
    ...overrides,
  };
}

function tender(method: string, amountQ: number): POSPaymentTenderDraft {
  return { method, amount_q: amountQ, collection: "terminal" };
}

const METHODS: POSPaymentMethodProjection[] = [
  { ref: "cash", label: "Dinheiro" },
  { ref: "pix", label: "PIX" },
  { ref: "card", label: "Cartão" },
  { ref: "mixed", label: "Misto" },
];

function action(overrides: Partial<Action> & { ref: string }): Action {
  return {
    kind: "mutation",
    label: "",
    priority: "secondary",
    enabled: true,
    reason: "",
    href: "",
    method: "POST",
    payload_schema: {},
    idempotency: "none",
    confirmation: {},
    ...overrides,
  };
}

function product(overrides: Partial<POSProductProjection> & { sku: string }): POSProductProjection {
  return {
    name: overrides.sku,
    price_q: 0,
    price_display: "",
    collection_ref: "",
    collection_color: "",
    collection_icon: "",
    
    image_url: "",
    ...overrides,
  };
}

function tab(overrides: Partial<POSTabProjection> & { ref: string }): POSTabProjection {
  return {
    display_ref: overrides.ref,
    session_key: "",
    state: "empty",
    status_label: "",
    status_class: "",
    customer_name: "",
    customer_phone: "",
    item_count: 0,
    line_count: 0,
    total_display: "",
    last_touched_display: "",
    items_preview: "",
    ...overrides,
  };
}

describe("presentation/actions — Action → affordance", () => {
  const actions = [
    action({ ref: "open_tab", label: "Abrir", href: "/api/v1/backstage/pos/tabs/{tab_ref}/open/" }),
    action({ ref: "fire_tab", label: "Cozinha", enabled: false, reason: "Caixa fechado", priority: "primary" }),
  ];

  it("finds actions and reports presence", () => {
    expect(findAction(actions, "open_tab")?.label).toBe("Abrir");
    expect(findAction(actions, "missing")).toBeUndefined();
    expect(hasAction(actions, "fire_tab")).toBe(true);
    expect(hasAction(actions, "missing")).toBe(false);
  });

  it("substitutes path params into the concrete href", () => {
    const aff = resolveAffordance(actions, "open_tab", { params: { tab_ref: "00001007" } });
    expect(aff.present).toBe(true);
    expect(aff.enabled).toBe(true);
    expect(aff.href).toBe("/api/v1/backstage/pos/tabs/00001007/open/");
  });

  it("reflects enabled/reason verbatim from the projection (zero policy)", () => {
    const aff = resolveAffordance(actions, "fire_tab");
    expect(aff.enabled).toBe(false);
    expect(aff.reason).toBe("Caixa fechado");
    expect(aff.priority).toBe("primary");
  });

  it("returns an absent affordance with the fallback href when the action is missing", () => {
    const aff = resolveAffordance(actions, "close_sale", { fallbackHref: "/fallback/" });
    expect(aff.present).toBe(false);
    expect(aff.enabled).toBe(false);
    expect(aff.href).toBe("/fallback/");
    expect(aff.method).toBe("POST");
    // Ação ausente da projection não pode ler como "não precisa de trava de
    // replay": o fallback repete o default restritivo do backend.
    expect(aff.idempotency).toBe("required");
  });
});

describe("presentation/catalog — grid shaping", () => {
  const collections: POSCollectionProjection[] = [
    { ref: "doces", name: "Doces" },
    { ref: "paes", name: "Pães" },
    { ref: "bebidas", name: "Bebidas" },
  ];

  it("orders favourites first, then alphabetically (pt-BR)", () => {
    expect(orderCollections(collections, ["paes"]).map((c) => c.ref)).toEqual([
      "paes",
      "bebidas",
      "doces",
    ]);
  });

  it("filters by collection and query (name or sku)", () => {
    const products = [
      product({ sku: "PAO-FRANCES", name: "Pão Francês", collection_ref: "paes" }),
      product({ sku: "CROISSANT", name: "Croissant", collection_ref: "paes" }),
      product({ sku: "CAFE", name: "Café", collection_ref: "bebidas" }),
    ];
    expect(filterProducts(products, { collectionRef: "paes" }).map((p) => p.sku)).toEqual([
      "PAO-FRANCES",
      "CROISSANT",
    ]);
    expect(filterProducts(products, { query: "cafe" }).map((p) => p.sku)).toEqual(["CAFE"]);
    expect(filterProducts(products, { query: "croiss" }).map((p) => p.sku)).toEqual(["CROISSANT"]);
    expect(filterProducts(products, {}).length).toBe(3);
  });

  it("acha produto sem acento e prioriza início de palavra", () => {
    const products = [
      product({ sku: "TRUFA-PAPAIA", name: "Trufa de Papaia", collection_ref: "doces" }),
      product({ sku: "PAO-QUEIJO", name: "Pão de Queijo", collection_ref: "paes" }),
      product({ sku: "CAFE", name: "Café", collection_ref: "bebidas" }),
    ];
    // "pao" (sem acento) acha "Pão de Queijo"
    expect(filterProducts(products, { query: "pao" }).map((p) => p.sku)).toEqual(["PAO-QUEIJO"]);
    // "que" bate no início da palavra "Queijo"
    expect(filterProducts(products, { query: "que" }).map((p) => p.sku)).toEqual(["PAO-QUEIJO"]);
    // "pa": início de palavra ("Pão", "Papaia") vence quem só CONTÉM ("truPA" não existe,
    // mas "Trufa de Papaia" também tem palavra começando com "pa") — ambos aparecem,
    // com word-start primeiro na ordem original filtrada
    expect(filterProducts(products, { query: "pa" }).map((p) => p.sku)).toEqual([
      "TRUFA-PAPAIA",
      "PAO-QUEIJO",
    ]);
    // match só no MEIO da palavra vem depois do match em início de palavra
    const mixed = [
      product({ sku: "COMPADRE", name: "Compadre", collection_ref: "doces" }),
      product({ sku: "PAO-FORMA", name: "Pão de Forma", collection_ref: "paes" }),
    ];
    expect(filterProducts(mixed, { query: "pa" }).map((p) => p.sku)).toEqual([
      "PAO-FORMA",
      "COMPADRE",
    ]);
    expect(normalizeSearchText("Pão de Açúcar")).toBe("pao de acucar");
  });

  it("Enter na busca mira o primeiro resultado DISPONÍVEL (esgotado pula)", () => {
    const products = [
      product({ sku: "PAO-FRANCES", name: "Pão Francês", sold_out: true }),
      product({ sku: "PAO-QUEIJO", name: "Pão de Queijo" }),
      product({ sku: "PAO-FORMA", name: "Pão de Forma" }),
    ];
    // O primeiro da ordem está esgotado: Enter adiciona o próximo disponível.
    expect(enterTargetProduct(products, "pao")?.sku).toBe("PAO-QUEIJO");
    // Um único resultado disponível → é ele.
    expect(enterTargetProduct([product({ sku: "CAFE", name: "Café" })], "cafe")?.sku).toBe("CAFE");
    // Único resultado, mas esgotado → nada a adicionar.
    expect(enterTargetProduct([product({ sku: "CAFE", name: "Café", sold_out: true })], "cafe")).toBeNull();
    // Busca vazia não decide: Enter não adiciona o primeiro produto da grade.
    expect(enterTargetProduct(products, "")).toBeNull();
    expect(enterTargetProduct(products, "   ")).toBeNull();
    // Sem resultado algum → nada.
    expect(enterTargetProduct([], "xyz")).toBeNull();
  });

  it("o tile sem foto veste cor e ícone da coleção primária", () => {
    const p = product({
      sku: "BF",
      name: "Baguette",
      collection_ref: "rusticos",
      collection_color: "#B49B7F",
      collection_icon: "wheat",
    });
    // A cor sai como custom property; os tints (claro/escuro) são do CSS.
    expect(productFallbackStyle(p)).toEqual({ "--tile-color": "#B49B7F" });
    expect(productFallbackIcon(p)).toBe("lucide:wheat");
    // Sem configuração: nenhuma property (o CSS cai no par neutro) e ícone calmo.
    const bare = product({ sku: "Y", name: "" });
    expect(productFallbackStyle(bare)).toEqual({});
    expect(productFallbackIcon(bare)).toBe("lucide:package");
  });
});

describe("presentation/tabBoard — board shaping", () => {
  const tabs = [
    tab({ ref: "00001003", state: "empty", status_label: "Livre" }),
    tab({ ref: "00001001", state: "in_use", status_label: "Em uso", item_count: 2, total_display: "R$ 24,00", customer_name: "Ana" }),
    tab({ ref: "00001002", state: "in_use", status_label: "Em uso", item_count: 1, total_display: "R$ 8,00", fired: true }),
  ];

  it("sorts open tabs first, then numerically by display ref", () => {
    expect(sortTabs(tabs).map((t) => t.ref)).toEqual(["00001001", "00001002", "00001003"]);
  });

  it("filters and counts the in-use tabs", () => {
    expect(filterTabs(tabs, "in_use").map((t) => t.ref)).toEqual(["00001001", "00001002"]);
    expect(filterTabs(tabs, "all").length).toBe(3);
    expect(countOpenTabs(tabs)).toBe(2);
  });

  it("builds the per-tab card view", () => {
    const open = tabCardView(tabs[1]!, "00001001");
    expect(open).toMatchObject({
      displayRef: "00001001",
      isInUse: true,
      isFree: false,
      isUnpaid: false,
      pendingKitchen: true,
      identity: "Ana",
      summary: "2 itens · R$ 24,00",
      selected: true,
    });

    const free = tabCardView(tabs[0]!);
    expect(free).toMatchObject({ isFree: true, pendingKitchen: false, summary: "Comanda livre", identity: "Livre", selected: false });

    const fired = tabCardView(tabs[2]!);
    expect(fired).toMatchObject({ isUnpaid: true, pendingKitchen: false, summary: "1 item · R$ 8,00" });
  });

  it("filtra os cards pelo que o operador digita (nome/ref, sem acento)", () => {
    expect(filterTabsByQuery(tabs, "ana").map((t) => t.ref)).toEqual(["00001001"]);
    expect(filterTabsByQuery(tabs, "Anã").map((t) => t.ref)).toEqual(["00001001"]);
    expect(filterTabsByQuery(tabs, "1002").map((t) => t.ref)).toEqual(["00001002"]);
    expect(filterTabsByQuery(tabs, "").length).toBe(3);
    expect(filterTabsByQuery(tabs, "zzz")).toEqual([]);
  });

  it("aponta a próxima comanda numérica livre, com o padding do contrato", () => {
    // 1001 e 1002 em uso; 1003 livre → a próxima livre é a 1003.
    expect(nextFreeNumericTabRef(tabs, 8)).toBe("00001003");
    // Todas em uso → a seguinte à maior (nova).
    const allBusy = tabs.map((t) => ({ ...t, state: "in_use" }));
    expect(nextFreeNumericTabRef(allBusy, 8)).toBe("00001004");
    // Sem comanda numérica nenhuma → começa do 1.
    expect(nextFreeNumericTabRef([{ ref: "mesa-vip", state: "in_use" }], 4)).toBe("0001");
    expect(nextFreeNumericTabRef([], 0)).toBe("1");
  });

  it("sanitizes a tab ref to the channel's allowed shape", () => {
    const opts = { maxLength: 8, disallowedChars: ["/", "#"] };
    // Collapses runs of whitespace to one space (does not trim — faithful to the
    // original) and clamps to maxLength.
    expect(sanitizeTabRef("Mesa  12", opts)).toBe("Mesa 12");
    expect(sanitizeTabRef("a/b#c", opts)).toBe("abc");
    expect(sanitizeTabRef("123456789", opts)).toBe("12345678");
    expect(sanitizeTabRef("li\tn\ne", opts)).toBe("line");
  });
});

describe("presentation/numpad — quantity/discount buffer", () => {
  it("replaces on the first fresh keystroke, then appends up to maxLength", () => {
    expect(pushDigit("5", "3", { fresh: true, maxLength: 3 })).toBe("3");
    expect(pushDigit("3", "2", { fresh: false, maxLength: 3 })).toBe("32");
    expect(pushDigit("999", "1", { fresh: false, maxLength: 3 })).toBe("999");
    expect(pushDigit("12", "a", { fresh: false, maxLength: 3 })).toBe("12");
  });

  it("pops the last digit", () => {
    expect(popDigit("123")).toBe("12");
    expect(popDigit("")).toBe("");
  });

  it("clamps quantity and discount percentage", () => {
    expect(clampQty("500", 999)).toBe(500);
    expect(clampQty("1500", 999)).toBe(999);
    expect(clampQty("", 999)).toBe(0);
    expect(clampPercent("40")).toBe(40);
    expect(clampPercent("150")).toBe(100);
  });
});

describe("presentation/payment — tender math & method affordance", () => {
  it("drops the derived 'mixed' pseudo-method from the injectable buttons", () => {
    expect(injectableMethods(METHODS).map((method) => method.ref)).toEqual(["cash", "pix", "card"]);
  });

  it("offers 'Em conta' only for a customer with a house account", () => {
    expect(injectableMethods(METHODS, { houseAccount: true }).map((method) => method.ref)).toEqual([
      "cash", "pix", "card", "account",
    ]);
    expect(injectableMethods(METHODS, { houseAccount: false }).map((method) => method.ref)).toEqual(["cash", "pix", "card"]);
    expect(methodLabel("account", injectableMethods(METHODS, { houseAccount: true }))).toBe("Em conta");
  });

  it("resolves the method label and icon, with fallbacks", () => {
    expect(methodLabel("pix", METHODS)).toBe("PIX");
    // Ref cru nunca chega à tela: fallback pt-BR digno.
    expect(methodLabel("external", METHODS)).toBe("Outro meio");
    expect(methodLabel("unknown", METHODS)).toBe("Outro meio");
    expect(paymentIcon("cash")).toBe("lucide:banknote");
    expect(paymentIcon("weird")).toBe("lucide:wallet");
  });

  it("sums tenders and derives remaining/change/covered against the authoritative total", () => {
    const tenders = [tender("cash", 3000), tender("pix", 1000)];
    expect(tenderSumQ(tenders)).toBe(4000);
    expect(paymentRemainingQ(tenders, 5000)).toBe(1000);
    expect(paymentRemainingQ(tenders, 3500)).toBe(-500);
    expect(paymentChangeQ(tenders, 3500)).toBe(500);
    expect(paymentChangeQ(tenders, 5000)).toBe(0);
    expect(isPaymentCovered(tenders, 4000)).toBe(true);
    expect(isPaymentCovered(tenders, 5000)).toBe(false);
    expect(isPaymentCovered([], 0)).toBe(false);
  });

  // Troco sai da gaveta: só dinheiro em espécie recebido a mais é troco. Antes,
  // R$ 5.000,00 digitados na linha do cartão numa venda de R$ 42,00 faziam o PDV
  // mandar devolver R$ 4.958,00 de verdade.
  it("never turns a non-cash overpay into change", () => {
    const card = [tender("card", 500000)];
    expect(paymentChangeQ(card, 4200)).toBe(0);
    expect(nonCashExcessQ(card, 4200)).toBe(495800);

    const pix = [tender("pix", 10000)];
    expect(paymentChangeQ(pix, 4200)).toBe(0);
  });

  it("limits change to the cash share of a mixed payment", () => {
    const tenders = [tender("card", 4200), tender("cash", 1000)];
    expect(paymentChangeQ(tenders, 4200)).toBe(1000);
    expect(nonCashExcessQ(tenders, 4200)).toBe(0);
    expect(cashTenderSumQ(tenders)).toBe(1000);
  });

  it("aponta a falta quando o troco-para da entrega não cobre o total", () => {
    // Pedido de R$ 42,00; cliente diz que paga com R$ 40,00 → faltam R$ 2,00.
    expect(changeForShortfallQ(4000, 4200)).toBe(200);
    // Cobriu (ou sobrou): nada a avisar.
    expect(changeForShortfallQ(4200, 4200)).toBe(0);
    expect(changeForShortfallQ(5000, 4200)).toBe(0);
    // Opcional: vazio/zero não avisa.
    expect(changeForShortfallQ(0, 4200)).toBe(0);
  });

  it("shapes a tender line view", () => {
    expect(tenderLineView(tender("pix", 2599), METHODS)).toEqual({
      method: "pix",
      label: "PIX",
      icon: "lucide:qr-code",
      amountQ: 2599,
      amountDisplay: formatBRL(2599),
    });
  });

  it("o trilho de cédulas vem do contrato; sem contrato, as notas BR padrão", () => {
    const contract = { cash_tender_delta_presets_q: [0, 1000, 5000] } as POSCheckoutContractProjection;
    // Valores não-positivos do contrato não viram cédula.
    expect(cashNotesQ(contract)).toEqual([1000, 5000]);
    expect(cashNotesQ(null)).toEqual([200, 500, 1000, 2000, 5000, 10000]);
    expect(cashNotesQ()).toEqual([200, 500, 1000, 2000, 5000, 10000]);
    expect(cashNotesQ({ cash_tender_delta_presets_q: [] } as unknown as POSCheckoutContractProjection)).toEqual([200, 500, 1000, 2000, 5000, 10000]);
  });

  it("filters payment collections by fulfillment type", () => {
    const collections: POSPaymentCollectionProjection[] = [
      { ref: "terminal", label: "No balcão", description: "", fulfillment_types: ["pickup", "delivery"], payment_method_refs: [] },
      { ref: "on_delivery", label: "Na entrega", description: "", fulfillment_types: ["delivery"], payment_method_refs: [] },
    ];
    expect(collectionsForFulfillment(collections, "pickup").map((c) => c.ref)).toEqual(["terminal"]);
    expect(collectionsForFulfillment(collections, "delivery").map((c) => c.ref)).toEqual(["terminal", "on_delivery"]);
  });
});

describe("presentation/payment — digital proof (PCI SAQ A)", () => {
  it("returns null for cash or empty results", () => {
    expect(paymentProofView(null)).toBeNull();
    expect(paymentProofView(undefined)).toBeNull();
    expect(paymentProofView({ method: "cash" } as POSPaymentResultProjection)).toBeNull();
  });

  it("shapes a PIX proof with a render-ready QR src and copy-paste", () => {
    const proof = paymentProofView({
      method: "pix",
      amount_q: 5000,
      amount_display: "R$ 50,00",
      status: "pending",
      message: "Aguarde confirmação.",
      qr_code: "iVBORw0KGgo=",
      copy_paste: "00020126BR.GOV.BCB.PIX",
    } as POSPaymentResultProjection);
    expect(proof).not.toBeNull();
    expect(proof!.isPix).toBe(true);
    expect(proof!.tone).toBe("info");
    expect(proof!.qrCodeSrc).toBe("data:image/png;base64,iVBORw0KGgo=");
    expect(proof!.copyPaste).toBe("00020126BR.GOV.BCB.PIX");
    expect(proof!.hasProof).toBe(true);
  });

  it("shapes a card proof with a checkout link and never invents proof", () => {
    const proof = paymentProofView({
      method: "card",
      amount_q: 9900,
      amount_display: "R$ 99,00",
      status: "error",
      checkout_url: "https://checkout.stripe.com/x",
    } as POSPaymentResultProjection);
    expect(proof!.isCard).toBe(true);
    expect(proof!.tone).toBe("danger");
    expect(proof!.checkoutUrl).toBe("https://checkout.stripe.com/x");
    expect(proof!.qrCodeSrc).toBe("");
    expect(proof!.hasProof).toBe(true);
  });

  it("passes through data/http QR URIs and wraps bare base64", () => {
    expect(qrCodeSrc("")).toBe("");
    expect(qrCodeSrc("data:image/png;base64,abc")).toBe("data:image/png;base64,abc");
    expect(qrCodeSrc("https://x/qr.png")).toBe("https://x/qr.png");
    expect(qrCodeSrc("abc123")).toBe("data:image/png;base64,abc123");
  });
});

describe("presentation/cash — blind drawer shaping", () => {
  // O REF continua `sangria`/`suprimento` (identificador do domínio, viaja na
  // API); o RÓTULO diz a direção, porque quem confere o caixa lê a filipeta
  // dias depois e pode nunca ter ouvido a palavra "sangria".
  it("labels movement kinds with a fallback", () => {
    expect(movementLabel("sangria")).toBe("Saída de caixa");
    expect(movementLabel("suprimento")).toBe("Entrada de caixa");
    expect(movementLabel("custom")).toBe("custom");
  });

  it("formats the opening timestamp, falling back gracefully", () => {
    expect(formatOpenedAt(null)).toBe("—");
    expect(formatOpenedAt("")).toBe("—");
    expect(formatOpenedAt("not-a-date")).toBe("not-a-date");
    expect(formatOpenedAt("2026-06-06T13:05:00")).toMatch(/06\/06/);
  });

  it("requires an open shift for sale unless the contract opts out", () => {
    // Ausência da capability (ou da flag) = exigido — o default seguro.
    expect(requiresOpenShiftForSale(null)).toBe(true);
    expect(requiresOpenShiftForSale(undefined)).toBe(true);
    expect(requiresOpenShiftForSale({})).toBe(true);
    expect(requiresOpenShiftForSale({ requires_open_shift_for_sale: true })).toBe(true);
    expect(requiresOpenShiftForSale({ requires_open_shift_for_sale: false })).toBe(false);
  });

  it("derives the session lobby screen state from the runtime", () => {
    const base = { has_open_shift: false, shift_id: null, terminal_ref: "t1", terminal_label: "T1", operator_username: "", opened_at: "" } as POSCashRuntimeProjection;
    // Dois estados, nao tres. `occupied` existia quando a custodia era da
    // PESSOA: a segunda do balcao achava a gaveta ocupada por outra e ficava
    // presa sem vender. Com a custodia na gaveta, quem chega trabalha no turno
    // que ja esta aberto.
    expect(sessionScreenState(base, true)).toBe("open");
    expect(sessionScreenState(base, false)).toBe("closed");
  });

  // O motivo responde PARA ONDE o dinheiro foi (sangria) ou DE ONDE veio
  // (suprimento). Repetir o tipo no campo motivo é o que acontece quando a única
  // saída é digitar com a fila andando.
  // Os motivos vêm do SERVIDOR (capability `cash_management`). Repetir a lista
  // aqui daria dois donos para a mesma pergunta.
  const capacidade = {
    movement_reasons: { sangria: ["Sangria", "Fornecedor"], suprimento: [] },
  };

  it("offers the saída reasons the server sent", () => {
    expect(movementReasons(capacidade, "sangria")).toEqual(["Sangria", "Fornecedor"]);
  });

  // "Entrada de caixa" já é a resposta inteira. Um campo com uma opção só
  // ensina o balcão a preencher qualquer coisa para passar.
  it("asks nothing on the entrada side", () => {
    expect(movementReasons(capacidade, "suprimento")).toEqual([]);
  });

  // Sem capability (contrato antigo, servidor mudo) a tela cai no campo livre em
  // vez de esconder a única porta que sobrou.
  it("falls back to the free field when the server said nothing", () => {
    expect(movementReasons(null, "sangria")).toEqual([]);
    expect(movementReasons(capacidade, "custom")).toEqual([]);
  });

  // O motivo é exigência da SUPERFÍCIE (o servidor aceita `reason` vazio). Se este
  // gate afrouxar, passa sangria sem motivo e a trilha perde o que ela existe para
  // contar.
  it("requires kind, amount and reason before a movement can be registered", () => {
    expect(canRegisterMovement("sangria", "50", "Cofre")).toBe(true);
    expect(canRegisterMovement("", "50", "Cofre")).toBe(false);
    expect(canRegisterMovement("sangria", "", "Cofre")).toBe(false);
    expect(canRegisterMovement("sangria", "   ", "Cofre")).toBe(false);
    expect(canRegisterMovement("sangria", "50", "")).toBe(false);
    expect(canRegisterMovement("sangria", "50", "   ")).toBe(false);
  });

  // Movimento de zero não move nada; "1,2,3" colado virava "0" no servidor e
  // entrava calado na trilha. Agora o valor precisa ser legível E positivo.
  it("rejects a movement whose amount is illegible or zero", () => {
    expect(canRegisterMovement("sangria", "1,2,3", "Cofre")).toBe(false);
    expect(canRegisterMovement("sangria", "abc", "Cofre")).toBe(false);
    expect(canRegisterMovement("sangria", "0", "Cofre")).toBe(false);
    expect(canRegisterMovement("suprimento", "0,00", "")).toBe(false);
    expect(canRegisterMovement("suprimento", "25,00", "")).toBe(true);
  });
});

describe("presentation/cash — valores explícitos (abrir/fechar caixa)", () => {
  // "0" e "ilegível" são respostas diferentes: no fechamento, zero é gaveta
  // esvaziada; ilegível é pergunta sem resposta. `parseAmountToQ` esmaga os
  // dois em 0 (serve ao troco, que exige positivo); `amountToQ` os separa.
  it("amountToQ distingue zero de ilegível", () => {
    expect(amountToQ("120,50")).toBe(12050);
    expect(amountToQ("120.50")).toBe(12050);
    expect(amountToQ("0")).toBe(0);
    expect(amountToQ("0,00")).toBe(0);
    expect(amountToQ("")).toBeNull();
    expect(amountToQ("   ")).toBeNull();
    expect(amountToQ("1,2,3")).toBeNull();
    expect(amountToQ("abc")).toBeNull();
    expect(amountToQ("10,555")).toBeNull();
  });

  it("parseAmountToQ continua esmagando ilegível em 0 (contrato do troco)", () => {
    expect(parseAmountToQ("120,50")).toBe(12050);
    expect(parseAmountToQ("abc")).toBe(0);
  });

  // Campo vazio virava "0" calado no fechar caixa: o turno fechava com uma
  // contagem que ninguém fez. O CTA só arma com resposta explícita — e zero
  // digitado É resposta (abrir sem fundo, fechar gaveta esvaziada).
  it("abrir/fechar exigem valor explícito e legível; zero digitado vale", () => {
    expect(canSubmitCashAmount("200,00")).toBe(true);
    expect(canSubmitCashAmount("0")).toBe(true);
    expect(canSubmitCashAmount("")).toBe(false);
    expect(canSubmitCashAmount("   ")).toBe(false);
    expect(canSubmitCashAmount("1,2,3")).toBe(false);
  });

  // A mensagem inline só aparece quando HÁ texto e ele não é um valor: gritar
  // antes de a pessoa digitar é validação que atrapalha.
  it("amountInputError acusa só o texto ilegível", () => {
    expect(amountInputError("")).toBe("");
    expect(amountInputError("120,50")).toBe("");
    expect(amountInputError("0")).toBe("");
    expect(amountInputError("1,2,3")).not.toBe("");
    expect(amountInputError("abc")).not.toBe("");
  });

  it("formatAmountInput devolve o texto que o campo aceita de volta", () => {
    expect(formatAmountInput(12050)).toBe("120,50");
    expect(formatAmountInput(20000)).toBe("200,00");
    expect(formatAmountInput(0)).toBe("0,00");
    // Ida e volta estável: o que o contador escreve, o CTA aceita.
    expect(amountToQ(formatAmountInput(12345))).toBe(12345);
  });

  // O contador de denominações é AJUDA: qty ilegível ou vazia conta zero, e a
  // soma nunca trava a contagem de quem digita direto.
  it("denominationCountTotalQ soma qty × denominação, ignorando o ilegível", () => {
    expect(denominationCountTotalQ({})).toBe(0);
    expect(denominationCountTotalQ({ 2000: "2", 50: "3" })).toBe(4150);
    expect(denominationCountTotalQ({ 2000: "", 50: "abc" })).toBe(0);
    expect(denominationCountTotalQ({ 2000: "0" })).toBe(0);
    // "12abc" digitado num campo numérico: parseInt lê o prefixo — o campo já
    // filtra por pattern, isto é só a rede de baixo.
    expect(denominationCountTotalQ({ 100: "12" })).toBe(1200);
  });
});

describe("presentation/cash — pedido de troco (o dinheiro não anda)", () => {
  const denominacoes = {
    change_denominations: [
      { q: 2000, label: "20", shape: "note" as const },
      { q: 500, label: "5", shape: "note" as const },
      { q: 50, label: "0,50", shape: "coin" as const },
    ],
  };

  // A lista de dinheiro é do servidor. Se ela vivesse aqui, o dia em que uma
  // moeda saísse de circulação deixaria o pedido falando de dinheiro que não
  // existe — e ninguém descobriria pela tela.
  it("reads the denominations from the server, not from a local list", () => {
    expect(changeDenominations(denominacoes).map((d) => d.q)).toEqual([2000, 500, 50]);
    expect(changeDenominations(null)).toEqual([]);
  });

  // Antes havia um pedido "aproximado": quem ia ao cofre lia "moedas", tinha de
  // adivinhar quanto, e voltava com o que achou.
  it("always demands a real number — the value IS the request", () => {
    expect(canRequestChange("")).toBe(false);
    expect(canRequestChange("   ")).toBe(false);
    expect(canRequestChange("0")).toBe(false);
    expect(canRequestChange("abc")).toBe(false);
    expect(canRequestChange("50,00")).toBe(true);
    expect(canRequestChange("100")).toBe(true);
  });

  it("reads centavos the way the counter types them", () => {
    expect(parseAmountToQ("100")).toBe(10000);
    expect(parseAmountToQ("50,50")).toBe(5050);
    expect(parseAmountToQ("50.50")).toBe(5050);
    expect(parseAmountToQ("-5")).toBe(0);
    expect(parseAmountToQ("1,234")).toBe(0);
  });

  // "R$ 100 em notas de 5 e moedas de 0,50" é uma frase que se diz de verdade.
  it("summarises what was asked, and in what", () => {
    const base = {
      ref: "a1", amount_q: 10000, amount_display: "R$ 100,00",
      denominations: [500, 50], note: "", requested_by: "marina", requested_at: "",
    };
    expect(changeRequestSummary(base, denominacoes)).toBe("R$ 100,00 · em 5, 0,50");
  });

  // Sem denominação é um pedido INTEIRO, não um pedido pela metade: o gerente
  // resolve com o que houver no cofre.
  it("a bare value is a complete request", () => {
    const base = {
      ref: "a1", amount_q: 10000, amount_display: "R$ 100,00",
      denominations: [], note: "", requested_by: "marina", requested_at: "",
    };
    expect(changeRequestSummary(base, denominacoes)).toBe("R$ 100,00");
  });

  it("formats the request time, falling back gracefully", () => {
    expect(formatRequestedAt(null)).toBe("");
    expect(formatRequestedAt("")).toBe("");
    expect(formatRequestedAt("not-a-date")).toBe("not-a-date");
    expect(formatRequestedAt("2026-06-06T13:05:00")).toMatch(/13:05/);
  });
});

describe("presentation/managerAuth — o que se assina e quem assina", () => {
  // O motivo do SERVIDOR ganha do fixo do ato: quando a review disse por que
  // parou, é isso que o gerente precisa ler, não a frase genérica da exceção.
  it("prefers the review codes over the action's fixed reason", () => {
    expect(
      managerAuthReason({ action: "cash_out", reasons: ["discount_over_threshold"], thresholdQ: 5000 }),
    ).toBe(`Desconto acima de ${formatBRL(5000)}.`);
  });

  // ⚠️ Frase curta, sem explicação. A copy antiga explicava a política dentro do
  // diálogo ("Retirar dinheiro da gaveta é exceção auditada: um gerente precisa
  // autorizar") e o dono achou prolixo: quem está de pé com fila não lê parágrafo.
  it("a frase de cada ato é curta", () => {
    for (const acao of Object.keys(MANAGER_ACTIONS) as ManagerAction[]) {
      const frase = MANAGER_ACTIONS[acao].reason;
      expect(frase.length).toBeLessThanOrEqual(40);
      expect(frase).not.toContain(":");
    }
  });

  // O título nomeia O ATO — "Autorizar destrave da gaveta", não "Autorização".
  it("o título nomeia o ato", () => {
    expect(managerAuthTitle("drawer_unlock")).toBe("Autorizar destrave da gaveta");
    expect(managerAuthTitle(undefined)).toBe("Autorização do gerente");
  });

  it("spells out the review codes, threshold included", () => {
    const text = managerAuthReason({ reasons: ["discount_over_threshold"], thresholdQ: 1500 });
    expect(text).toContain("Desconto acima de");
    expect(text).toContain("15,00");
  });

  // ⚠️ Havia um segundo código, `price_override` — o operador digitava o preço à
  // mão. O mecanismo saiu inteiro: preço à mão não passava pela régua do
  // desconto (limite da loja, motivo, "maior desconto ganha") e tinha portão
  // próprio. Código sem tradução cai na frase genérica, que é o certo: dizer
  // pouco é melhor que dizer errado.
  it("um código que a tela não conhece cai no genérico, não inventa motivo", () => {
    expect(managerAuthReason({ reasons: ["price_override"] })).toBe("Precisa de um gerente.");
  });

  // Dizer pouco é melhor que dizer errado: o diálogo já afirmou "desconto acima de
  // R$ X" quando o gatilho era preço alterado, e o gerente assinou sem saber o quê.
  it("falls back to a generic line instead of guessing a reason", () => {
    expect(managerAuthReason({})).toBe("Precisa de um gerente.");
    expect(managerAuthReason({ reasons: ["codigo_desconhecido"] })).toBe("Precisa de um gerente.");
  });

  // Sem username o servidor não sabe contra QUAL credencial validar o PIN, e a
  // assinatura em `approved_by` sairia da pessoa errada.
});

describe("presentation/moveLines — move modes, gate & payload", () => {
  it("offers modes driven by the tab_manipulation capability", () => {
    expect(availableMoveModes({ allows_split: true, allows_transfer: true, allows_merge: true }).map((m) => m.ref))
      .toEqual(["split", "transfer", "merge"]);
    expect(availableMoveModes({ allows_split: true, allows_transfer: false, allows_merge: true }).map((m) => m.ref))
      .toEqual(["split", "merge"]);
    // Absent capability is defensive: offer all three so the dialog still works.
    expect(availableMoveModes(null).map((m) => m.ref)).toEqual(["split", "transfer", "merge"]);
  });

  it("flags price-freezing from the capability, defaulting to true", () => {
    expect(freezesPriceOnMove({ freezes_price_on_move: true })).toBe(true);
    expect(freezesPriceOnMove({ freezes_price_on_move: false })).toBe(false);
    expect(freezesPriceOnMove({})).toBe(true);
    expect(freezesPriceOnMove(null)).toBe(true);
  });

  it("addresses a line by server line_id, falling back to sku", () => {
    expect(moveLineId(cartItem({ sku: "CR", line_id: "L1" }))).toBe("L1");
    expect(moveLineId(cartItem({ sku: "CR" }))).toBe("CR");
  });

  it("needs line selection for split/transfer but not merge", () => {
    expect(modeNeedsSelection("split")).toBe(true);
    expect(modeNeedsSelection("transfer")).toBe(true);
    expect(modeNeedsSelection("merge")).toBe(false);
  });

  it("shapes a line view and selects ids in tab order", () => {
    const items = [
      cartItem({ sku: "CR", name: "Croissant", price_q: 800, qty: 2, line_id: "L1" }),
      cartItem({ sku: "PC", name: "Pão", price_q: 500, qty: 1, line_id: "L2" }),
    ];
    expect(moveLineView(items[0]!)).toEqual({ id: "L1", label: "2x Croissant", amountDisplay: formatBRL(1600) });
    expect(selectedLineIds(items, new Set(["L2"]))).toEqual(["L2"]);
    expect(selectedLineIds(items, new Set(["L2", "L1"]))).toEqual(["L1", "L2"]);
  });

  it("gates submit per mode", () => {
    const base = { selectedIds: ["L1"], splitRef: "1007/2", targetSessionKey: "s1", itemCount: 2, busy: false };
    expect(canSubmitMove({ ...base, mode: "split" })).toBe(true);
    expect(canSubmitMove({ ...base, mode: "split", splitRef: " " })).toBe(false);
    expect(canSubmitMove({ ...base, mode: "split", selectedIds: [] })).toBe(false);
    expect(canSubmitMove({ ...base, mode: "transfer" })).toBe(true);
    expect(canSubmitMove({ ...base, mode: "transfer", targetSessionKey: "" })).toBe(false);
    expect(canSubmitMove({ ...base, mode: "merge", selectedIds: [] })).toBe(true);
    expect(canSubmitMove({ ...base, mode: "merge", itemCount: 0 })).toBe(false);
    expect(canSubmitMove({ ...base, mode: "split", busy: true })).toBe(false);
  });

  it("builds the move payload per mode, or null when invalid", () => {
    const items = [cartItem({ sku: "CR", line_id: "L1" }), cartItem({ sku: "PC", line_id: "L2" })];
    expect(buildMovePayload({ mode: "split", items, selectedIds: ["L1"], splitRef: " 1007/2 ", targetSessionKey: "" }))
      .toEqual({ mode: "split", lineIds: ["L1"], toTabRef: "1007/2" });
    expect(buildMovePayload({ mode: "transfer", items, selectedIds: ["L1"], splitRef: "", targetSessionKey: "s1" }))
      .toEqual({ mode: "transfer", lineIds: ["L1"], toSessionKey: "s1" });
    expect(buildMovePayload({ mode: "merge", items, selectedIds: [], splitRef: "", targetSessionKey: "s1" }))
      .toEqual({ mode: "merge", lineIds: ["L1", "L2"], toSessionKey: "s1", closeSource: true });
    expect(buildMovePayload({ mode: "split", items, selectedIds: [], splitRef: "x", targetSessionKey: "" })).toBeNull();
    expect(buildMovePayload({ mode: "merge", items: [], selectedIds: [], splitRef: "", targetSessionKey: "s1" })).toBeNull();
  });

  it("lists destination tabs with a session, labelling by customer when present", () => {
    const tabs = [
      tab({ ref: "1007", display_ref: "1007", session_key: "s1", customer_name: "Maria" }),
      tab({ ref: "1011", display_ref: "1011", session_key: "s2" }),
      tab({ ref: "1099", display_ref: "1099", session_key: "" }),
    ];
    expect(moveTargetOptions(tabs)).toEqual([
      { sessionKey: "s1", label: "#1007 · Maria" },
      { sessionKey: "s2", label: "#1011" },
    ]);
    expect(defaultMoveTarget(tabs)).toBe("s1");
    expect(defaultMoveTarget([])).toBe("");
  });
});

describe("presentation/kitchen — fire-to-kitchen shaping", () => {
  it("counts fired vs unfired lines", () => {
    const items = [cartItem({ sku: "A", fired: true }), cartItem({ sku: "B" }), cartItem({ sku: "C" })];
    expect(firedCount(items)).toBe(1);
    expect(unfiredCount(items)).toBe(2);
    expect(allLinesFired(items)).toBe(false);
    expect(allLinesFired([cartItem({ sku: "A", fired: true })])).toBe(true);
    expect(allLinesFired([])).toBe(false);
  });

  it("a linha que CRESCEU depois de ir para a cozinha ainda tem o que enviar", () => {
    // ⚠️ O defeito que isto tranca: o PDV tem uma linha por SKU, então pedir
    // mais um chá aumenta a QUANTIDADE de uma linha já enviada. Enquanto a
    // conta era por linha, o botão dizia "Enviado" e o segundo chá nunca era
    // feito — o fire deduplicava por `line_id` e virava no-op.
    const meio = cartItem({ sku: "CHA", qty: 2, fired: true, fired_qty: 1 });
    expect(pendingKitchenQty(meio)).toBe(1);
    expect(unfiredCount([meio])).toBe(1);
    expect(allLinesFired([meio])).toBe(false);
    expect(kitchenBadge(meio)).toEqual({ label: "1 de 2 na cozinha", tone: "neutral" });

    const bar = fireBarView({ items: [meio], affordance: affordance(), hasOpenTab: true, busy: false });
    expect(bar.disabled).toBe(false);
    expect(bar.unfired).toBe(1);
  });

  it("a contagem é de UNIDADES, não de linhas", () => {
    // "Enviar 1" com três croissants pendentes é o número errado: o que a
    // cozinha vai fazer são três.
    const items = [cartItem({ sku: "CROISSANT", qty: 3 })];
    expect(unfiredCount(items)).toBe(3);
  });

  it("comanda sem `fired_qty` mantém o comportamento antigo", () => {
    // Payload de outra origem (ou comanda aberta antes desta mudança): linha
    // marcada como enviada conta como enviada inteira, nunca como pendente.
    const antiga = cartItem({ sku: "CHA", qty: 2, fired: true });
    expect(pendingKitchenQty(antiga)).toBe(0);
    expect(allLinesFired([antiga])).toBe(true);
  });

  it("derives per-line kitchen state", () => {
    expect(kitchenLineState(cartItem({ sku: "A" }), { canUnfire: true })).toBe("unfired");
    expect(kitchenLineState(cartItem({ sku: "A", fired: true, line_id: "L1" }), { canUnfire: true })).toBe("fired_cancellable");
    // Fired but no unfire affordance, or no line_id to target → non-interactive.
    expect(kitchenLineState(cartItem({ sku: "A", fired: true, line_id: "L1" }), { canUnfire: false })).toBe("fired");
    expect(kitchenLineState(cartItem({ sku: "A", fired: true }), { canUnfire: true })).toBe("fired");
  });

  it("linha que a cozinha já encerrou não oferece mais desfazer o envio", () => {
    // Desfazer o envio de algo que já saiu do fogão não é gesto de tela: é
    // conversa com quem está lá dentro. Oferecer o botão convidava o operador a
    // "cancelar" um prato pronto e achar que o cancelamento chegou.
    const pronto = cartItem({ sku: "A", fired: true, line_id: "L1", kitchen_status: "done" });
    const cancelado = cartItem({ sku: "A", fired: true, line_id: "L1", kitchen_status: "cancelled" });
    const preparando = cartItem({ sku: "A", fired: true, line_id: "L1", kitchen_status: "in_progress" });

    expect(kitchenLineState(pronto, { canUnfire: true })).toBe("fired");
    expect(kitchenLineState(cancelado, { canUnfire: true })).toBe("fired");
    expect(kitchenLineState(preparando, { canUnfire: true })).toBe("fired_cancellable");
  });

  it("o selo da linha segue o ticket, e a cor só aparece onde tem significado", () => {
    // "Na cozinha" era selo FIXO: o ticket virava pronto (ou era cancelado) e o
    // balcão seguia anunciando o estado do minuto do disparo.
    expect(kitchenBadge(cartItem({ sku: "A", fired: true }))).toEqual({ label: "Na cozinha", tone: "neutral" });
    expect(kitchenBadge(cartItem({ sku: "A", fired: true, kitchen_status: "pending" })))
      .toEqual({ label: "Na cozinha", tone: "neutral" });
    expect(kitchenBadge(cartItem({ sku: "A", fired: true, kitchen_status: "in_progress" })))
      .toEqual({ label: "Preparando", tone: "neutral" });
    expect(kitchenBadge(cartItem({ sku: "A", fired: true, kitchen_status: "done" })))
      .toEqual({ label: "Pronto", tone: "success" });
    expect(kitchenBadge(cartItem({ sku: "A", fired: true, kitchen_status: "cancelled" })))
      .toEqual({ label: "Cancelado na cozinha", tone: "destructive" });
  });

  it("shapes the fire bar: Action label + delta, all-fired state, disabled logic", () => {
    const items = [cartItem({ sku: "A", fired: true }), cartItem({ sku: "B" })];
    const bar = fireBarView({ items, affordance: affordance(), hasOpenTab: true, busy: false });
    expect(bar.visible).toBe(true);
    // A contagem saiu do RÓTULO e virou badge na tela — o texto do botão é o
    // que a Action manda, sem número colado.
    expect(bar.label).toBe("Enviar itens");
    expect(bar.unfired).toBe(1);
    expect(bar.disabled).toBe(false);

    const allFired = fireBarView({
      items: [cartItem({ sku: "A", fired: true })],
      affordance: affordance(),
      hasOpenTab: true,
      busy: false,
    });
    expect(allFired.label).toBe("Enviado");
    expect(allFired.allFired).toBe(true);
    expect(allFired.disabled).toBe(true); // nothing left to fire

    expect(fireBarView({ items, affordance: affordance({ present: false }), hasOpenTab: true, busy: false }).visible).toBe(false);
    expect(fireBarView({ items, affordance: affordance(), hasOpenTab: false, busy: false }).visible).toBe(false);
    expect(fireBarView({ items: [], affordance: affordance(), hasOpenTab: true, busy: false }).visible).toBe(false);
    expect(fireBarView({ items, affordance: affordance(), hasOpenTab: true, busy: true }).disabled).toBe(true);
    expect(fireBarView({ items, affordance: affordance({ enabled: false }), hasOpenTab: true, busy: false }).disabled).toBe(true);
  });
});

describe("presentation/selection — multi-select batch shaping", () => {
  const items = [
    cartItem({ sku: "A", line_id: "L1" }),
    cartItem({ sku: "B", line_id: "L2", fired: true }),
    cartItem({ sku: "C" }), // no line_id yet (unsaved)
  ];

  it("toggles a sku immutably", () => {
    const a = toggleSelected(new Set<string>(), "A");
    expect([...a]).toEqual(["A"]);
    const b = toggleSelected(a, "B");
    expect([...b].sort()).toEqual(["A", "B"]);
    expect([...toggleSelected(b, "A")].sort()).toEqual(["B"]);
    // original set is untouched (new Set each time)
    expect([...a]).toEqual(["A"]);
  });

  it("shapes the batch toolbar: counts, firable vs unfirable line_ids", () => {
    const view = selectionView(items, new Set(["A", "B", "C"]));
    expect(view.count).toBe(3);
    expect(view.skus.sort()).toEqual(["A", "B", "C"]);
    // A is unfired with a line_id → firable; C has no line_id → excluded.
    expect(view.firableLineIds).toEqual(["L1"]);
    expect(view.canFire).toBe(true);
    // B is fired with a line_id → unfirable.
    expect(view.unfirableLineIds).toEqual(["L2"]);
    expect(view.canUnfire).toBe(true);
  });

  it("empty selection has no batch affordances", () => {
    const view = selectionView(items, new Set());
    expect(view.count).toBe(0);
    expect(view.canFire).toBe(false);
    expect(view.canUnfire).toBe(false);
  });

  it("prunes selected skus no longer in the cart", () => {
    const pruned = pruneSelection(new Set(["A", "Z"]), items);
    expect([...pruned]).toEqual(["A"]);
  });

  it("selectedItems returns the cart items whose sku is selected", () => {
    expect(selectedItems(items, new Set(["A", "C"])).map((i) => i.sku)).toEqual(["A", "C"]);
    expect(selectedItems(items, new Set())).toEqual([]);
    expect(selectedItems(items, new Set(["Z"]))).toEqual([]);
  });
});

describe("presentation/receipt — print shaping (D3)", () => {
  const snap: PosReceiptSnapshot = {
    orderRef: "PED-1",
    tabDisplay: "1007",
    customerName: "João",
    items: [
      { name: "Croissant", qty: 2, price_q: 1300, discountPct: 0 },
      { name: "Café", qty: 1, price_q: 1000, discountPct: 10 },
    ],
    totalDisplay: "R$ 35,00",
    payments: [{ method: "cash", amount_q: 3500 }],
    fulfillmentLabel: "Retirada",
    printedAtMs: 0,
  };

  it("applies per-line discount to the net line total", () => {
    expect(receiptLineTotalQ(snap.items[0]!)).toBe(2600); // no discount
    expect(receiptLineTotalQ(snap.items[1]!)).toBe(900); // 10% off 1000
  });

  it("shapes receipt lines with unit and net total displays", () => {
    const lines = receiptLines(snap);
    expect(lines[0]).toMatchObject({ name: "Croissant", qty: 2, totalDisplay: formatBRL(2600), discountPct: 0 });
    expect(lines[1]).toMatchObject({ name: "Café", totalDisplay: formatBRL(900), discountPct: 10 });
  });

  it("labels payments from the method projection", () => {
    const methods = [{ ref: "cash", label: "Dinheiro", icon: "", requires_change: true }] as any;
    expect(receiptPayments(snap, methods)).toEqual([{ label: "Dinheiro", amountDisplay: formatBRL(3500) }]);
  });
});

describe("troco não é sangria", () => {
  it("nenhum motivo de sangria oferece trocar nota", () => {
    // Trocar uma nota não muda o dinheiro que existe na gaveta: saem R$ 50,
    // entram 5×R$ 10. Lançar como sangria derruba o esperado por um dinheiro
    // que nunca saiu, e o turno fecha com falta fantasma se ninguém lembrar do
    // suprimento gêmeo. Gaveta que abre sem mover dinheiro é "abrir sem venda".
    expect(movementReasons("sangria").some((r) => /troco/i.test(r))).toBe(false);
  });

  it("o ajuste não existe mais e não devolve motivo nenhum", () => {
    expect(movementReasons("ajuste")).toEqual([]);
  });
});


describe("atalhos das formas de pagamento", () => {
  const m = (ref: string, label: string) => ({ ref, label }) as never;

  it("as quatro formas do balcão têm tecla, e nenhuma disputa a do vizinho", () => {
    // ⚠️ A tecla era DERIVADA da inicial do rótulo, e a derivação morreu no dia
    // em que o balcão passou a distinguir crédito de débito: "Dinheiro" e
    // "Débito" disputam o D, "Cartão" e "Crédito" disputam o C. Quem chegasse
    // depois ficava mudo, sem nada na tela dizendo por quê. O dinheiro virou R,
    // de Reais, e o D ficou com o débito.
    expect(methodShortcuts([
      m("cash", "Dinheiro"),
      m("pix", "Pix"),
      m("credit", "Crédito"),
      m("debit", "Débito"),
    ])).toEqual({ cash: "R", pix: "P", credit: "C", debit: "D" });
  });

  it("a tecla vem do REF, não do rótulo — renomear a forma não move a tecla", () => {
    // O músculo do operador é da tecla, não da palavra. Se a casa resolver
    // chamar de "Cartão de crédito", o C continua sendo o C.
    expect(methodShortcuts([m("credit", "Cartão de crédito")])).toEqual({ credit: "C" });
    expect(methodShortcuts([m("cash", "Espécie")])).toEqual({ cash: "R" });
  });

  it("forma fora do mapa cai na inicial do rótulo, como antes", () => {
    // "Em conta" (E) é o caso vivo: só aparece para cliente com conta na casa.
    expect(methodShortcuts([m("account", "Em conta")])).toEqual({ account: "E" });
  });

  it("colisão ainda deixa o segundo SEM atalho, nunca com o do vizinho", () => {
    // Melhor sem tecla do que com uma que lança a forma errada com o cliente na
    // frente. `card` e `credit` compartilham o C de propósito — eles nunca
    // aparecem juntos, porque o balcão só oferece um dos dois.
    const keys = methodShortcuts([m("credit", "Crédito"), m("card", "Cartão")]);
    expect(keys).toEqual({ credit: "C" });
    expect(keys.card).toBeUndefined();
  });
});

describe("dividir a conta — a máquina faz a conta, não o operador", () => {
  it("dois iguais numa conta par", () => {
    expect(splitShareQ(10000, 2, 0, 10000)).toBe(5000);
    expect(splitShareQ(10000, 2, 1, 5000)).toBe(5000);
  });

  it("os centavos FECHAM numa conta que não divide redondo", () => {
    // 100,00 ÷ 3. Três vezes 33,33 deixaria um centavo órfão para o operador
    // caçar com três clientes olhando.
    const total = 10000;
    let restante = total;
    const parcelas: number[] = [];
    for (let i = 0; i < 3; i++) {
      const parcela = splitShareQ(total, 3, i, restante);
      parcelas.push(parcela);
      restante -= parcela;
    }
    // O centavo sobrando cai na parcela do MEIO — consequência da acumulação
    // (round(10000·2/3) = 6667). Onde ele cai não importa; que a soma feche, sim.
    expect(parcelas).toEqual([3333, 3334, 3333]);
    expect(parcelas.reduce((a, b) => a + b, 0)).toBe(total);
    expect(restante).toBe(0);
  });

  it("fecha para qualquer total e qualquer número de pessoas", () => {
    for (const total of [1, 99, 4245, 9945, 123457]) {
      for (const n of [2, 3, 4, 5, 6, 7]) {
        let restante = total;
        for (let i = 0; i < n; i++) restante -= splitShareQ(total, n, i, restante);
        expect(restante).toBe(0);
      }
    }
  });

  it("a ÚLTIMA parcela leva o que restou, mesmo depois de o operador editar", () => {
    // "Esse aqui paga os R$ 50, o resto divide": a primeira linha foi editada
    // para 5000 num total de 9945, dividido em 3.
    const total = 9945;
    // já existem 2 linhas somando 5000 + 2000 → faltam 2945
    expect(splitShareQ(total, 3, 2, 2945)).toBe(2945);
  });

  it("nunca lança mais do que falta", () => {
    expect(splitShareQ(10000, 4, 0, 900)).toBe(900);
  });

  it("sem divisão, a próxima linha é o restante inteiro", () => {
    expect(splitShareQ(10000, 1, 0, 10000)).toBe(10000);
    expect(splitShareQ(10000, 0, 0, 7000)).toBe(7000);
  });

  it("total já coberto não lança nada", () => {
    expect(splitShareQ(10000, 3, 1, 0)).toBe(0);
  });
});

describe("splitHint — quanto pedir a quem está na frente", () => {
  it("manda FAZER, e diz de quem é a vez", () => {
    // ⚠️ `formatBRL` separa com espaço NÃO-QUEBRÁVEL. Comparar com um espaço
    // comum passa despercebido na leitura e reprova no runner.
    // O verbo entrou quando a frase virou a instrução do rodapé do checkout,
    // lida de longe e dita em voz alta: "R$ 33,15 · pessoa 1 de 3" é etiqueta de
    // mostrador; "Peça R$ 33,15" é o que fazer agora.
    expect(splitHint(9945, 3, 0, 9945)).toBe(`Peça ${formatBRL(3315)} · pessoa 1 de 3`);
    expect(splitHint(9945, 3, 1, 6630)).toBe(`Peça ${formatBRL(3315)} · pessoa 2 de 3`);
  });

  it("coberto, avisa que acabou", () => {
    expect(splitHint(9945, 3, 3, 0)).toBe("Dividido em 3. Total coberto.");
  });

  it("sem divisão, sem frase", () => {
    expect(splitHint(9945, 1, 0, 9945)).toBe("");
  });
});

describe("cashLandedInDrawer — a gaveta só abre com dinheiro que ENTROU nela", () => {
  // ⚠️ A pergunta parece "teve dinheiro?" e não é: é "teve dinheiro AQUI?".
  // Numa entrega paga na porta o operador ainda precisa lançar uma linha de
  // dinheiro para liberar o Validar — e a gaveta do balcão chutava e abria com o
  // dinheiro ainda na rua. Gaveta aberta sem motivo é caixa exposto.
  const linha = (method: string, collection?: string) => ({ method, amount_q: 1000, collection });

  it("dinheiro no terminal abre", () => {
    expect(cashLandedInDrawer([linha("cash", "terminal")])).toBe(true);
  });

  it("dinheiro NA PORTA não abre", () => {
    expect(cashLandedInDrawer([linha("cash", "on_delivery")])).toBe(false);
  });

  it("misto com uma parte na gaveta abre", () => {
    expect(cashLandedInDrawer([linha("card", "terminal"), linha("cash", "terminal")])).toBe(true);
  });

  it("cartão e Pix nunca abrem", () => {
    expect(cashLandedInDrawer([linha("card", "terminal"), linha("pix", "terminal")])).toBe(false);
  });

  it("sem coleta declarada, dinheiro é dinheiro na gaveta (o padrão do balcão)", () => {
    expect(cashLandedInDrawer([linha("cash")])).toBe(true);
  });

  it("venda sem pagamento nenhum não abre", () => {
    expect(cashLandedInDrawer([])).toBe(false);
  });
});

describe("formas de pagamento do balcão — o que vai ao gateway e o que não vai", () => {
  const m = (ref: string, label: string) => ({ ref, label }) as never;

  it("as cinco formas do balcão têm tecla própria", () => {
    expect(methodShortcuts([
      m("cash", "Dinheiro"),
      m("pix", "Pix"),
      m("credit", "Crédito"),
      m("debit", "Débito"),
      m("link", "Link de pagamento"),
    ])).toEqual({ cash: "R", pix: "P", credit: "C", debit: "D", link: "L" });
  });

  it("crédito e débito NÃO têm comprovante remoto — a maquininha é física", () => {
    // A prova deles é o papel que a maquininha imprime. Oferecer um QR ou um
    // link ali seria a tela prometendo uma cobrança que não existe.
    for (const method of ["credit", "debit", "cash"]) {
      expect(paymentProofView({ method, status: "pending" } as never)).toBeNull();
    }
  });

  it("o LINK tem comprovante: é uma URL para o cliente abrir depois", () => {
    // Ele é o oposto do cartão de balcão — não há maquininha, há gateway, e o
    // dinheiro chega quando o cliente paga.
    const proof = paymentProofView({
      method: "link",
      status: "pending",
      checkout_url: "https://pay.example.com/abc",
      amount_display: "R$ 63,00",
    } as never);
    expect(proof).not.toBeNull();
    expect(proof!.isPix).toBe(false);
    expect(proof!.isLink).toBe(true);
    // ⚠️ NÃO é `isCard`. O cartão da loja online ABRE o checkout numa aba — faz
    // sentido lá, onde quem está na frente da tela é quem compra. No balcão quem
    // está na frente é o OPERADOR, e abrir a página de pagamento ali significaria
    // ele digitando o cartão do cliente — o oposto do que a maquininha existe
    // para evitar. O link é para ENTREGAR: copiar e mandar.
    expect(proof!.isCard).toBe(false);
    expect(proof!.checkoutUrl).toBe("https://pay.example.com/abc");
    expect(proof!.hasProof).toBe(true);
  });

  it("o cartão da loja online continua sendo para ABRIR, não para entregar", () => {
    const proof = paymentProofView({
      method: "card", status: "pending", checkout_url: "https://pay.stripe.com/x",
    } as never);
    expect(proof!.isCard).toBe(true);
    expect(proof!.isLink).toBe(false);
  });
});

describe("vale até — o prazo do link, dito como o operador diz", () => {
  // Terça, 2 de setembro de 2026, 15:00 no fuso local da tela.
  const agora = new Date(2026, 8, 2, 15, 0, 0);
  const local = (y: number, m: number, d: number, h: number, min = 0) => new Date(y, m - 1, d, h, min).toISOString();

  it("hoje, amanhã, e depois o dia da semana com a data curta", () => {
    expect(paymentDeadlineLabel(local(2026, 9, 2, 18), agora)).toBe("hoje às 18h");
    expect(paymentDeadlineLabel(local(2026, 9, 3, 9), agora)).toBe("amanhã às 9h");
    expect(paymentDeadlineLabel(local(2026, 9, 5, 14), agora)).toBe("sáb. 5/9 às 14h");
    expect(paymentDeadlineLabel(local(2026, 9, 10, 8), agora)).toBe("qui. 10/9 às 8h");
  });

  it("minuto só aparece quando não é cheio", () => {
    expect(paymentDeadlineLabel(local(2026, 9, 3, 9, 30), agora)).toBe("amanhã às 9h30");
    expect(paymentDeadlineLabel(local(2026, 9, 3, 0, 5), agora)).toBe("amanhã às 0h05");
  });

  it("'amanhã' é o dia civil seguinte, não 'daqui a 24 h'", () => {
    // Às 23h, um link que vence à 0h30 já é amanhã — e o das 15h de amanhã também.
    const tarde = new Date(2026, 8, 2, 23, 0, 0);
    expect(paymentDeadlineLabel(local(2026, 9, 3, 0, 30), tarde)).toBe("amanhã às 0h30");
    expect(paymentDeadlineLabel(local(2026, 9, 3, 15), tarde)).toBe("amanhã às 15h");
  });

  it("lê o ISO com fuso do servidor e traduz para a hora local da tela", () => {
    // O servidor grava tz-aware (UTC); a tela fala na hora do balcão.
    const utc = new Date(2026, 8, 3, 9, 0, 0).toISOString();
    expect(paymentDeadlineLabel(utc, agora)).toBe("amanhã às 9h");
  });

  it("sem prazo (ou lixo), sem frase", () => {
    expect(paymentDeadlineLabel("", agora)).toBe("");
    expect(paymentDeadlineLabel("ontem", agora)).toBe("");
  });

  it("o comprovante do LINK carrega o prazo; o do Pix, não", () => {
    const link = paymentProofView({
      method: "link",
      status: "pending",
      checkout_url: "https://pay.example.com/abc",
      expires_at: local(2026, 9, 3, 9),
    } as never, agora);
    expect(link!.expiresDisplay).toBe("amanhã às 9h");

    const pix = paymentProofView({
      method: "pix",
      status: "pending",
      copy_paste: "000201",
      expires_at: local(2026, 9, 2, 15, 30),
    } as never, agora);
    expect(pix!.expiresDisplay).toBe("");

    const semPrazo = paymentProofView({
      method: "link",
      status: "pending",
      checkout_url: "https://pay.example.com/abc",
    } as never, agora);
    expect(semPrazo!.expiresDisplay).toBe("");
  });
});

describe("a maquininha e as cédulas", () => {
  const linha = (method: string) => ({
    method,
    label: method,
    icon: "lucide:credit-card",
    amountQ: 2500,
    amountDisplay: "R$ 25,00",
  });

  it("só crédito e débito pedem conferência na maquininha", () => {
    // Pix, dinheiro e link não passam por terminal físico: pedir confirmação
    // neles seria um clique a mais em todo atendimento do balcão.
    const lines = [linha("cash"), linha("credit"), linha("pix"), linha("debit"), linha("link")];
    expect(machineTenderLines(lines).map((l) => l.method)).toEqual(["credit", "debit"]);
  });

  it("cédula perde o centavo, preset quebrado o mantém", () => {
    expect(cashNoteLabel(200)).toBe("R$ 2");
    expect(cashNoteLabel(10000)).toBe("R$ 100");
    expect(cashNoteLabel(250)).toBe(formatBRL(250));
  });
});
