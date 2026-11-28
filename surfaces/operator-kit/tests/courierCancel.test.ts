import { describe, expect, it } from "vitest";
import { cancelConfirmation, courierCancelNotice } from "../app/presentation/courierCancel";

// O cancelamento pedido de uma corrida da TaOn nunca fica mudo: espera, dúvida e
// recusa são três avisos diferentes, com a frase do servidor.

describe("courierCancelNotice", () => {
  it("sem cancelamento pedido, sem aviso", () => {
    expect(courierCancelNotice("", "")).toBeNull();
    expect(courierCancelNotice(undefined, undefined)).toBeNull();
    expect(courierCancelNotice("pending", "")).toBeNull();
  });

  it("pedido enviado é espera, não erro", () => {
    const message = "Pedido de cancelamento enviado. Esperando a TaOn confirmar.";
    expect(courierCancelNotice("pending", message)).toEqual({ color: "info", icon: "i-lucide-hourglass", message });
  });

  it("envio sem resposta pede conferência na central", () => {
    const message = "Cancelamento sem resultado confirmado. Confira esta corrida na central antes de reenviar.";
    expect(courierCancelNotice("unknown", message)?.color).toBe("warning");
  });

  it("recusa da TaOn é erro: a corrida segue aberta", () => {
    const message = "A TaOn não cancelou a corrida B. Cancele pela central da TaOn.";
    expect(courierCancelNotice("failed", message)).toEqual({
      color: "error",
      icon: "i-lucide-triangle-alert",
      message,
    });
  });
});

describe("confirmação de cancelar a corrida", () => {
  const base = { label: "Cancelar corrida" };

  it("antes do aceite: a pergunta e o botão do servidor, sem motivo para escolher", () => {
    const copy = cancelConfirmation({
      ...base,
      confirmation: {
        required: true,
        description: "Cancelar a corrida B? A05 e C12 voltam para Aguardando.",
        confirm_label: "Cancelar a corrida B",
      },
    });
    expect(copy.question).toBe("Cancelar a corrida B? A05 e C12 voltam para Aguardando.");
    expect(copy.confirmLabel).toBe("Cancelar a corrida B");
    expect(copy.reasons).toEqual([]);
  });

  it("depois do aceite: cada motivo do servidor vira um botão, com o reason_id dele", () => {
    const copy = cancelConfirmation({
      ...base,
      confirmation: {
        required: true,
        description: "Cancelar a corrida B? A05 volta para Aguardando.",
        reason_question: "Por que cancelar a corrida B?",
        consequence: "A05 volta para Aguardando.",
        reasons: [
          { id: 12, label: "O entregador não está vindo" },
          { id: 37, label: "Está demorando demais" },
          { id: 40, label: "Não consegui falar com o entregador" },
        ],
      },
    });
    expect(copy.reasonQuestion).toBe("Por que cancelar a corrida B?");
    expect(copy.consequence).toBe("A05 volta para Aguardando.");
    expect(copy.reasons.map((reason) => [reason.id, reason.label])).toEqual([
      [12, "O entregador não está vindo"],
      [37, "Está demorando demais"],
      [40, "Não consegui falar com o entregador"],
    ]);
    expect(new Set(copy.reasons.map((reason) => reason.icon)).size).toBe(3);
  });

  it("motivo sem id inteiro ou sem rótulo não vira botão; sem frases, o texto mínimo", () => {
    const copy = cancelConfirmation({
      ...base,
      confirmation: { reasons: [{ id: "12", label: "x" }, { id: 37 }, { id: 40, label: "Não consegui falar com o entregador" }] },
    });
    expect(copy.reasons.map((reason) => reason.id)).toEqual([40]);
    expect(copy.question).toBe("Cancelar a corrida?");
    expect(copy.confirmLabel).toBe("Cancelar corrida");
    expect(cancelConfirmation(null).reasons).toEqual([]);
  });
});
