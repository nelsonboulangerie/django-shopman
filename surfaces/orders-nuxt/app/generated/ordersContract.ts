// AUTO-GENERATED — do not edit by hand.
// Source of truth: shopman/backstage/projections/order_queue.py + shopman/shop/projections/types.py + shopman/backstage/projections/catalog.py + shopman/backstage/projections/feeds.py
// Regenerate with: python manage.py export_orders_schema

/** CatalogPricePreviewCell(id: 'int', sku: 'str', surface_ref: 'str', tier: 'str', before_q: 'int', after_q: 'int') */
export interface CatalogPricePreviewCell {
  id: number;
  sku: string;
  surface_ref: string;
  tier: string;
  before_q: number;
  after_q: number;
}

/** CatalogPricePreview(base_revision: 'str', expected_actor_id: 'int', cells: 'tuple[CatalogPricePreviewCell, ...]', limit: 'int') */
export interface CatalogPricePreview {
  base_revision: string;
  expected_actor_id: number;
  cells: CatalogPricePreviewCell[];
  limit: number;
}

/** CatalogPublicationCell(sku: 'str', surface_ref: 'str', tier: 'str', before: 'dict[str, bool]', after: 'dict[str, bool]') */
export interface CatalogPublicationCell {
  sku: string;
  surface_ref: string;
  tier: string;
  before: Record<string, boolean>;
  after: Record<string, boolean>;
}

/** CatalogPublicationSkip(sku: 'str', surface_ref: 'str', reason: 'str') */
export interface CatalogPublicationSkip {
  sku: string;
  surface_ref: string;
  reason: string;
}

/** CatalogPublicationPreview(base_revision: 'str', expected_actor_id: 'int', cells: 'tuple[CatalogPublicationCell, ...]', skipped: 'tuple[CatalogPublicationSkip, ...]', limit: 'int') */
export interface CatalogPublicationPreview {
  base_revision: string;
  expected_actor_id: number;
  cells: CatalogPublicationCell[];
  skipped: CatalogPublicationSkip[];
  limit: number;
}

/** Canonical action offered by a Shopman projection to any surface. */
export interface Action {
  ref: string;
  kind: string;
  label: string;
  priority: string;
  enabled: boolean;
  reason: string;
  href: string;
  method: string;
  payload_schema: Record<string, unknown>;
  idempotency: string;
  confirmation: Record<string, unknown>;
}

/** IFoodNegotiationProjection(id: str, type: str, action: str, message: str, expires_at: str, timeout_action: str, state: str, can_respond: bool, response_notice: str, items: tuple[str, ...], evidence_urls: tuple[str, ...], accept_reasons: tuple[str, ...], reject_reasons: tuple[str, ...], alternatives_available: bool, actions: tuple[shopman.shop.projections.types.Action, ...]) */
export interface IFoodNegotiationProjection {
  id: string;
  type: string;
  action: string;
  message: string;
  expires_at: string;
  timeout_action: string;
  state: string;
  can_respond: boolean;
  response_notice: string;
  items: string[];
  evidence_urls: string[];
  accept_reasons: string[];
  reject_reasons: string[];
  alternatives_available: boolean;
  actions: Action[];
}

/** CatalogSnapshotSummary(id: int, account_ref: str, catalog_ref: str, context: str, captured_at: str, imported_at: str, sha256: str, source: str, item_count: int) */
export interface CatalogSnapshotSummary {
  id: number;
  account_ref: string;
  catalog_ref: string;
  context: string;
  captured_at: string;
  imported_at: string;
  sha256: string;
  source: string;
  item_count: number;
}

/** CatalogProductOption(sku: str, name: str) */
export interface CatalogProductOption {
  sku: string;
  name: string;
}

/** CatalogCurrentBinding(sku: str, name: str, actor: str, confirmed_at: str, revision: int, snapshot_id: int) */
export interface CatalogCurrentBinding {
  sku: string;
  name: string;
  actor: string;
  confirmed_at: string;
  revision: number;
  snapshot_id: number;
}

/** CatalogReviewItem(item_id: str, product_ref: str, category_ref: str, category_name: str, item_context_ref: str, name: str, description: str, image_path: str, status: str, price: str, external_code: str, diagnostic: str, notice: str, candidates: tuple[shopman.backstage.projections.catalog_bindings.CatalogProductOption, ...], binding: shopman.backstage.projections.catalog_bindings.CatalogCurrentBinding | None, base_revision: str, can_bind: bool, needs_review: bool, blocked_reason: str, binding_action: shopman.shop.projections.types.Action) */
export interface CatalogReviewItem {
  item_id: string;
  product_ref: string;
  category_ref: string;
  category_name: string;
  item_context_ref: string;
  name: string;
  description: string;
  image_path: string;
  status: string;
  price: string;
  external_code: string;
  diagnostic: string;
  notice: string;
  candidates: CatalogProductOption[];
  binding: CatalogCurrentBinding | null;
  base_revision: string;
  can_bind: boolean;
  needs_review: boolean;
  blocked_reason: string;
  binding_action: Action;
}

/** CatalogBindingReviewProjection(channel_ref: str, channel_name: str, provider: str, snapshots: tuple[shopman.backstage.projections.catalog_bindings.CatalogSnapshotSummary, ...], selected_snapshot: shopman.backstage.projections.catalog_bindings.CatalogSnapshotSummary | None, products: tuple[shopman.backstage.projections.catalog_bindings.CatalogProductOption, ...], items: tuple[shopman.backstage.projections.catalog_bindings.CatalogReviewItem, ...], expected_actor_id: int | None, notice: str, import_action: shopman.shop.projections.types.Action) */
export interface CatalogBindingReviewProjection {
  channel_ref: string;
  channel_name: string;
  provider: string;
  snapshots: CatalogSnapshotSummary[];
  selected_snapshot: CatalogSnapshotSummary | null;
  products: CatalogProductOption[];
  items: CatalogReviewItem[];
  expected_actor_id: number | null;
  notice: string;
  import_action: Action;
}

/** FeedCollectionRef(ref: 'str', name: 'str', exists: 'bool') */
export interface FeedCollectionRef {
  ref: string;
  name: string;
  exists: boolean;
}

/** FeedProjection(ref: 'str', name: 'str', kind: 'str', kind_label: 'str', kind_icon: 'str', capability: 'str', is_active: 'bool', output_path: 'str', collections: 'tuple[FeedCollectionRef, ...]', rotate_seconds: 'int', items_per_page: 'int', actions: 'tuple[Action, ...]' = ()) */
export interface FeedProjection {
  ref: string;
  name: string;
  kind: string;
  kind_label: string;
  kind_icon: string;
  capability: string;
  is_active: boolean;
  output_path: string;
  collections: FeedCollectionRef[];
  rotate_seconds: number;
  items_per_page: number;
  actions: Action[];
}

/** CatalogChannelProjection(ref: 'str', name: 'str', projection_enabled: 'bool', diagnostic: 'str', synced: 'int', pending: 'int', errors: 'int', retracted: 'int', skipped: 'int', observed: 'int', catalog_path: 'str' = '/catalog') */
export interface CatalogChannelProjection {
  ref: string;
  name: string;
  projection_enabled: boolean;
  diagnostic: string;
  synced: number;
  pending: number;
  errors: number;
  retracted: number;
  skipped: number;
  observed: number;
  catalog_path: string;
}

/** CollectionOptionProjection(ref: 'str', name: 'str', product_count: 'int') */
export interface CollectionOptionProjection {
  ref: string;
  name: string;
  product_count: number;
}

/** FeedBoardProjection(feeds: 'tuple[FeedProjection, ...]', all_collections: 'tuple[CollectionOptionProjection, ...]', catalog_channels: 'tuple[CatalogChannelProjection, ...]' = ()) */
export interface FeedBoardProjection {
  feeds: FeedProjection[];
  all_collections: CollectionOptionProjection[];
  catalog_channels: CatalogChannelProjection[];
}

/** One line item as displayed on order tracking or confirmation. */
export interface OrderItemProjection {
  sku: string;
  name: string;
  qty: string;
  unit_price_display: string;
  total_display: string;
}

/** A single event in the order timeline. */
export interface TimelineEventProjection {
  label: string;
  event_type: string;
  timestamp_display: string;
  actor: string;
  detail: string;
}

/** A compact production dependency shown on order cards and detail. */
export interface AwaitingWorkOrderProjection {
  ref: string;
  status: string;
  status_label: string;
  output_sku: string;
  planned_qty: string;
  finished_qty: string;
  progress_pct: number;
}

/** Um aparelho que o entregador pode levar no despacho (ref do canal + rótulo). */
export interface EquipmentOptionProjection {
  ref: string;
  label: string;
  enabled: boolean;
  reason: string;
}

/** Onde está o aparelho agora: saiu com o entregador deste pedido e não voltou. */
export interface EquipmentOutProjection {
  ref: string;
  label: string;
  order_ref: string;
  customer_name: string;
  out_at: string;
  actions: Action[];
  identified: boolean;
}

/** Quem é este cliente, para o operador decidir como tratá-lo. */
export interface CustomerProfileProjection {
  is_first_order: boolean;
  total_orders: number;
  orders_label: string;
  last_order_display: string;
  average_ticket_display: string;
  favorite_product: string;
  segment: string;
  segment_label: string;
  segment_tone: string;
  notes: string;
  dietary_restrictions: string;
  birthday_display: string;
  is_birthday_today: boolean;
}

/** A single order card in the operator queue. */
export interface OrderCardProjection {
  ref: string;
  status: string;
  actions: Action[];
  revisions: Record<string, string>;
  status_label: string;
  status_color: string;
  channel_ref: string;
  channel_icon: string;
  customer_name: string;
  created_at_display: string;
  created_at_iso: string;
  server_now_iso: string;
  elapsed_seconds: number;
  timer_class: string;
  items_summary: string;
  items_count: number;
  total_display: string;
  fulfillment_icon: string;
  fulfillment_label: string;
  fulfillment_type: string;
  delivery_address: string;
  delivery_instructions: string;
  can_confirm: boolean;
  can_advance: boolean;
  next_status: string;
  next_action_label: string;
  payment_method: string;
  payment_method_label: string;
  payment_status: string;
  payment_status_label: string;
  payment_pending: boolean;
  payment_tone: string;
  advance_block_label: string;
  advance_block_reason: string;
  can_settle_delivery_cash: boolean;
  fiscal_status_label: string;
  fiscal_status: string;
  fiscal_state: string;
  has_kitchen_note: boolean;
  has_customer_note: boolean;
  is_gift: boolean;
  gift_has_recipient: boolean;
  assigned_operator: string;
  awaiting_work_orders: AwaitingWorkOrderProjection[];
  confirmation_deadline_iso: string;
  confirmation_action: string;
  courier_status: string;
  courier_status_label: string;
  is_preorder: boolean;
  commitment_date: string;
  commitment_date_display: string;
  change_for_q: number;
  change_out_suggested_q: number;
  change_out_q: number;
  change_back_pending: boolean;
  change_back_q: number;
  change_label: string;
  equipment_options: EquipmentOptionProjection[];
  equipment_out: string[];
  equipment_label: string;
  equipment_back_pending: boolean;
  waitlist_state: string;
  waitlist_deadline_iso: string;
  waitlist_label: string;
  ifood_cancellation_notice: string;
  ifood_payment_summary: string[];
  ifood_operation_summary: string[];
  ifood_negotiations: IFoodNegotiationProjection[];
}

/** Expanded detail for a single order (operator side-panel). */
export interface OperatorOrderProjection {
  ref: string;
  status: string;
  actions: Action[];
  revisions: Record<string, string>;
  status_label: string;
  status_color: string;
  customer_name: string;
  customer_phone: string;
  customer_phone_uri: string;
  customer_whatsapp_url: string;
  customer_email: string;
  customer_ref: string;
  channel_ref: string;
  channel_icon: string;
  fulfillment_label: string;
  fulfillment_type: string;
  delivery_address: string;
  delivery_instructions: string;
  total_display: string;
  items: OrderItemProjection[];
  timeline: TimelineEventProjection[];
  kitchen_note: string;
  customer_note: string;
  payment_method: string;
  payment_method_label: string;
  payment_status: string;
  payment_status_label: string;
  can_confirm: boolean;
  can_advance: boolean;
  can_cancel: boolean;
  cancel_requires_approval: boolean;
  cancel_block_label: string;
  next_action_label: string;
  advance_block_label: string;
  advance_block_reason: string;
  can_settle_delivery_cash: boolean;
  fiscal_status_label: string;
  fiscal_status: string;
  fiscal_state: string;
  fiscal_links: Record<string, string>[];
  awaiting_work_orders: AwaitingWorkOrderProjection[];
  is_gift: boolean;
  gift_recipient_name: string;
  gift_recipient_phone: string;
  gift_message: string;
  gift_hide_values: boolean;
  cancellation_presets: string[];
  kitchen_note_tags: string[];
  customer_profile: CustomerProfileProjection | null;
  courier: Record<string, unknown> | null;
  change_for_q: number;
  change_out_suggested_q: number;
  change_out_q: number;
  change_back_pending: boolean;
  change_back_q: number;
  change_label: string;
  equipment_options: EquipmentOptionProjection[];
  equipment_out: string[];
  equipment_label: string;
  equipment_back_pending: boolean;
  can_resend_payment_link: boolean;
  payment_link_notice: string;
  ifood_cancellation_notice: string;
  ifood_payment_summary: string[];
  ifood_operation_summary: string[];
  ifood_negotiations: IFoodNegotiationProjection[];
}

/** Top-level read model for the operator order queue. */
export interface OrderQueueProjection {
  orders: OrderCardProjection[];
  counts: Record<string, number>;
  active_filter: string;
}

/** Operator queue grouped by action area: intake, prep and expedition */
export interface TwoZoneQueueProjection {
  intake: OrderCardProjection[];
  preparing_count: number;
  prep: OrderCardProjection[];
  expedition_pickup: OrderCardProjection[];
  expedition_delivery: OrderCardProjection[];
  expedition_delivery_transit: OrderCardProjection[];
  expedition_delivery_count: number;
  expedition_count: number;
  total_count: number;
  service_day: string;
  service_day_ends_at: string;
  preorders: OrderCardProjection[];
  preorders_count: number;
  equipment_out: EquipmentOutProjection[];
  equipment_available: EquipmentOptionProjection[];
  ifood_negotiation_orders: OrderCardProjection[];
}
