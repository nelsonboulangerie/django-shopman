import { describe, expect, it } from "vitest";

import {
  PENDING_TONES,
  pendingButton,
  pendingLines,
  pendingTone,
  refundRetrySentence,
  refundRetryToast,
  settledMoney,
} from "../app/presentation/orderPending";

// WP-G05: a tradução da lista do servidor em desenho. Nenhuma régua de negócio aqui.

const action = (ref: string, over: Record<string, unknown> = {}) => ({
  ref, label: ref, enabled: true, reason: "", href: "", ...over,
});
const idle = { busy: false, danfePrinting: false };

describe("pendingTone", () => {
  it("tom desconhecido vira o mais calmo, nunca alarme", () => {
    expect(pendingTone("error")).toBe("error");
    expect(pendingTone("warning")).toBe("warning");
    expect(pendingTone("info")).toBe("info");
    expect(pendingTone("danger")).toBe("info");
    expect(pendingTone("")).toBe("info");
  });

  it("espera saudável não usa cor de erro nem de aviso", () => {
    expect(PENDING_TONES.info.iconClass).toBe("text-muted");
    expect(PENDING_TONES.error.iconClass).toBe("text-error");
  });
});

describe("pendingButton", () => {
  it("o principal é cheio; o resto, contornado; cancelar é sempre vermelho", () => {
    expect(pendingButton(action("requeue-fiscal"), { ...idle, lead: true })).toMatchObject({ color: "primary", variant: "solid" });
    expect(pendingButton(action("requeue-fiscal"), { ...idle, lead: false })).toMatchObject({ color: "neutral", variant: "outline" });
    expect(pendingButton(action("cancel"), { ...idle, lead: false })).toMatchObject({ color: "error", variant: "outline" });
  });

  it("a conversa com o cliente é link e não trava com a gravação do pedido", () => {
    const contact = pendingButton(action("contact-customer", { href: "https://wa.me/55" }), { busy: true, danfePrinting: false, lead: false });
    expect(contact.href).toBe("https://wa.me/55");
    expect(contact.disabled).toBe(false);
    expect(pendingButton(action("requeue-fiscal"), { busy: true, danfePrinting: false, lead: false }).disabled).toBe(true);
  });

  it("o motivo de quem não pode vai escrito, e não só no botão", () => {
    const blocked = pendingButton(action("cancel", { enabled: false, reason: "Cancelar pedido em Pronto é do gerente." }), { ...idle, lead: true });
    expect(blocked.disabled).toBe(true);
    expect(blocked.blockedReason).toBe("Cancelar pedido em Pronto é do gerente.");
  });
});

// WP-G13: "Tentar o estorno de novo" na linha "Estorno não saiu".
describe("pendingButton: tentar o estorno de novo", () => {
  const retry = action("refund-retry", { label: "Tentar o estorno de novo" });

  it("parado, é o gesto da linha, com o ícone de voltar", () => {
    expect(pendingButton(retry, { ...idle, lead: true })).toMatchObject({
      label: "Tentar o estorno de novo", icon: "i-lucide-rotate-ccw", color: "primary", variant: "solid", disabled: false, loading: false,
    });
  });

  it("enquanto o estorno vai ao meio de pagamento, o botão diz isso e não aceita outro toque", () => {
    expect(pendingButton(retry, { busy: true, danfePrinting: false, refundRetrying: true, lead: true })).toMatchObject({
      label: "Tentando o estorno…", disabled: true, loading: true,
    });
    // Outro gesto da faixa não vira "tentando": só trava pela gravação em andamento.
    expect(pendingButton(action("requeue-fiscal"), { busy: true, danfePrinting: false, refundRetrying: true, lead: false })).toMatchObject({
      label: "requeue-fiscal", disabled: true, loading: false,
    });
  });

  it("quem não pode vê o botão desligado, com o motivo escrito", () => {
    const reason = "Identifique uma pessoa com permissão para gerenciar pedidos.";
    expect(pendingButton({ ...retry, enabled: false, reason }, { ...idle, lead: true })).toMatchObject({ disabled: true, blockedReason: reason });
  });
});

describe("refundRetrySentence / refundRetryToast", () => {
  const money = (state: string, amount = "R$ 22,00") => ({ state, label: "", amount_display: amount, customer_line: "", settled: state === "refunded" });

  it("o gerente lê o valor antes de assinar; sem valor, a frase do ato assume", () => {
    expect(refundRetrySentence(money("refund_failed"))).toBe("Estorno de R$ 22,00, pedido de novo ao meio de pagamento.");
    expect(refundRetrySentence(money("refund_failed", ""))).toBe("");
    expect(refundRetrySentence(null)).toBe("");
  });

  it("só diz Estornado com a confirmação; a tentativa que não saiu não vira aviso solto", () => {
    expect(refundRetryToast(money("refunded"))).toBe("Estornado: o meio de pagamento confirmou a devolução.");
    expect(refundRetryToast(money("refund_requested"))).toBe("Estorno pedido. O pedido mostra quando ele for confirmado.");
    expect(refundRetryToast(money("refund_failed"))).toBe("");
    expect(refundRetryToast(null)).toBe("");
  });
});

describe("pendingLines", () => {
  it("a falha da última tentativa vai com a linha, separada do motivo", () => {
    const failure = "Última tentativa, em 18/11 às 14h32: O Pix não aceitou o estorno. Nada foi devolvido ao cliente. Chame o suporte.";
    const [line] = pendingLines(
      [{ key: "refund", tone: "error", label: "Estorno não saiu", reason: "A devolução de R$ 22,00 não chegou ao cliente.", failure, actions: [action("refund-retry")] }],
      idle,
    );
    expect(line!.failure).toBe(failure);
    expect(line!.reason).toBe("A devolução de R$ 22,00 não chegou ao cliente.");
  });

  it("o gesto principal é o da primeira linha que pede alguém, pulando a espera", () => {
    const lines = pendingLines(
      [
        { key: "payment", tone: "info", label: "Aguardando pagamento", reason: "", failure: "", actions: [action("resend-payment-link")] },
        { key: "phase", tone: "error", label: "Etapa automática travada", reason: "", failure: "", actions: [] },
        { key: "nfce", tone: "error", label: "NFC-e não autorizada", reason: "", failure: "", actions: [action("requeue-fiscal")] },
        { key: "danfe", tone: "warning", label: "DANFE não impressa", reason: "", failure: "", actions: [action("print-danfe")] },
      ],
      idle,
    );
    expect(lines.map((line) => line.buttons.map((button) => button.variant))).toEqual([["outline"], [], ["solid"], ["outline"]]);
  });

  it("junta os motivos das ações travadas sem repetir", () => {
    const reason = "Identifique uma pessoa com permissão para gerenciar pedidos.";
    const [line] = pendingLines(
      [{ key: "payment", tone: "error", label: "Pix expirado", reason: "", failure: "", actions: [
        action("cancel", { enabled: false, reason }),
        action("resend-payment-link", { enabled: false, reason }),
      ] }],
      idle,
    );
    expect(line!.blockedReasons).toEqual([reason]);
  });
});

describe("settledMoney", () => {
  it("só fala do dinheiro que já está onde devia", () => {
    expect(settledMoney(null)).toBeNull();
    expect(settledMoney({ state: "refund_requested", label: "Estorno pedido", amount_display: "R$ 18,70", customer_line: "x", settled: false })).toBeNull();
    expect(settledMoney({ state: "refunded", label: "Estornado", amount_display: "R$ 18,70", customer_line: "Devolvemos os R$ 18,70 do seu Pix para a mesma conta.", settled: true })).toEqual({
      title: "Dinheiro do pedido cancelado: Estornado",
      customerLine: "O cliente lê na loja: “Devolvemos os R$ 18,70 do seu Pix para a mesma conta.”",
    });
    expect(settledMoney({ state: "nothing_charged", label: "Nada foi cobrado", amount_display: "", customer_line: "", settled: true })).toEqual({
      title: "Dinheiro do pedido cancelado: Nada foi cobrado",
      customerLine: "",
    });
  });
});
