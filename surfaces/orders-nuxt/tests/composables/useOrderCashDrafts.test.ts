import { beforeEach, expect, it, vi } from "vitest";
import { ref } from "vue";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useOrderCashDrafts } from "../../app/composables/useOrderCashDrafts";
const env = installNuxtGlobals();
const session = ref<{ operator?: { id: number } }>({ operator: { id: 1 } });
vi.stubGlobal("useNuxtData", () => ({ data: session }));
const initial = { amount: "", changeBack: "10,00", equipmentBack: true, revision: "shift-1", custody: "Turno 1" };
beforeEach(() => { env.reset(); session.value = { operator: { id: 1 } }; });

it("fechar/voltar em outra página conserva dado físico e base sem adotar custódia nova", () => {
  const board = useOrderCashDrafts();
  const draft = board.settlement("A", initial);
  draft.amount = "15,00";
  draft.changeBack = "8,00";
  draft.equipmentBack = false;
  const detail = useOrderCashDrafts();
  expect(detail.settlement("A", { ...initial, revision: "shift-2" })).toEqual({ ...initial, amount: "15,00", changeBack: "8,00", equipmentBack: false });
  expect(detail.settlement("B", initial).amount).toBe("");
  detail.clear("settlement", "A");
  expect(detail.settlement("A", { ...initial, revision: "shift-2" }).amount).toBe("");
});

it("saída mantém valor/equipamentos; expiração conserva e outra pessoa descarta", () => {
  const board = useOrderCashDrafts();
  const draft = board.dispatch("A", { amount: "10,00", equipment: [] });
  draft.amount = "9,00"; draft.equipment.push("card_machine");
  session.value = {};
  expect(board.dispatch("A", { amount: "12,00", equipment: [] }).amount).toBe("9,00");
  session.value = { operator: { id: 1 } };
  expect(board.dispatches.value.A?.equipment).toEqual(["card_machine"]);
  session.value = { operator: { id: 2 } };
  expect(board.dispatches.value).toEqual({});
  expect(board.settlements.value).toEqual({});
});

it("proteção de saída distingue draft alterado de vazio/restaurado e remove após commit", () => {
  const drafts = useOrderCashDrafts();
  const settlement = drafts.settlement("A", initial);
  expect(drafts.hasDirty.value).toBe(false);
  settlement.amount = "15,00";
  expect(drafts.hasDirty.value).toBe(true);
  settlement.amount = "";
  expect(drafts.hasDirty.value).toBe(false);
  settlement.revision = "shift-2";
  expect(drafts.hasDirty.value).toBe(false);
  drafts.dispatch("A", { amount: "10,00", equipment: [] }).equipment.push("card_machine");
  expect(drafts.hasDirty.value).toBe(true);
  drafts.clear("dispatch", "A");
  expect(drafts.hasDirty.value).toBe(false);
});
