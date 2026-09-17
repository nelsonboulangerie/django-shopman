import { describe, expect, it } from "vitest";
import {
  deliveryActionLabel,
  includesDirectMessage,
  includesPublicPublication,
} from "~/presentation/marketingDelivery";

describe("rótulo do último gesto", () => {
  it("só o botão que dispara diz disparar, e ele diz sempre a mesma coisa", () => {
    // O destino não muda o verbo: a caixa já escreve, na linha acima do botão, o que
    // vai para cada plataforma. Três verbos diferentes ali custavam a palavra que a
    // casa usa no resto do caminho sem acrescentar um fato novo.
    expect(deliveryActionLabel({})).toBe("Disparar agora");
  });

  it("agendar vence o verbo, porque 'agora' mentiria sobre o quando", () => {
    expect(deliveryActionLabel({ scheduled: true })).toBe("Agendar");
  });

  it("separa mural de mensagem direta — que é o que a tela explica em prosa", () => {
    expect(includesDirectMessage(["instagram", "whatsapp"])).toBe(true);
    expect(includesPublicPublication(["whatsapp"])).toBe(false);
    expect(includesPublicPublication(["google_business"])).toBe(true);
    expect(includesDirectMessage([])).toBe(false);
    expect(includesPublicPublication([])).toBe(false);
  });
});
