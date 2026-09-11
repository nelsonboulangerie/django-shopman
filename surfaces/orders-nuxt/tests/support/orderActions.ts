import type { Action } from "../../app/generated/ordersContract";

/** Presentation fixtures only. Domain eligibility is exercised against Django. */
export function fixtureActions(card: { can_confirm?: boolean; can_advance?: boolean; next_action_label?: string; advance_block_label?: string; advance_block_reason?: string }): Action[] {
  const action = (ref: string, label: string, enabled = true, reason = "", priority = "primary"): Action => ({
    ref, label, enabled, reason, priority, kind: "mutation", href: "", method: "POST", payload_schema: { expected_actor_id: 1, base_revision: "fixture-base", target_status: "preparing" }, idempotency: "required", confirmation: {},
  });
  if (card.can_confirm) return [action("confirm", "Aceitar"), action("reject", "Recusar", true, "", "danger")];
  if (card.can_advance) return [action("advance", card.next_action_label || "Avançar")];
  if (card.advance_block_label) return [action("advance", card.advance_block_label, false, card.advance_block_reason)];
  return [];
}
