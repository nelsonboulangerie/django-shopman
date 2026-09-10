// AUTO-GENERATED — do not edit by hand.
// Source of truth: shopman/shop/services/pos_intent.py
// Regenerate with: python manage.py export_pos_schema

export const POS_SALE_INTENT_VERSION = "pos.sale-intent.v1";

export const POS_SALE_INTENT_KEYS = ["cash_shift_id", "change_for_q", "client_request_id", "customer_email", "customer_memory_action", "customer_name", "customer_phone", "customer_ref", "customer_tax_id", "delivery_address", "delivery_address_structured", "delivery_date", "delivery_fee_override_q", "delivery_time_slot", "expected_revision", "fiscal_tax_id", "fulfillment_type", "intent_version", "items", "manager_approval", "manual_discount", "order_notes", "payment_collection", "payment_method", "payment_tenders", "pos_terminal_ref", "receipt_channels", "receipt_email", "review_total_q", "save_receipt_contact", "save_receipt_tax_id", "save_receipt_tax_id_confirmed", "schema_version", "tab_ref", "tab_session_key", "tendered_q"] as const;
export type PosSaleIntentKey = (typeof POS_SALE_INTENT_KEYS)[number];

export const POS_PAYMENT_METHODS = ["account", "card", "cash", "credit", "debit", "external", "link", "mixed", "pix"] as const;
export type PosPaymentMethod = (typeof POS_PAYMENT_METHODS)[number];

export const POS_PAYMENT_COLLECTIONS = ["on_delivery", "terminal"] as const;
export type PosPaymentCollection = (typeof POS_PAYMENT_COLLECTIONS)[number];

export const POS_RECEIPT_CHANNELS = ["email", "print"] as const;
export type PosReceiptChannel = (typeof POS_RECEIPT_CHANNELS)[number];
