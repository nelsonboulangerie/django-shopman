import { describe, expect, it } from "vitest";
import {
  deliveryActionLabel,
  includesDirectMessage,
  includesPublicPublication,
} from "~/presentation/marketingDelivery";

describe("rótulo do efeito da entrega", () => {
  it("dá o mesmo nome ao mesmo efeito, venha do card ou da confirmação", () => {
    expect(deliveryActionLabel({ platforms: ["whatsapp"] })).toBe("Enviar agora");
    expect(deliveryActionLabel({ platforms: ["instagram"] })).toBe(
      "Publicar agora",
    );
    expect(deliveryActionLabel({ platforms: ["instagram", "whatsapp"] })).toBe(
      "Entregar agora",
    );
  });

  it("agendar vence o verbo, porque o efeito deixa de ser agora", () => {
    expect(
      deliveryActionLabel({ platforms: ["whatsapp"], scheduled: true }),
    ).toBe("Agendar");
  });

  it("sem plataforma nenhuma, não promete mensagem que ninguém vai receber", () => {
    expect(includesDirectMessage([])).toBe(false);
    expect(includesPublicPublication([])).toBe(false);
    expect(deliveryActionLabel({ platforms: [] })).toBe("Publicar agora");
  });

  it("separa mural de mensagem direta", () => {
    expect(includesDirectMessage(["instagram", "whatsapp"])).toBe(true);
    expect(includesPublicPublication(["whatsapp"])).toBe(false);
    expect(includesPublicPublication(["google_business"])).toBe(true);
  });
});
