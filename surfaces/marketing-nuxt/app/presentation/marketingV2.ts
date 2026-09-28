import type { Choice, MarketingPlatformCapability } from "~/types/campaign";
import type { Platform } from "~/composables/usePlatforms";

export type MarketingV2DestinationState =
  "executable" | "limited" | "disconnected" | "unknown" | "available";

export type MarketingV2Destination = {
  ref: string;
  label: string;
  deliveryLabel: string;
  formatLabels: string[];
  state: MarketingV2DestinationState;
  stateLabel: string;
  detail: string;
  selectable: boolean;
};

type DestinationInput = {
  choices: readonly Choice[];
  capabilities: readonly MarketingPlatformCapability[];
  readiness: readonly Platform[];
};

function stateFor(
  platform: Platform | undefined,
  selectable: boolean,
): Pick<MarketingV2Destination, "state" | "stateLabel" | "detail"> {
  if (!selectable) {
    return {
      state: "available",
      stateLabel: "Disponível",
      detail:
        "O destino é conhecido, mas ainda não foi liberado para campanhas neste contrato.",
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
  readiness,
}: DestinationInput): MarketingV2Destination[] {
  const choiceMap = new Map(choices.map((item) => [item.value, item]));
  const capabilityMap = new Map(
    capabilities.map((item) => [item.platform, item]),
  );
  const readinessMap = new Map(readiness.map((item) => [item.platform, item]));
  const refs = [
    ...capabilities.map((item) => item.platform),
    ...choices.map((item) => item.value),
    ...readiness.map((item) => item.platform),
  ].filter((ref, index, all) => all.indexOf(ref) === index);

  return refs.map((ref) => {
    const choice = choiceMap.get(ref);
    const capability = capabilityMap.get(ref);
    const platform = readinessMap.get(ref);
    const selectable = Boolean(choice && capability);
    const state = stateFor(platform, selectable);
    return {
      ref,
      label: choice?.label || capability?.label || platform?.label || ref,
      deliveryLabel:
        capability?.delivery_kind === "direct_message"
          ? "Mensagem direta"
          : "Publicação pública",
      formatLabels: capability?.formats.map((format) => format.label) ?? [],
      selectable,
      ...state,
    };
  });
}
