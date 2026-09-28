import { describe, expect, it } from "vitest";
import type { Platform } from "../app/composables/usePlatforms";
import type {
  Choice,
  MarketingPlatformCapability,
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

describe("mapa de destinos do Marketing V2", () => {
  it("mantém Google visível quando a conexão ainda não está configurada", () => {
    const choices: Choice[] = [{ value: "google_business", label: "Google" }];
    const destinations = marketingV2Destinations({
      choices,
      capabilities: [googleCapability],
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
      capabilities: [googleCapability],
      readiness: [],
    });

    expect(destinations[0]).toEqual(
      expect.objectContaining({
        ref: "google_business",
        selectable: false,
        state: "available",
        stateLabel: "Disponível",
      }),
    );
  });

  it("expõe conexão pronta como executável sem perder os formatos", () => {
    const destinations = marketingV2Destinations({
      choices: [{ value: "google_business", label: "Google" }],
      capabilities: [googleCapability],
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
});
