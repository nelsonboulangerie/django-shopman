import type { OrderCardProjection } from "../../app/types/orders";
import { fixtureActions } from "./orderActions";

const AZUL = { ref: "card_machine:az", label: "Azul", enabled: true, reason: "", order_ref: "" };
const PRETA = { ref: "card_machine:pr", label: "Preta", enabled: true, reason: "", order_ref: "" };
export const machines = {
  bothFree: [AZUL, PRETA],
  oneFree: [AZUL, { ...PRETA, enabled: false, reason: "Na rua com o pedido 0415", order_ref: "DLV-0415" }],
  noneFree: [
    { ...AZUL, enabled: false, reason: "Na rua com o pedido 0415", order_ref: "DLV-0415" },
    { ...PRETA, enabled: false, reason: "Na rua com o pedido 0418", order_ref: "DLV-0418" },
  ],
};

/** Um pedido de entrega pronto para sair (cartão na porta, por padrão). */
export function readyCard(over: Partial<OrderCardProjection> = {}): OrderCardProjection {
  return {
    ref: "DLV-0420", status: "ready", status_label: "Pronto", status_color: "", channel_ref: "web", channel_icon: "language",
    customer_name: "Carla", created_at_display: "", created_at_iso: "", server_now_iso: "", elapsed_seconds: 60, timer_class: "timer-ok",
    items_summary: "2× Croissant", items_count: 2, total_display: "R$ 38,00", fulfillment_icon: "truck", fulfillment_label: "Entrega",
    fulfillment_type: "delivery", delivery_address: "", delivery_instructions: "", can_confirm: false, can_advance: true,
    next_status: "dispatched", next_action_label: "Saiu com a maquininha", payment_method: "credit", payment_method_label: "Cartão na entrega",
    change_out_suggested_q: 0, change_label: "", equipment_options: machines.oneFree, equipment_out: [], equipment_label: "",
    equipment_back_pending: false, dispatch_needs_machine: true, trip_with: [], courier_return_orders: [], courier_return_lines: [],
    actions: fixtureActions({ can_advance: true, next_action_label: "Saiu com a maquininha" }),
    ...over,
  } as OrderCardProjection;
}
