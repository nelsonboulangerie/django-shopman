// A prévia em tamanho real: quantos retratos, quais, e de ONDE sai o conteúdo de cada um.
//
// O de-para fonte→lugar é o coração deste arquivo: na edição sai o rascunho corrente,
// na confirmação sai o corpo congelado do comando. Trocar as duas fontes de lugar é o
// defeito que este teste existe para não deixar entrar.
import { describe, expect, it } from "vitest";
import {
  joinPlatformLabels,
  scenesFromDraftArtifacts,
  scenesFromFrozenCommand,
  simulatedSceneKind,
  simulatedScenes,
} from "~/presentation/simulatedPreview";

const LABELS = {
  instagram: "Instagram",
  facebook: "Facebook",
  google_business: "Google",
  whatsapp: "WhatsApp",
};

function content(over: Partial<Record<string, unknown>> = {}) {
  return {
    body: "Pães de fermentação natural saíram do forno.",
    hashtags: ["#padaria"],
    imageUrl: "https://example.invalid/pao.jpg",
    link: "",
    ...over,
  } as {
    body: string;
    hashtags: string[];
    imageUrl: string;
    link: string;
  };
}

describe("o formato manda, não a plataforma", () => {
  it("lê o formato declarado e cai na plataforma quando o artefato é antigo", () => {
    expect(
      simulatedSceneKind({ platform: "instagram", publicationFormat: "story" }),
    ).toBe("story");
    expect(
      simulatedSceneKind({ platform: "instagram", publicationFormat: "feed" }),
    ).toBe("feed");
    expect(
      simulatedSceneKind({
        platform: "google_business",
        publicationFormat: "standard",
      }),
    ).toBe("google_update");
    // WhatsApp é mensagem, e mensagem não tem formato de mural.
    expect(
      simulatedSceneKind({ platform: "whatsapp", publicationFormat: "feed" }),
    ).toBe("whatsapp_message");
    // Artefato histórico sem formato continua legível: a plataforma decide.
    expect(simulatedSceneKind({ platform: "facebook" })).toBe("feed");
    expect(simulatedSceneKind({ platform: "google_business" })).toBe(
      "google_update",
    );
  });

  it("junta Instagram e Facebook num Feed só e separa Story de Feed do mesmo Instagram", () => {
    const shared = content();
    const scenes = simulatedScenes([
      {
        platform: "instagram",
        platformLabel: "Instagram",
        publicationFormat: "story",
        content: shared,
      },
      {
        platform: "facebook",
        platformLabel: "Facebook",
        publicationFormat: "feed",
        content: shared,
      },
      {
        platform: "google_business",
        platformLabel: "Google",
        publicationFormat: "feed",
        content: shared,
      },
    ]);

    expect(scenes.map((scene) => scene.label)).toEqual([
      "Story no Instagram",
      "Feed no Facebook e Google",
    ]);
    expect(scenes.map((scene) => scene.kind)).toEqual(["story", "feed"]);
    expect(scenes.map((scene) => scene.key)).toEqual([
      "story:instagram",
      "feed:facebook+google_business",
    ]);
  });

  it("volta a separar quando o mesmo formato leva conteúdos diferentes", () => {
    // Um retrato só mostraria o Facebook com o texto do Instagram — que é precisamente
    // o engano que a prévia deveria evitar.
    const scenes = simulatedScenes([
      {
        platform: "instagram",
        platformLabel: "Instagram",
        publicationFormat: "feed",
        content: content({ body: "Texto do Instagram" }),
      },
      {
        platform: "facebook",
        platformLabel: "Facebook",
        publicationFormat: "feed",
        content: content({ body: "Texto do Facebook" }),
      },
    ]);

    expect(scenes).toHaveLength(2);
    expect(scenes.map((scene) => scene.body)).toEqual([
      "Texto do Instagram",
      "Texto do Facebook",
    ]);
  });

  it("Google e WhatsApp não repetem a plataforma no rótulo", () => {
    const scenes = simulatedScenes([
      {
        platform: "google_business",
        platformLabel: "Google",
        publicationFormat: "standard",
        content: content(),
      },
      {
        platform: "whatsapp",
        platformLabel: "WhatsApp",
        publicationFormat: "",
        content: content({ body: "Mensagem" }),
      },
    ]);

    expect(scenes.map((scene) => scene.label)).toEqual([
      "Atualização do Google",
      "Mensagem no WhatsApp",
    ]);
    expect(scenes.map((scene) => scene.directMessage)).toEqual([false, true]);
  });

  it("escreve a lista de plataformas como se fala", () => {
    expect(joinPlatformLabels([])).toBe("");
    expect(joinPlatformLabels(["Instagram"])).toBe("Instagram");
    expect(joinPlatformLabels(["Instagram", "Facebook"])).toBe(
      "Instagram e Facebook",
    );
    expect(joinPlatformLabels(["Instagram", "Facebook", "Google"])).toBe(
      "Instagram, Facebook e Google",
    );
  });
});

describe("de onde sai o conteúdo de cada lugar", () => {
  it("na tela de edição, sai do rascunho corrente já resolvido pelo servidor", () => {
    const scenes = scenesFromDraftArtifacts({
      previews: {
        instagram: {
          artifact: {
            body: "Rascunho sendo editado agora",
            hashtags: ["padaria", "lote"],
            image_url: "https://example.invalid/vertical.jpg",
            link: "/produtos/pao-artesanal/",
            provider_fields: { publication_format: "story" },
          },
        },
      },
      platformLabels: LABELS,
    });

    expect(scenes).toHaveLength(1);
    expect(scenes[0]?.body).toBe("Rascunho sendo editado agora");
    expect(scenes[0]?.kind).toBe("story");
    // Hashtag é guardada limpa e lida com "#": o retrato mostra o que sai.
    expect(scenes[0]?.hashtags).toEqual(["#padaria", "#lote"]);
    expect(scenes[0]?.link).toBe("/produtos/pao-artesanal/");
  });

  it("na confirmação, sai do corpo CONGELADO do comando, nunca do anúncio na tela", () => {
    const scenes = scenesFromFrozenCommand({
      frozenBody: {
        base_version: 3,
        body: "  Texto selado no comando  ",
        hashtags: ["padaria"],
      },
      platforms: ["instagram", "whatsapp"],
      platformLabels: LABELS,
      platformContent: {
        instagram: {
          publication_format: "story",
          image_url: "https://example.invalid/vertical.jpg",
        },
        whatsapp: {},
      },
      imageUrl: "https://example.invalid/quadrada.jpg",
    });

    expect(scenes.map((scene) => scene.kind)).toEqual([
      "story",
      "whatsapp_message",
    ]);
    expect(scenes.map((scene) => scene.body)).toEqual([
      "Texto selado no comando",
      "Texto selado no comando",
    ]);
    expect(scenes.map((scene) => scene.hashtags)).toEqual([
      ["#padaria"],
      ["#padaria"],
    ]);
    // A foto por plataforma vence a do topo, que é o último recurso.
    expect(scenes[0]?.imageUrl).toBe("https://example.invalid/vertical.jpg");
    expect(scenes[1]?.imageUrl).toBe("https://example.invalid/quadrada.jpg");
  });

  it("sem corpo congelado, a confirmação não inventa retrato", () => {
    expect(
      scenesFromFrozenCommand({
        frozenBody: undefined,
        platforms: [],
        platformLabels: LABELS,
      }),
    ).toEqual([]);
  });
});
