import type { Action } from "../../app/generated/ordersContract";

/** Presentation fixtures only. Domain eligibility is exercised against Django. */
export function fixtureActions(card: { can_confirm?: boolean; can_advance?: boolean; next_action_label?: string; advance_block_label?: string; advance_block_reason?: string }): Action[] {
  const action = (ref: string, label: string, enabled = true, reason = "", priority = "primary"): Action => ({
    ref, label, enabled, reason, priority, kind: "mutation", href: "", method: "POST", payload_schema: { expected_actor_id: 1, base_revision: "fixture-base", target_status: "preparing" }, idempotency: "required", confirmation: {},
  });
  // A nota da cozinha é editável em todo pedido aberto: o servidor emite `notes`
  // sempre, e só a desliga no pedido encerrado (beta 05/11, GES-10).
  const notes = action("notes", "Salvar nota", true, "", "secondary");
  if (card.can_confirm) return [action("confirm", "Aceitar"), action("reject", "Recusar", true, "", "danger"), notes];
  if (card.can_advance) return [action("advance", card.next_action_label || "Avançar"), notes];
  if (card.advance_block_label) return [action("advance", card.advance_block_label, false, card.advance_block_reason), notes];
  return [notes];
}
