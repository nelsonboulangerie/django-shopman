import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";

import OrderCardActions from "../../app/components/OrderCardActions.vue";
import type { Affordance } from "../../app/presentation/board";
import type { OrderCardProjection } from "../../app/types/orders";

// WP-G06 (laudo do Gestor, P2-01 e P1-12): o botão secundário respeita o `disabled` do
// servidor, e o porquê de um botão travado vai escrito, porque o tablet não tem hover.

const stubs = { OrderCardMenu: { template: "<span data-card-menu />" } };
const card = (over: Partial<OrderCardProjection> = {}) =>
  ({ ref: "NB-261118-W33", actions: [], advance_block_reason: "", ...over }) as OrderCardProjection;
const aff = (over: Partial<Affordance> = {}): Affordance => ({
  ref: "confirm", label: "Aceitar", icon: "lucide:check", priority: "primary",
  needsInput: false, disabled: false, reason: "", ...over,
});
const reject = (over: Partial<Affordance> = {}) =>
  aff({ ref: "reject", label: "Recusar", icon: "lucide:x", priority: "danger", needsInput: true, ...over });

function rodape(props: Record<string, unknown> = {}) {
  const primary = (props.primary ?? aff()) as Affordance | null;
  return mount(OrderCardActions, {
    props: {
      card: card(), handoff: null, primary, secondary: [reject()],
      primaryLabel: primary?.label ?? "", waitingFor: "", ...props,
    },
    global: { stubs },
  });
}
const PERMISSION = "Identifique uma pessoa com permissão para gerenciar pedidos.";

describe("OrderCardActions: botão travado", () => {
  it("o secundário livre emite o gesto", async () => {
    const w = rodape();
    await w.get('[data-card-secondary="reject"]').trigger("click");
    expect(w.emitted("action")).toEqual([["reject"]]);
    expect(w.find("[data-card-blocked-reason]").exists()).toBe(false);
  });

  it("o secundário travado pelo servidor fica desligado e não emite (P2-01)", async () => {
    const w = rodape({ secondary: [reject({ disabled: true, reason: "O iFood já concluiu este pedido: não há o que recusar." })] });
    const button = w.get('[data-card-secondary="reject"]');
    expect(button.attributes("disabled")).toBeDefined();
    expect(button.find('[data-icon="i-lucide-lock"]').exists()).toBe(true);
    await button.trigger("click");
    expect(w.emitted("action")).toBeUndefined();
  });

  it("o motivo do secundário travado aparece escrito, com o nome do botão", () => {
    const w = rodape({
      primary: aff({ ref: "advance", label: "Marcar como retirado" }),
      primaryLabel: "Entregar W33",
      secondary: [
        aff({ ref: "settle_cash", label: "Receber na retirada", icon: "lucide:banknote", priority: "secondary",
          disabled: true, reason: "Abra um turno de caixa para registrar o acerto." }),
      ],
    });
    expect(w.findAll("[data-card-blocked-reason]").map((line) => line.text())).toEqual([
      "Receber na retirada: Abra um turno de caixa para registrar o acerto.",
    ]);
  });

  it("o Aceitar travado mostra o motivo sem depender de hover (P1-12)", () => {
    const reason = "Cancelamento solicitado ao iFood. Aguardando confirmação.";
    const w = rodape({ primary: aff({ disabled: true, reason }) });
    expect(w.get("[data-card-primary]").attributes("disabled")).toBeDefined();
    expect(w.get("[data-card-blocked-reason]").text()).toBe(`Aceitar: ${reason}`);
  });

  it("o mesmo motivo em todos os botões sai uma vez só", () => {
    const w = rodape({
      primary: aff({ disabled: true, reason: PERMISSION }),
      secondary: [reject({ disabled: true, reason: PERMISSION })],
    });
    expect(w.findAll("[data-card-blocked-reason]").map((line) => line.text())).toEqual([PERMISSION]);
  });

  it("o bloqueio que o cartão já anuncia na pílula não vira segunda frase", () => {
    const w = rodape({
      card: card({ advance_block_reason: "gerado às 21h55 · expira às 22h25 · sem pagamento até lá, cancela sozinho" }),
      primary: aff({ disabled: true, reason: "Pagamento ainda não confirmado. Aceite o pedido quando o dinheiro entrar." }),
    });
    expect(w.find("[data-card-blocked-reason]").exists()).toBe(false);
  });

  it("o avanço travado que repete a pílula do bloqueio não vira botão morto (P1-16)", () => {
    const w = rodape({
      card: card({ advance_block_label: "Pix expirado", advance_block_reason: "gerado às 20h56 · expirou às 21h26" }),
      primary: aff({ ref: "advance", label: "Pix expirado", disabled: true, reason: "Pagamento ainda não foi confirmado." }),
      secondary: [],
    });
    expect(w.find("[data-card-primary]").exists()).toBe(false);
    expect(w.find("[data-card-blocked-reason]").exists()).toBe(false);
    expect(w.find("[data-card-menu]").exists()).toBe(true);
  });

  it("o Aceitar travado continua no cartão, com o nome do gesto", () => {
    const w = rodape({
      card: card({ advance_block_label: "Aguardando Pix…", advance_block_reason: "expira às 22h25" }),
      primary: aff({ disabled: true, reason: "Pagamento ainda não confirmado." }),
    });
    expect(w.get("[data-card-primary]").text()).toContain("Aceitar");
  });

  it("com a saída tocada (Desfazer no lugar dos botões), não há motivo a escrever", () => {
    const w = rodape({
      handoff: { label: "Entregue", canUndo: false, untilIso: "", sinceIso: "", action: "undo_handoff" },
      primary: aff({ disabled: true, reason: PERMISSION }),
    });
    expect(w.find("[data-card-blocked-reason]").exists()).toBe(false);
  });
});
