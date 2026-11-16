import { describe, expect, it } from "vitest";
import { courierCancelNotice } from "../app/presentation/courierCancel";

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
