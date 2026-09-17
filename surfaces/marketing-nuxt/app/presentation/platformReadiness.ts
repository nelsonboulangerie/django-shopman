// Prontidão de plataforma ANTES do clique.
//
// O formulário de campanha e o card de revisão ofereciam as quatro plataformas como
// se todas publicassem, e a recusa só aparecia depois de aprovar. O servidor já sabe
// o estado e o motivo (`/marketing/platforms/`, `delivery_readiness.py`); esta camada
// só traduz isso em pílula pintada e frase visível junto da escolha.
//
// ⚠️ Prontidão é pré-condição de PUBLICAR, não de configurar: salvar a campanha
// continua livre. O que a tela promete é "não vai publicar ali até resolver".
import type { Platform } from "~/composables/usePlatforms";

export type PlatformReadiness = Pick<
  Platform,
  | "platform"
  | "state"
  | "ready"
  | "reason"
  | "limitation"
  | "source_status"
  | "canary_recipients"
>;

export type ReadinessTone = "ready" | "limited" | "blocked" | "unknown";

export interface PlatformReadinessNote {
  tone: ReadinessTone;
  /** Palavra curta para a pílula: "não publica", "não verificada", "limitada". */
  badge: string;
  /** Frase completa para baixo da escolha. Vazia quando pronta. */
  text: string;
}

export function readinessByPlatform(
  readiness: PlatformReadiness[] | undefined,
): Record<string, PlatformReadiness> {
  return Object.fromEntries(
    (readiness ?? []).map((item) => [item.platform, item]),
  );
}

export function readinessTone(item: PlatformReadiness | undefined): ReadinessTone {
  if (!item) return "ready";
  if (item.state === "blocked") return "blocked";
  if (item.state === "unknown") return "unknown";
  if (item.state === "degraded" || !item.ready) return "limited";
  return "ready";
}

/**
 * A nota de uma plataforma, com o nome que o gestor vê ("Instagram") e o que
 * acontece se ele escolher: ausente do inventário = pronta (nada a dizer).
 */
export function platformReadinessNote(
  item: PlatformReadiness | undefined,
  label: string,
): PlatformReadinessNote {
  const tone = readinessTone(item);
  if (tone === "ready" || !item) return { tone: "ready", badge: "", text: "" };
  if (tone === "limited" && typeof item.canary_recipients === "number") {
    return {
      tone: "limited",
      badge: "ensaio",
      text: `${label}: ${canaryText(item.canary_recipients)}`,
    };
  }
  if (item.source_status === "simulated") {
    return {
      tone: "limited",
      badge: "simulação",
      text: `${label}: ${item.reason || "simulação local ativa"}`,
    };
  }
  if (tone === "blocked") {
    return {
      tone,
      badge: "não publica",
      text: `${label}: ${item.reason || "a plataforma não está pronta."} Não vai publicar por aqui até resolver.`,
    };
  }
  if (tone === "unknown") {
    return {
      tone,
      badge: "não verificada",
      text: `${label}: ${item.reason || "não foi possível verificar a plataforma."} Não vai publicar por aqui até a verificação passar.`,
    };
  }
  return {
    tone: "limited",
    badge: "limitada",
    text: `${label}: ${item.limitation || item.reason || "publica com limite."}`,
  };
}

/**
 * Ensaio do WhatsApp: a mensagem sai, mas só para os contatos escolhidos. Diz QUANTOS,
 * nunca quais — o ref de cliente não vem para a tela.
 */
export function canaryText(recipients: number): string {
  const n = Math.max(0, Math.trunc(recipients));
  return n === 1
    ? "Ensaio: só 1 contato recebe."
    : `Ensaio: só ${n} contatos recebem.`;
}

/** Classes da pílula por tom — a cor conta o estado antes de qualquer clique. */
export function readinessPillClass(tone: ReadinessTone): string {
  if (tone === "blocked") return "border-destructive/60 text-destructive";
  if (tone === "unknown")
    return "border-slate-400/60 text-slate-700 dark:text-slate-300";
  if (tone === "limited") return "border-warning/60 text-warning";
  return "";
}
