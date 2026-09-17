// O caminho do disparo até a revisão, e o que a tela diz depois da decisão.
//
// As duas queixas do gestor viram teste aqui: o disparo que não dizia nada na tela em
// que ele estava, e o "aceito pelo provedor" que era correto e inútil.
import { describe, expect, it } from "vitest";
import { fireDispatchRoute } from "~/presentation/campaignFire";
import {
  acceptedAwaitingConfirmationNote,
  announcementDispatchNotice,
  decisionOutcomeNotice,
  deliverySettled,
  deliveryTrackingCeilingMs,
  DELIVERY_TRACKING_POLICY,
} from "~/presentation/marketingResult";
import {
  preserveMarketingReceipt,
  restoreMarketingReceipt,
} from "~/utils/marketingReceipt";
import type { MarketingCommandReceipt } from "~/types/campaign";

function fireReceipt(
  over: Partial<MarketingCommandReceipt> = {},
): MarketingCommandReceipt {
  return {
    ref: "fire-receipt-77",
    kind: "fire",
    state: "completed",
    base_version: 1,
    resulting_version: 2,
    // O recurso do disparo é a CAMPANHA; o anúncio nasce dele, e é o desfecho que diz.
    resource_ref: "campaign:3",
    outcome: { announcement_ref: "announcement:77", audience_count: 2 },
    created_at: "2026-09-17T10:00:00-03:00",
    completed_at: "2026-09-17T10:00:01-03:00",
    ...over,
  };
}

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  };
}

describe("o disparo cai direto na revisão", () => {
  it("leva a tela ao anúncio, sem escala, dizendo de onde veio", () => {
    expect(
      fireDispatchRoute({ replayed: false, announcement: { pk: 77 } as never }),
    ).toEqual({
      path: "/announcements/77",
      query: { dispatch: "new" },
      hash: "#review",
    });
    expect(
      fireDispatchRoute({ replayed: true, announcement: { pk: 77 } as never }),
    ).toEqual({
      path: "/announcements/77",
      query: { dispatch: "replayed" },
      hash: "#review",
    });
  });

  it("preserva o comprovante do disparo, cujo recurso é a campanha", () => {
    const storage = memoryStorage();

    expect(
      preserveMarketingReceipt(77, fireReceipt(), { storage, now: 1_000 }),
    ).toBe(true);
    expect(restoreMarketingReceipt(77, { storage, now: 2_000 })).toEqual(
      fireReceipt(),
    );
    // O anúncio de outro disparo continua sendo recusado: a prova não atravessa recurso.
    expect(
      preserveMarketingReceipt(78, fireReceipt(), { storage, now: 1_000 }),
    ).toBe(false);
  });

  it("conta pessoas na mensagem e plataformas na postagem", () => {
    expect(
      announcementDispatchNotice({
        platforms: ["whatsapp"],
        audienceCount: 1,
        replayed: false,
      }),
    ).toMatchObject({
      detail: "1 pessoa elegível. Nada saiu ainda.",
      replayNote: "",
    });
    expect(
      announcementDispatchNotice({
        platforms: ["instagram", "facebook"],
        audienceCount: 0,
        replayed: false,
      }).detail,
    ).toBe("2 postagens públicas preparadas. Nada foi publicado ainda.");
  });

  it("diz que o toque repetido não duplicou anúncio nenhum", () => {
    expect(
      announcementDispatchNotice({
        platforms: ["whatsapp"],
        audienceCount: 4,
        replayed: true,
      }).replayNote,
    ).toContain("nenhum anúncio foi duplicado");
  });
});

describe("depois da decisão a tela continua dizendo o que aconteceu", () => {
  it("separa mensagem, postagem, disparo misto e agendamento", () => {
    expect(
      decisionOutcomeNotice({
        action: "approve",
        publishMode: "now",
        includesDirectMessage: true,
        includesPublicPost: false,
      }).title,
    ).toBe("Enviado");
    expect(
      decisionOutcomeNotice({
        action: "approve",
        publishMode: "now",
        includesDirectMessage: false,
        includesPublicPost: true,
      }).title,
    ).toBe("Publicado");
    expect(
      decisionOutcomeNotice({
        action: "approve",
        publishMode: "now",
        includesDirectMessage: true,
        includesPublicPost: true,
      }).title,
    ).toBe("Disparado");
    expect(
      decisionOutcomeNotice({
        action: "approve",
        publishMode: "scheduled",
        includesDirectMessage: true,
        includesPublicPost: false,
        scheduledSummary: "quinta-feira, 18 de setembro de 2026 às 07:30",
      }).title,
    ).toBe("Agendado para quinta-feira, 18 de setembro de 2026 às 07:30");
  });

  it("nunca promete entrega no instante da decisão", () => {
    const immediate = decisionOutcomeNotice({
      action: "approve",
      publishMode: "now",
      includesDirectMessage: true,
      includesPublicPost: false,
    });

    // A promessa é "entrou na fila", nunca "chegou" — a directive ainda nem rodou.
    expect(immediate.detail).toContain("na fila");
    expect(immediate.detail).toContain("confirmação");
    expect(immediate.detail).not.toMatch(/entregue|enviada com sucesso/i);
  });

  it("recusa não vira promessa de envio", () => {
    expect(
      decisionOutcomeNotice({
        action: "reject",
        includesDirectMessage: true,
        includesPublicPost: true,
      }),
    ).toMatchObject({ title: "Anúncio recusado", tone: "quiet" });
  });
});

describe("o acompanhamento tem fim e não inventa sucesso", () => {
  it("só para quando o estado deixa de ser pendente", () => {
    expect(deliverySettled(null)).toBe(false);
    expect(deliverySettled(undefined)).toBe(false);
    for (const state of ["not_started", "fanout_pending", "delivering"] as const) {
      expect(deliverySettled({ state })).toBe(false);
    }
    for (const state of [
      "succeeded",
      "completed_with_failures",
      "unknown",
      "cancelled",
      "expired",
      "legacy_untracked",
    ] as const) {
      expect(deliverySettled({ state })).toBe(true);
    }
  });

  it("espera cerca de meio minuto e desiste — nunca fica batendo para sempre", () => {
    const ceiling = deliveryTrackingCeilingMs();

    expect(DELIVERY_TRACKING_POLICY.attempts).toBeLessThanOrEqual(8);
    expect(ceiling).toBeGreaterThanOrEqual(20_000);
    expect(ceiling).toBeLessThanOrEqual(45_000);
  });
});

describe("aceito pelo provedor diz o que fazer com isso", () => {
  it("explica de onde vem a confirmação e por que não reenviar", () => {
    const note = acceptedAwaitingConfirmationNote(1);

    expect(note).toContain("Uma entrega foi aceita pelo provedor");
    expect(note).toContain("confirmação");
    expect(note).toContain("não reenvie");
    expect(acceptedAwaitingConfirmationNote(3)).toContain(
      "3 entregas foram aceitas pelo provedor",
    );
  });

  it("cala quando não há nada aceito", () => {
    expect(acceptedAwaitingConfirmationNote(0)).toBe("");
  });
});
