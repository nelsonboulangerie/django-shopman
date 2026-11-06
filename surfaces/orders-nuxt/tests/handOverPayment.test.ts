// Beta 05/11 (GES-03): pedido sem pagamento registrado era entregue com um toque.
import { describe, expect, it } from "vitest";
import { handOverPaymentQuestion } from "~/presentation/board";

const base = { total_display: "R$ 50,00", payment_unrecorded: true };

describe("handOverPaymentQuestion", () => {
  it("pergunta antes do balcão entregar na mão", () => {
    const q = handOverPaymentQuestion({ ...base, status: "ready", target: "completed" });
    expect(q?.title).toBe("Já recebeu R$ 50,00?");
    expect(q?.confirmLabel).toBe("Já foi pago, entregar");
    expect(q?.tone).toBe("primary");
  });

  it("pergunta antes da saída para entrega", () => {
    const q = handOverPaymentQuestion({ ...base, status: "ready", target: "dispatched" });
    expect(q?.confirmLabel).toBe("Já foi pago, marcar saída");
  });

  it("não pergunta nos degraus que não entregam mercadoria", () => {
    for (const target of ["confirmed", "preparing", "ready", "delivered"])
      expect(handOverPaymentQuestion({ ...base, status: "accepted", target })).toBeNull();
    // Concluído vindo de Entregue é só escrituração: a sacola já saiu.
    expect(
      handOverPaymentQuestion({ ...base, status: "delivered", target: "completed" }),
    ).toBeNull();
  });

  it("não pergunta quando há pagamento registrado", () => {
    expect(
      handOverPaymentQuestion({
        ...base,
        payment_unrecorded: false,
        status: "ready",
        target: "completed",
      }),
    ).toBeNull();
  });

  it("a copy não usa travessão", () => {
    const q = handOverPaymentQuestion({ ...base, status: "ready", target: "dispatched" });
    expect(JSON.stringify(q)).not.toMatch(/[—–]/);
  });
});
