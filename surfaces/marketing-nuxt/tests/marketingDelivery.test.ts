import { describe, expect, it } from "vitest";
import {
  deliveryActionLabel,
  includesDirectMessage,
  includesPublicPost,
  outgoingImageUrl,
} from "~/presentation/marketingDelivery";

describe("rótulo do último gesto", () => {
  it("dá verbo próprio a cada ato, porque são atos diferentes", () => {
    // Mensagem se envia e não se apaga; postagem se publica e se apaga. Só quando o
    // anúncio faz os dois é que não há verbo específico — aí vale o genérico da casa.
    expect(deliveryActionLabel({ platforms: ["whatsapp"] })).toBe("Enviar agora");
    expect(deliveryActionLabel({ platforms: ["instagram"] })).toBe(
      "Publicar agora",
    );
    expect(deliveryActionLabel({ platforms: ["instagram", "whatsapp"] })).toBe(
      "Disparar agora",
    );
  });

  it("agendar vence os três, porque 'agora' mentiria sobre o quando", () => {
    expect(
      deliveryActionLabel({ platforms: ["instagram", "whatsapp"], scheduled: true }),
    ).toBe("Agendar");
  });

  it("sem plataforma nenhuma, não promete mensagem que ninguém vai receber", () => {
    expect(includesDirectMessage([])).toBe(false);
    expect(includesPublicPost([])).toBe(false);
    expect(deliveryActionLabel({ platforms: [] })).toBe("Publicar agora");
  });

  it("separa mural de mensagem — a distinção que dá o verbo", () => {
    expect(includesDirectMessage(["instagram", "whatsapp"])).toBe(true);
    expect(includesPublicPost(["whatsapp"])).toBe(false);
    expect(includesPublicPost(["google_business"])).toBe(true);
  });
});

describe("a foto que vai sair", () => {
  it("procura no conteúdo por plataforma, não só no campo do topo", () => {
    // O campo óbvio quase sempre está vazio; a foto de verdade mora na plataforma.
    // Quem olhar só o topo conclui "sem foto" para um anúncio que tem.
    expect(
      outgoingImageUrl({
        image_url: "",
        platform_content: { whatsapp: {}, instagram: { image_url: "/story.jpg" } },
      }),
    ).toBe("/story.jpg");
  });

  it("o campo do topo ganha quando existe", () => {
    expect(
      outgoingImageUrl({
        image_url: "/capa.jpg",
        platform_content: { instagram: { image_url: "/story.jpg" } },
      }),
    ).toBe("/capa.jpg");
  });

  it("sem foto em lugar nenhum devolve vazio, e não um caminho quebrado", () => {
    expect(outgoingImageUrl({})).toBe("");
    expect(
      outgoingImageUrl({ image_url: "  ", platform_content: { instagram: {} } }),
    ).toBe("");
  });
});
