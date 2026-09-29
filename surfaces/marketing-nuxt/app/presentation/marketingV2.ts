import type {
  Choice,
  MarketingPlatformCapability,
  MarketingProviderCapability,
  MarketingProviderFormatCapability,
} from "~/types/campaign";
import type { Platform } from "~/composables/usePlatforms";

export type MarketingV2DestinationState =
  "executable" | "limited" | "disconnected" | "unknown" | "available";

export type MarketingV2Destination = {
  ref: string;
  label: string;
  deliveryLabel: string;
  formatLabels: string[];
  formats: MarketingV2Format[];
  connectorState: "active" | "dormant" | "unknown";
  state: MarketingV2DestinationState;
  stateLabel: string;
  detail: string;
  selectable: boolean;
};

export type MarketingV2FormatState =
  "executable" | "partial" | "planned" | "gated" | "unimplemented";

export type MarketingV2Format = {
  ref: string;
  label: string;
  state: MarketingV2FormatState;
  stateLabel: string;
  detail: string;
  selectable: boolean;
};

type DestinationInput = {
  choices: readonly Choice[];
  capabilities: readonly MarketingPlatformCapability[];
  providerCapabilities?: readonly MarketingProviderCapability[];
  readiness: readonly Platform[];
};

function stateFor(
  platform: Platform | undefined,
  selectable: boolean,
  provider: MarketingProviderCapability | undefined,
): Pick<MarketingV2Destination, "state" | "stateLabel" | "detail"> {
  if (!selectable) {
    if (provider?.connector_state === "dormant") {
      return {
        state: "available",
        stateLabel: "Planejado",
        detail:
          provider.notes[0] ||
          "O conector ainda não faz parte da operação executável.",
      };
    }
    return {
      state: "available",
      stateLabel: "Não implementada",
      detail:
        provider?.notes[0] ||
        "A API reconhece este destino, mas o Shopman ainda não o executa.",
    };
  }
  if (!platform) {
    return {
      state: "available",
      stateLabel: "Disponível · sem diagnóstico",
      detail:
        "Pode ser escolhido, mas a situação da conexão ainda não foi verificada.",
    };
  }
  if (platform.state === "ready") {
    return {
      state: "executable",
      stateLabel: "Executável",
      detail:
        platform.reason || "Conexão verificada e disponível para publicação.",
    };
  }
  if (platform.state === "degraded") {
    return {
      state: "limited",
      stateLabel: "Executável com limite",
      detail:
        platform.limitation ||
        platform.reason ||
        "A conexão funciona com uma limitação conhecida.",
    };
  }
  if (platform.state === "blocked") {
    return {
      state: "disconnected",
      stateLabel:
        platform.reason_code === "platform_switched_off"
          ? "Desligada"
          : "Não configurada",
      detail:
        platform.reason ||
        "A plataforma pode ser conectada, mas ainda não executa publicações.",
    };
  }
  return {
    state: "unknown",
    stateLabel: "Conectável · não verificada",
    detail:
      platform.reason ||
      "A conexão existe no catálogo, mas não há diagnóstico confiável agora.",
  };
}

function formatDetail(format: MarketingProviderFormatCapability): string {
  const implemented = format.implemented_variants.length
    ? "O conector já executa parte deste formato."
    : "";
  return [implemented, format.notes[0], format.media.notes[0]]
    .filter(Boolean)
    .join(" ");
}

function providerFormats(
  provider: MarketingProviderCapability | undefined,
  executable: MarketingPlatformCapability | undefined,
  destinationSelectable: boolean,
): MarketingV2Format[] {
  const executableRefs = new Set(
    executable?.formats.map((format) => format.ref) ?? [],
  );
  if (!provider) {
    return (executable?.formats ?? []).map((format) => ({
      ref: format.ref,
      label: format.label,
      state: "executable",
      stateLabel: "Executável",
      detail: "Formato disponível no contrato operacional atual.",
      selectable: destinationSelectable,
    }));
  }
  return provider.formats.map((format) => {
    const executableNow =
      destinationSelectable &&
      (executableRefs.has(format.ref) ||
        (format.operational_format_refs ?? []).some((ref) =>
          executableRefs.has(ref),
        ));
    if (executableNow) {
      const partial = format.implementation_state === "partial";
      return {
        ref: format.ref,
        label: format.label,
        state: partial ? "partial" : "executable",
        stateLabel: partial ? "Executável em parte" : "Executável",
        detail:
          formatDetail(format) ||
          "Formato disponível no contrato operacional atual.",
        selectable: true,
      };
    }
    if (format.implementation_state === "planned") {
      return {
        ref: format.ref,
        label: format.label,
        state: "planned",
        stateLabel: "Planejado",
        detail: formatDetail(format) || "Ainda não implementado no conector.",
        selectable: false,
      };
    }
    if (format.implementation_state === "gated") {
      return {
        ref: format.ref,
        label: format.label,
        state: "gated",
        stateLabel: "Com gate",
        detail:
          formatDetail(format) ||
          "Depende de aprovação, conexão ou prova controlada.",
        selectable: false,
      };
    }
    return {
      ref: format.ref,
      label: format.label,
      state: "unimplemented",
      stateLabel: "Não implementado",
      detail:
        formatDetail(format) ||
        "A plataforma suporta este formato, mas o conector ainda não.",
      selectable: false,
    };
  });
}

/**
 * Une três verdades sem confundi-las:
 *
 * - `choices`: allow-list que o operador pode realmente selecionar;
 * - `capabilities`: formatos/campos que o domínio sabe selar;
 * - `readiness`: situação viva da conexão neste ambiente.
 *
 * Uma conexão bloqueada continua visível. Bloqueio muda o estado e a explicação,
 * nunca apaga a plataforma do produto.
 */
export function marketingV2Destinations({
  choices,
  capabilities,
  providerCapabilities = [],
  readiness,
}: DestinationInput): MarketingV2Destination[] {
  const choiceMap = new Map(choices.map((item) => [item.value, item]));
  const capabilityMap = new Map(
    capabilities.map((item) => [item.platform, item]),
  );
  const readinessMap = new Map(readiness.map((item) => [item.platform, item]));
  const providerMap = new Map(
    providerCapabilities.map((item) => [item.platform, item]),
  );
  const refs = [
    ...providerCapabilities.map((item) => item.platform),
    ...capabilities.map((item) => item.platform),
    ...choices.map((item) => item.value),
    ...readiness.map((item) => item.platform),
  ].filter((ref, index, all) => all.indexOf(ref) === index);

  return refs.map((ref) => {
    const choice = choiceMap.get(ref);
    const capability = capabilityMap.get(ref);
    const provider = providerMap.get(ref);
    const platform = readinessMap.get(ref);
    const selectable = Boolean(choice && capability);
    const state = stateFor(platform, selectable, provider);
    const formats = providerFormats(provider, capability, selectable);
    const deliveryKind =
      capability?.delivery_kind || provider?.formats[0]?.delivery_kind;
    return {
      ref,
      label:
        choice?.label ||
        provider?.label ||
        capability?.label ||
        platform?.label ||
        ref,
      deliveryLabel:
        deliveryKind === "direct_message"
          ? "Mensagem direta"
          : deliveryKind === "creator_handoff"
            ? "Rascunho para concluir no app"
            : "Publicação pública",
      formatLabels: formats.map((format) => format.label),
      formats,
      connectorState: provider?.connector_state ?? "unknown",
      selectable,
      ...state,
    };
  });
}
