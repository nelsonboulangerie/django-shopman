import type { PosPaymentCollection, PosPaymentMethod } from "~/generated/posContract";

export interface Action {
  ref: string;
  kind: string;
  label: string;
  priority: "primary" | "secondary" | "quiet" | string;
  enabled: boolean;
  reason: string;
  href: string;
  method: string;
  payload_schema: Record<string, unknown>;
  idempotency: string;
  confirmation: Record<string, unknown>;
}

export interface POSProductProjection {
  sku: string;
  name: string;
  price_q: number;
  price_display: string;
  collection_ref: string;
  image_url: string;
  /** Esgotado no escopo do canal do PDV: tile visível porém inerte. */
  sold_out?: boolean;
}

export interface POSCollectionProjection {
  ref: string;
  name: string;
}

export interface POSPaymentMethodProjection {
  ref: PosPaymentMethod | string;
  label: string;
}

export interface POSFulfillmentOptionProjection {
  ref: "pickup" | "delivery";
  label: string;
  description: string;
  requires_address: boolean;
}

export interface POSPaymentCollectionProjection {
  ref: PosPaymentCollection;
  label: string;
  description: string;
  fulfillment_types: Array<"pickup" | "delivery">;
  payment_method_refs: string[];
}

export interface POSCheckoutOptionProjection {
  ref: string;
  label: string;
  description: string;
}

export interface POSCheckoutFieldProjection {
  ref: string;
  payload_key: string;
  section_ref: string;
  label: string;
  input_type: string;
  required: boolean;
  required_when: Record<string, unknown>;
  placeholder: string;
  help_text: string;
  max_length: number;
  options: POSCheckoutOptionProjection[];
  capability_ref: string;
}

export interface POSCheckoutSectionProjection {
  ref: string;
  label: string;
  description: string;
  field_refs: string[];
}

// Sub-objetos do mapa `capabilities` do contrato de checkout. Só os campos que a
// superfície lê são tipados; o index signature preserva as demais chaves (o servidor
// pode carregar mais) e mantém cada capability atribuível a `Record<string, unknown>`.
/** Uma cédula ou moeda que o balcão pode pedir como troco. */
export interface POSChangeDenomination {
  /** Valor em centavos — é o que viaja na API. */
  q: number;
  /** Como se lê no botão: "20", "0,50". */
  label: string;
  /** Só o desenho do botão: cédula é retangular, moeda é redonda. */
  shape: "note" | "coin";
}

export interface POSCashManagementCapability {
  movement_kinds?: string[];
  /**
   * Motivos por tipo de movimento. SAÍDA pergunta para onde o dinheiro foi;
   * ENTRADA vem com lista vazia de propósito — "entrada de caixa" já é a
   * resposta inteira. Quem exige o motivo da saída é o servidor.
   */
  movement_reasons?: Record<string, string[]>;
  /** A lista vem do SERVIDOR para não existirem duas listas de dinheiro. */
  change_denominations?: POSChangeDenomination[];
  requires_open_shift_for_sale?: boolean;
  [key: string]: unknown;
}
export interface POSKitchenHandoffCapability {
  fire_action_ref?: string;
  [key: string]: unknown;
}
export interface POSTabManipulationCapability {
  rename_action_ref?: string;
  [key: string]: unknown;
}
export interface POSSaleCorrectionCapability {
  cancel_recent_action_ref?: string;
  max_age_minutes?: number;
  [key: string]: unknown;
}
export interface POSCheckoutCapabilities {
  cash_management?: POSCashManagementCapability | null;
  kitchen_handoff?: POSKitchenHandoffCapability | null;
  tab_manipulation?: POSTabManipulationCapability | null;
  sale_correction?: POSSaleCorrectionCapability | null;
  [key: string]: unknown;
}

export interface POSCheckoutContractProjection {
  intent_version: string;
  allowed_payload_keys: string[];
  sections: POSCheckoutSectionProjection[];
  fields: POSCheckoutFieldProjection[];
  receipt_channels: POSCheckoutOptionProjection[];
  tender_methods: POSCheckoutOptionProjection[];
  cash_tender_delta_presets_q: number[];
  discount_types: POSCheckoutOptionProjection[];
  discount_reasons: POSCheckoutOptionProjection[];
  customer_memory_actions: POSCheckoutOptionProjection[];
  // O tipo detalhado existia e não estava ligado aqui: `Record<string, unknown>`
  // fazia cada leitura virar `unknown` e obrigava um cast na chamada. O gate da
  // antesala ("sem turno aberto não há venda") lia daí — se o contrato mudasse a
  // chave, ele receberia `undefined` em silêncio e a antesala nunca dispararia.
  capabilities: POSCheckoutCapabilities;
}

/**
 * Um pedido de troco pendente, à espera de alguém trazer.
 *
 * O troco não sai andando: o operador pede, o gerente traz, e a troca acontece
 * no balcão à vista de todos. Nada aqui é dinheiro do fechamento — trocar é net
 * zero, o total da gaveta não muda.
 */
export interface POSChangeRequestProjection {
  ref: string;
  amount_q: number;
  /** Vazio só em linha antiga do livro — o livro é imutável e guarda o que já foi. */
  amount_display: string;
  /** Cédulas/moedas pedidas, em centavos, do maior para o menor. Vazio = "me traz o valor". */
  denominations: number[];
  note: string;
  requested_by: string;
  requested_at: string;
}

/**
 * Um pedido cancelado cujo dinheiro ainda não saiu de nenhuma gaveta.
 *
 * Cancelar não é devolver: o gestor cancela às 22h e ninguém abriu gaveta. A
 * pendência fica na antesala até alguém com turno aberto entregar as notas.
 */
export interface POSPendingCashRefundProjection {
  order_ref: string;
  amount_q: number;
  amount_display: string;
  customer_name: string;
  cancelled_at: string;
}

/**
 * Um cliente com conta na casa e saldo em aberto (Σ das vendas "em conta" ainda
 * não acertadas, derivado do Payman; nunca tabela de saldo).
 */
export interface POSAccountBalanceProjection {
  customer_ref: string;
  customer_name: string;
  balance_q: number;
  balance_display: string;
  intents: number;
  oldest_at: string;
}

export interface POSCashRuntimeProjection {
  has_open_shift: boolean;
  shift_id: number | null;
  terminal_ref: string;
  terminal_label: string;
  operator_username: string;
  opened_at: string;
  status?: "open" | "closed" | string;
  /**
   * Pode ver a APURAÇÃO (esperado, contado, diferença, faturamento)?
   *
   * `false` para quase todo mundo, de propósito — inclusive para o gerente.
   * Quem sabe o esperado não conta às cegas: confere um gabarito.
   */
  can_audit_cash?: boolean;
  /** Só os PENDENTES: atendido e cancelado ficam na trilha do turno, não na tela. */
  pending_change_requests?: POSChangeRequestProjection[];
  /** Devoluções em dinheiro de vendas canceladas, à espera de uma gaveta aberta. */
  pending_cash_refunds?: POSPendingCashRefundProjection[];
  /** Contas na casa com saldo em aberto: quem está com a gaveta aberta recebe o acerto. */
  account_balances?: POSAccountBalanceProjection[];
  /**
   * Sugestão FIXA de fundo de troco para a abertura guiada (config do
   * terminal, escolhida pelo gestor no Admin). Nunca derivada do contado ou
   * do esperado de turnos — o regime de contagem cega não vaza por aqui.
   */
  default_float_q?: number;
  /** "R$ 200,00"; "" quando não configurado. */
  default_float_display?: string;
}

export interface POSAddressAutocompleteProjection {
  enabled: boolean;
  provider: "google_places" | string;
  public_api_key: string;
  language: string;
  region: string;
  countries: string[];
  types: string[];
  fields: string[];
  structured_fields: string[];
  reverse_geocode_action_ref: string;
  shop_latitude: number | null;
  shop_longitude: number | null;
  bias_radius_m: number;
}

export interface StructuredAddressProjection {
  formatted_address?: string;
  route?: string;
  street_number?: string;
  neighborhood?: string;
  city?: string;
  state?: string;
  state_code?: string;
  postal_code?: string;
  country?: string;
  country_code?: string;
  latitude?: number | null;
  longitude?: number | null;
  place_id?: string | null;
  complement?: string;
  delivery_instructions?: string;
  reference?: string;
  is_verified?: boolean;
}

export interface SavedAddressProjection extends StructuredAddressProjection {
  id: number;
  label: string;
  label_key: string;
  label_custom: string;
  formatted_address: string;
  complement: string;
  delivery_instructions: string;
  is_default: boolean;
}

export interface POSCustomerMemoryProjection {
  total_orders: number;
  average_order_display: string;
  favorite_product: string;
  favorite_item: Record<string, unknown>;
  last_order_items: Array<Record<string, unknown>>;
}

export interface POSCustomerLookupProjection {
  ref: string;
  name: string;
  phone: string;
  email: string;
  /** CPF/CNPJ do cadastro — valor padrão do "CPF na nota"; editável por venda. */
  tax_id: string;
  /** O cliente já optou antes: pré-marca o checkout (editável por venda). */
  fiscal_prefs: { cpf_na_nota?: boolean; email_receipt?: boolean };
  /** Observações do balcão — editável no painel do cliente. */
  notes: string;
  /** Restrições alimentares — dado de SEGURANÇA: chip de alerta. */
  dietary_restrictions: string;
  /** "15/05"; os bools dirigem o chip do mês e o aviso do DIA. */
  birthday_display: string;
  is_birthday_today: boolean;
  is_birthday_month: boolean;
  /** Promoção de aniversariante ATIVA (Core aplica sozinha no reprice). Vazio = nenhuma. */
  birthday_promo_label: string;
  /** A faixa de preço do cliente (`PriceTier.ref`) — é ela que decide o preço. */
  price_tier: string;
  is_staff: boolean;
  default_address: SavedAddressProjection | null;
  saved_addresses: SavedAddressProjection[];
  memory: POSCustomerMemoryProjection;
  /** Conta na casa: só o Admin liga; sem ela o PDV nem mostra "Em conta". */
  house_account?: boolean;
  /** Quanto o cliente deve hoje (centavos), quando tem conta. */
  account_balance_q?: number;
}

export interface POSCustomerLookupResponse {
  customer: POSCustomerLookupProjection | null;
  /** Só no resolve: o cadastro foi CRIADO agora (true) ou encontrado (false). */
  created?: boolean;
}

export interface POSCustomerSearchResult {
  ref: string;
  name: string;
  phone: string;
  document: string;
  email: string;
}

export interface POSCustomerSearchResponse {
  results: POSCustomerSearchResult[];
}

export interface POSTerminalComponentProjection {
  key: string;
  label: string;
  /**
   * `deferred` = a resposta existe, mas só a estação alcança quem a tem (o
   * agente do balcão vive na loopback do balcão). O servidor dizer `ready` aí
   * seria repetir a mentira antiga do adapter "simulated".
   */
  status: "ready" | "warning" | "error" | "absent" | "deferred" | string;
  message: string;
}

/** Como ESTE balcão abre a gaveta. `can_kick: false` = abre com a chave. */
export interface POSCashDrawerProjection {
  adapter: "manual" | "agent" | string;
  can_kick: boolean;
  open_on_cash_sale: boolean;
  /** Por que não dá, quando `can_kick` é false. A tela mostra em vez de sumir. */
  reason?: string;
  agent_url?: string;
  token?: string;
  pulse?: { pin: number; on_ms: number; off_ms: number };
}

export interface POSOperatorProjection {
  id: number;
  username: string;
  name: string;
}

/** Quem pode ASSINAR uma exceção (sangria, desconto acima do teto).
 *
 * Só identidade: o `username` é o que o servidor exige no contrato
 * `{username, pin}` da aprovação. A projection não publica id nem e-mail, e a
 * tela não tem por que pedi-los. */
export interface POSManagerProjection {
  username: string;
  name: string;
}

export interface POSProjection {
  products: POSProductProjection[];
  collections: POSCollectionProjection[];
  payment_methods: POSPaymentMethodProjection[];
  fulfillment_options: POSFulfillmentOptionProjection[];
  payment_collections: POSPaymentCollectionProjection[];
  checkout: POSCheckoutContractProjection;
  actions: Action[];
  has_open_cash_session: boolean;
  cash_runtime: POSCashRuntimeProjection;
  terminal_ref: string;
  terminal_label: string;
  terminal_default_fulfillment_type: "pickup" | "delivery" | string;
  terminal_health_status: "ready" | "warning" | "error" | string;
  terminal_components: POSTerminalComponentProjection[];
  cash_drawer?: POSCashDrawerProjection;
  favorite_collection_refs: string[];
  delivery_minimum_q: number;
  delivery_minimum_display: string;
  fiscal_status: "ready" | "warning" | "error" | string;
  fiscal_label: string;
  fiscal_message: string;
  /** A nota na tela (host do Django) abre para QUEM está logado? O servidor
   * decide; a tela não renderiza porta que devolve 404. É consulta — a via do
   * cliente sai na bobina, e essa não depende deste gate. */
  danfe_screen_allowed: boolean;
  /** Hoje pelo relógio da LOJA — o padrão da data de entrega. */
  delivery_today: string;
  /** As janelas de hoje, para o formulário abrir já respondendo. A review
   * assume quando o operador escolhe OUTRA data. */
  delivery_slots_today: Array<{ ref: string; label: string }>;
  operators: POSOperatorProjection[];
  managers: POSManagerProjection[];
  auto_lock_seconds: number;
  // Geometria do rolo declarada pelo terminal; 0 = não declarou e vale o default
  // do print CSS (80mm). Ver presentation/printGeometry.
  terminal_roll_width_mm: number;
  terminal_roll_margin_mm: number;
  // Nome fantasia da loja (Shop singleton): a tela do cliente dá as boas-vindas
  // em nome da LOJA, não do terminal.
  shop_name: string;
}

export interface POSShiftSummaryProjection {
  count: number;
  total_display: string;
  pickup_count: number;
  delivery_count: number;
  last_ref: string;
  last_total_display: string;
  cod_pending_count: number;
  cod_pending_display: string;
}

export interface POSTabProjection {
  ref: string;
  display_ref: string;
  session_key: string;
  state: "empty" | "in_use" | string;
  status_label: string;
  status_class: string;
  customer_name: string;
  customer_phone: string;
  item_count: number;
  line_count: number;
  total_display: string;
  last_touched_display: string;
  items_preview: string;
  fired?: boolean;
}

export interface POSResponse {
  pos: POSProjection;
  shift: POSShiftSummaryProjection;
  tabs: POSTabProjection[];
  operator: POSOperatorProjection | null;
  // O operador ativo recebeu um PIN temporário (reset do gerente) e precisa
  // trocá-lo antes de operar — a lock screen força a troca quando true.
  pin_must_change: boolean;
}

export interface POSCartItem {
  sku: string;
  name: string;
  price_q: number;
  qty: number;
  notes: string;
  line_id?: string;
  fired?: boolean;
  /** Em que pé a COZINHA está com este SKU nesta comanda: "" (nada disparado),
   *  "pending", "in_progress", "done", "cancelled". Vem do ticket do KDS e chega
   *  por push (canal SSE `tabs`) — o selo da linha segue o ticket em vez de
   *  congelar no estado do minuto do disparo. */
  kitchen_status?: string;
  discount?: { value: number; reason: string };
  /** Desconto AUTOMÁTICO de pricing que venceu a linha (lote/liquidação, happy
   *  hour, funcionário), carimbado pelo kernel e exposto pelo payload da
   *  comanda. Informativo: o `price_q` da linha já vem reduzido. */
  pricing_discount?: { type: string; label: string; amount_q: number; percent: number } | null;
  /** Preço de ETIQUETA por unidade, antes de qualquer desconto. Igual a
   *  `charged_price_q` quando não houve desconto nenhum. */
  list_price_q?: number;
  /** O que se COBRA por unidade, depois de todos os descontos (automático e
   *  manual). ⚠️ Não é `price_q`: aquele é o número de restauração — pré-desconto
   *  manual — e com desconto na linha ele é MAIOR do que o cliente paga. */
  charged_price_q?: number;
  /** Operator overrode the unit price (numpad "Preço"): the kernel freezes it and
   *  the server review requires manager approval. Survives persist→reload. */
  price_overridden?: boolean;
}

export interface POSPaymentTenderDraft {
  method: string;
  amount_q: number;
  collection: PosPaymentCollection;
  reference?: string;
  /** Internal: amount is still the untouched system auto-fill (first cédula
   *  replaces it). Stripped before the intent — never sent to the server. */
  _virgin?: boolean;
}

export interface POSTabPayload {
  session_key: string;
  tab_session_key: string;
  tab_ref: string;
  tab_display: string;
  items: POSCartItem[];
  customer_phone: string;
  customer_name: string;
  customer_ref: string;
  price_tier?: string;
  customer_tax_id: string;
  customer_email: string;
  fulfillment_type: "pickup" | "delivery";
  delivery_address: string;
  delivery_address_structured: StructuredAddressProjection;
  delivery_date: string;
  delivery_time_slot: string;
  delivery_fee_override_q: number | null;
  order_notes: string;
  payment_method: string;
  payment_collection: PosPaymentCollection;
  payment_tenders: POSIntentCartState["paymentTenders"];
  tendered_amount_q: number | string;
  /** O CPF PEDIDO nesta venda (o que sai na nota), devolvido ao retomar a comanda. */
  fiscal_tax_id: string;
  receipt_channels: string[];
  receipt_email: string;
  discount_type: string;
  discount_value: string;
  discount_reason: string;
}

export interface POSCloseSaleResponse {
  ok: boolean;
  order_ref?: string;
  tab_ref?: string;
  payment?: POSPaymentResultProjection;
  /** Esta venda vai ter NFC-e. Quem responde é a regra fiscal no servidor: a
   *  emissão também dispara por forma de pagamento, sem o operador marcar nada,
   *  e a nota ainda não existe no instante do fechamento. */
  fiscal_expected?: boolean;
}

export interface POSPaymentResultProjection {
  method: string;
  amount_q: number;
  amount_display: string;
  status: string;
  message: string;
  intent_ref?: string;
  qr_code?: string;
  copy_paste?: string;
  expires_at?: string;
  checkout_url?: string;
  error?: string;
}

export interface POSIntentCartState {
  tabRef: string;
  tabSessionKey: string;
  items: POSCartItem[];
  customerName: string;
  customerRef: string;
  customerPhone: string;
  customerTaxId: string;
  /** O CPF PEDIDO para a nota DESTA venda. O cadastro empresta o valor
   *  inicial; editar aqui não volta para o cadastro. */
  invoiceTaxId: string;
  customerEmail: string;
  customerMemoryAction: string;
  fulfillmentType: "pickup" | "delivery";
  deliveryAddress: string;
  deliveryAddressStructured: StructuredAddressProjection;
  deliveryComplement: string;
  deliveryInstructions: string;
  deliveryDate: string;
  deliveryTimeSlot: string;
  /** A EXCEÇÃO que o operador assume (combinado de porta, cortesia). `null` =
   * sem exceção, e aí quem responde pela taxa é o motor de entrega no servidor.
   * Nunca 0 por omissão: ausente significa "resolva", não "cobre zero". */
  deliveryFeeOverrideQ: number | null;
  orderNotes: string;
  paymentMethod: string;
  paymentCollection: PosPaymentCollection;
  paymentTenders: POSPaymentTenderDraft[];
  tenderedAmountQ: number | null;
  /** "Troco para quanto?" do dinheiro na entrega, em centavos (0 = não informado). */
  changeForQ: number;
  receiptChannels: string[];
  receiptEmail: string;
  manualDiscount: Record<string, unknown> | null;
  managerApproval: Record<string, unknown> | null;
  clientRequestId: string;
}

export interface POSSaleReviewProjection {
  intent_version: string;
  tab_ref: string;
  subtotal_q: number;
  subtotal_display: string;
  discount_q: number;
  discount_display: string;
  delivery_fee_q: number;
  delivery_fee_display: string;
  total_q: number;
  total_display: string;
  payment_method: string;
  payment_collection: string;
  tender_total_q: number;
  tender_total_display: string;
  tender_count: number;
  tendered_amount_q: number;
  tendered_amount_display: string;
  change_q: number;
  change_display: string;
  requires_manager_approval: boolean;
  manager_approval_threshold_q: number;
  /** Por que o gerente foi chamado — o diálogo de autorização diz o que assinar. */
  approval_reasons: string[];
  receipt_channels: string[];
  /** Vai sair nota com CPF? (o consumidor pediu o documento nesta venda) */
  fiscal_tax_id_requested: boolean;
  warnings: Array<{ code: string; field: string; message: string }>;
  /** De onde a taxa saiu: "" (endereço em branco) · "zone" · "distance" ·
   * "default" · "manual" (exceção do operador) · "blocked" (fora da área). */
  delivery_fee_source: string;
  delivery_distance_km: number | null;
  /** A data que o servidor usou — em branco no pedido, é hoje pelo relógio da loja. */
  delivery_date: string;
  /** Janelas de meia hora do expediente daquele dia. Vazio = não há janela. */
  delivery_slots: Array<{ ref: string; label: string }>;
}

export interface POSSaleReviewResponse {
  ok: boolean;
  review: POSSaleReviewProjection;
}
