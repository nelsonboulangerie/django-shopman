import { describe, expect, it } from "vitest";
import {
  GOOGLE_CALL_TO_ACTIONS,
  GOOGLE_POST_TYPES,
  googleBusinessEdits,
  googleBusinessOptions,
  googleCallToActionLabel,
  googlePeriodLabel,
  withGoogleBusinessEdits,
} from "~/presentation/googleBusinessPost";
import {
  googleSceneDetails,
  scenesFromDraftArtifacts,
  scenesFromFrozenCommand,
} from "~/presentation/simulatedPreview";

describe("post do Google: rótulo é o que o Google mostra", () => {
  it("oferece exatamente os botões do Google, em pt-BR, com Nenhum primeiro", () => {
    expect(GOOGLE_CALL_TO_ACTIONS.map((item) => [item.value, item.label])).toEqual([
      ["none", "Nenhum"],
      ["call", "Ligar agora"],
      ["learn_more", "Saiba mais"],
      ["order", "Pedir on-line"],
      ["shop", "Comprar"],
      ["book", "Reservar"],
      ["sign_up", "Inscrever-se"],
    ]);
    // "Como chegar" não existe entre os botões do Google.
    expect(JSON.stringify(GOOGLE_CALL_TO_ACTIONS)).not.toContain("Como chegar");
    expect(GOOGLE_POST_TYPES.map((item) => item.label)).toEqual([
      "Atualização",
      "Evento",
      "Oferta",
    ]);
  });

  it("sem escolha gravada, o padrão é nenhum botão — link não vira botão", () => {
    const options = googleBusinessOptions({ publication_format: "standard" });

    expect(options.call_to_action).toBe("none");
    expect(googleCallToActionLabel(options.call_to_action)).toBe("");
  });

  it("valor desconhecido cai no padrão, nunca num botão inventado", () => {
    const options = googleBusinessOptions({
      publication_format: "alert",
      call_to_action: "directions",
    });

    expect(options.publication_format).toBe("standard");
    expect(options.call_to_action).toBe("none");
  });

  it("a aprovação leva só o que o tipo escolhido usa", () => {
    const base = googleBusinessOptions({});
    expect(googleBusinessEdits({ ...base, call_to_action: "call" })).toEqual({
      publication_format: "standard",
      call_to_action: "call",
    });
    expect(
      googleBusinessEdits({
        ...base,
        publication_format: "event",
        event_title: " Semana do Pão ",
        event_start: "2026-10-05T08:00",
        event_end: "2026-10-11T19:00",
        offer_terms: "resto de outra escolha",
      }),
    ).toEqual({
      publication_format: "event",
      call_to_action: "none",
      event_title: "Semana do Pão",
      event_start: "2026-10-05T08:00",
      event_end: "2026-10-11T19:00",
    });
    // Oferta não escolhe botão (o Google mostra "Ver oferta") nem escreve título.
    expect(
      googleBusinessEdits({
        ...base,
        publication_format: "offer",
        call_to_action: "order",
        offer_terms: "Só on-line.",
      }),
    ).toEqual({ publication_format: "offer", offer_terms: "Só on-line." });
  });

  it("a prévia recebe as escolhas da revisão por cima das do modelo", () => {
    const merged = withGoogleBusinessEdits(
      {
        instagram: { publication_format: "story" },
        google_business: {
          publication_format: "standard",
          call_to_action: "learn_more",
          image_url: "https://img.example.test/g.jpg",
        },
      },
      { ...googleBusinessOptions({}), call_to_action: "call" },
    );

    expect(merged.google_business).toEqual({
      publication_format: "standard",
      call_to_action: "call",
      image_url: "https://img.example.test/g.jpg",
    });
    expect(merged.instagram).toEqual({ publication_format: "story" });
  });

  it("período do evento no horário da loja", () => {
    expect(googlePeriodLabel("2026-10-05T08:00", "2026-10-05T12:00")).toBe(
      "seg., 05/10, 08:00 – 12:00",
    );
    expect(googlePeriodLabel("", "2026-10-05T12:00")).toBe("");
  });
});

describe("retrato do post do Google", () => {
  it("mostra o botão escolhido, e nenhum quando não há escolha", () => {
    const [withCall] = scenesFromDraftArtifacts({
      previews: {
        google_business: {
          artifact: {
            body: "Pão quente",
            provider_fields: { publication_format: "standard", call_to_action: "call" },
          },
        },
      },
      platformLabels: { google_business: "Google Meu Negócio" },
    });
    const [plain] = scenesFromDraftArtifacts({
      previews: {
        google_business: {
          artifact: { body: "Pão quente", provider_fields: { publication_format: "standard" } },
        },
      },
      platformLabels: {},
    });

    expect(withCall!.google?.buttonLabel).toBe("Ligar agora");
    expect(withCall!.label).toBe("Atualização do Google");
    expect(plain!.google?.buttonLabel).toBe("");
  });

  it("evento e oferta dizem o tipo, o título e o período", () => {
    expect(
      googleSceneDetails({
        publication_format: "offer",
        offer_title: "Semana do Pão",
        offer_start: "2026-09-25T12:00",
        offer_end: "2026-10-11T23:59",
      }),
    ).toEqual({
      postTypeLabel: "Oferta",
      buttonLabel: "Ver oferta",
      title: "Semana do Pão",
      period: "sex., 25/09, 12:00 – dom., 11/10, 23:59",
    });
    const [event] = scenesFromDraftArtifacts({
      previews: {
        google_business: {
          artifact: {
            body: "Venha",
            provider_fields: {
              publication_format: "event",
              event_title: "Semana do Pão",
              event_start: "2026-10-05T08:00",
              event_end: "2026-10-05T12:00",
            },
          },
        },
      },
      platformLabels: {},
    });
    expect(event!.label).toBe("Evento no Google");
  });

  it("na confirmação vale a escolha da revisão, que viaja no comando", () => {
    const [scene] = scenesFromFrozenCommand({
      frozenBody: {
        body: "Pão quente",
        google_business: { publication_format: "standard", call_to_action: "call" },
      },
      platforms: ["google_business"],
      platformLabels: {},
      platformContent: {
        google_business: { publication_format: "standard", call_to_action: "learn_more" },
      },
    });

    expect(scene!.google?.buttonLabel).toBe("Ligar agora");
  });
});
