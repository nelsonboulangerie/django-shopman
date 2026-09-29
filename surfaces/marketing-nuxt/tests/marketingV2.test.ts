import { describe, expect, it } from "vitest";
import type { Platform } from "../app/composables/usePlatforms";
import type {
  Choice,
  MarketingPlatformCapability,
  MarketingProviderCapability,
} from "../app/types/campaign";
import { marketingV2Destinations } from "../app/presentation/marketingV2";

function readiness(
  platform: string,
  state: Platform["state"],
  reason = "",
): Platform {
  return {
    platform,
    label: platform,
    kind: "publication",
    state,
    reason_code: state === "blocked" ? "provider_not_configured" : "",
    version: 1,
    ready: state === "ready",
    checked_at: "2026-09-28T10:00:00-03:00",
    facts_as_of: null,
    fresh_until: null,
    source_status: "live",
    reason,
    action: "",
    limitation: "",
    in_use: false,
  };
}

const googleCapability: MarketingPlatformCapability = {
  platform: "google_business",
  label: "Google Meu Negócio",
  delivery_kind: "publication",
  default_format: "standard",
  formats: [
    {
      ref: "standard",
      label: "Atualização",
      provider_fields: ["publication_format", "call_to_action"],
      required_provider_fields: ["publication_format"],
      media_required: false,
    },
    {
      ref: "event",
      label: "Evento",
      provider_fields: ["publication_format"],
      required_provider_fields: ["publication_format"],
      media_required: false,
    },
    {
      ref: "offer",
      label: "Oferta",
      provider_fields: ["publication_format"],
      required_provider_fields: ["publication_format"],
      media_required: false,
    },
  ],
};

function providerCapability(
  partial: Partial<MarketingProviderCapability> = {},
): MarketingProviderCapability {
  return {
    platform: "google_business",
    label: "Google",
    connector_state: "active",
    notes: [],
    formats: googleCapability.formats.map((format) => ({
      ref: format.ref,
      label: format.label,
      delivery_kind: "publication",
      implementation_state: "ready",
      implemented_variants: [format.ref],
      fields: [],
      media: {
        min_items: 0,
        max_items: 1,
        kinds: ["image"],
        image_formats: ["jpeg"],
        video_formats: [],
        notes: [],
      },
      cta_model: "provider_choice",
      notes: [],
    })),
    ...partial,
  };
}

describe("mapa de destinos do Marketing V2", () => {
  it("mantém Google visível quando a conexão ainda não está configurada", () => {
    const choices: Choice[] = [{ value: "google_business", label: "Google" }];
    const destinations = marketingV2Destinations({
      choices,
      capabilities: [googleCapability],
      providerCapabilities: [providerCapability()],
      readiness: [
        readiness(
          "google_business",
          "blocked",
          "Credencial do Perfil da Empresa ausente.",
        ),
      ],
    });

    expect(destinations).toEqual([
      expect.objectContaining({
        ref: "google_business",
        label: "Google",
        selectable: true,
        state: "disconnected",
        stateLabel: "Não configurada",
        formatLabels: ["Atualização", "Evento", "Oferta"],
      }),
    ]);
  });

  it("separa catálogo conhecido da allow-list executável", () => {
    const destinations = marketingV2Destinations({
      choices: [],
      capabilities: [],
      providerCapabilities: [providerCapability()],
      readiness: [],
    });

    expect(destinations[0]).toEqual(
      expect.objectContaining({
        ref: "google_business",
        selectable: false,
        state: "available",
        stateLabel: "Não implementada",
      }),
    );
  });

  it("expõe conexão pronta como executável sem perder os formatos", () => {
    const destinations = marketingV2Destinations({
      choices: [{ value: "google_business", label: "Google" }],
      capabilities: [googleCapability],
      providerCapabilities: [providerCapability()],
      readiness: [readiness("google_business", "ready")],
    });

    expect(destinations[0]).toEqual(
      expect.objectContaining({
        state: "executable",
        stateLabel: "Executável",
        selectable: true,
      }),
    );
  });

  it("mostra formatos planejados e com gate sem torná-los executáveis", () => {
    const tiktok = providerCapability({
      platform: "tiktok",
      label: "TikTok",
      connector_state: "dormant",
      notes: ["Connector dormente: oferecer primeiro o handoff de rascunho."],
      formats: [
        {
          ref: "photo_draft",
          label: "Rascunho de fotos",
          delivery_kind: "creator_handoff",
          implementation_state: "planned",
          implemented_variants: [],
          fields: [],
          media: {
            min_items: 1,
            max_items: 35,
            kinds: ["image"],
            image_formats: ["jpeg"],
            video_formats: [],
            notes: ["A publicação termina dentro do TikTok."],
          },
          cta_model: "none",
          notes: [],
        },
        {
          ref: "photo",
          label: "Publicação direta",
          delivery_kind: "publication",
          implementation_state: "gated",
          implemented_variants: [],
          fields: [],
          media: {
            min_items: 1,
            max_items: 35,
            kinds: ["image"],
            image_formats: ["jpeg"],
            video_formats: [],
            notes: [],
          },
          cta_model: "none",
          notes: ["Exige auditoria do TikTok."],
        },
      ],
    });

    const [destination] = marketingV2Destinations({
      choices: [],
      capabilities: [],
      providerCapabilities: [tiktok],
      readiness: [],
    });

    expect(destination).toEqual(
      expect.objectContaining({
        ref: "tiktok",
        connectorState: "dormant",
        selectable: false,
        stateLabel: "Planejado",
        deliveryLabel: "Rascunho para concluir no app",
      }),
    );
    expect(destination.formats).toEqual([
      expect.objectContaining({ state: "planned", selectable: false }),
      expect.objectContaining({ state: "gated", selectable: false }),
    ]);
  });

  it("expõe formatos do provider ausentes da allow-list como não implementados", () => {
    const instagram = providerCapability({
      platform: "instagram",
      label: "Instagram",
      formats: [
        {
          ...providerCapability().formats[0],
          ref: "feed",
          label: "Feed",
          implementation_state: "partial",
          implemented_variants: ["image"],
        },
        {
          ...providerCapability().formats[0],
          ref: "reel",
          label: "Reel",
          implementation_state: "planned",
          implemented_variants: [],
        },
      ],
    });
    const executable: MarketingPlatformCapability = {
      ...googleCapability,
      platform: "instagram",
      label: "Instagram",
      default_format: "feed",
      formats: [
        {
          ...googleCapability.formats[0],
          ref: "feed",
          label: "Feed",
        },
      ],
    };

    const [destination] = marketingV2Destinations({
      choices: [{ value: "instagram", label: "Instagram" }],
      capabilities: [executable],
      providerCapabilities: [instagram],
      readiness: [readiness("instagram", "ready")],
    });

    expect(destination.formats).toEqual([
      expect.objectContaining({ state: "partial", selectable: true }),
      expect.objectContaining({ state: "planned", selectable: false }),
    ]);
  });
});
