import { describe, expect, it } from "vitest";
import {
  deliveryActionLabel,
  includesDirectMessage,
  includesPublicPost,
  outgoingImageUrl,
  reachLines,
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

describe("o que o disparo alcança", () => {
  // ⚠️ Um número só, chamado "destinos", faz "37" valer para pessoa e para mural. A
  // caixa de confirmação já contava certo; o diálogo de RECUPERAÇÃO — onde se autoriza
  // reenvio, e onde a confusão custa mais caro — continuava no modelo antigo. A regra
  // vive aqui porque duas telas precisam dela, e uma delas não tinha.
  it("conta pessoas na mensagem e uma postagem por mural", () => {
    expect(
      reachLines({ platforms: ["whatsapp", "instagram"], audienceCount: 37 }),
    ).toEqual(["WhatsApp · 37 pessoas", "Instagram · 1 postagem"]);
  });

  it("o singular da pessoa é pessoa", () => {
    expect(reachLines({ platforms: ["whatsapp"], audienceCount: 1 })).toEqual([
      "WhatsApp · 1 pessoa",
    ]);
  });

  // ⚠️ Murais NÃO se juntam numa linha só: "Instagram, Facebook · 1 postagem em cada"
  // obriga o leitor a distribuir o "1" entre as duas, e com uma plataforma sozinha o
  // "em cada" fica sem complemento e não quer dizer nada.
  it("dá uma linha a cada mural, sem pedir que o leitor distribua o número", () => {
    expect(
      reachLines({ platforms: ["instagram", "facebook"], audienceCount: 0 }),
    ).toEqual(["Instagram · 1 postagem", "Facebook · 1 postagem"]);
  });

  it("sem plataforma, não inventa alcance", () => {
    expect(reachLines({ platforms: [], audienceCount: 99 })).toEqual([]);
  });
});
