import { describe, expect, it } from "vitest";
import {
  canaryText,
  platformReadinessNote,
  readinessByPlatform,
  readinessPillClass,
  readinessTone,
} from "~/presentation/platformReadiness";
import type { PlatformReadiness } from "~/presentation/platformReadiness";

function platform(over: Partial<PlatformReadiness> = {}): PlatformReadiness {
  return {
    platform: "instagram",
    state: "ready",
    ready: true,
    reason: "",
    limitation: "",
    source_status: "live",
    ...over,
  };
}

describe("prontidão de plataforma antes do clique", () => {
  it("plataforma fora do inventário conta como pronta — nada a dizer", () => {
    expect(readinessTone(undefined)).toBe("ready");
    expect(platformReadinessNote(undefined, "Instagram")).toEqual({
      tone: "ready",
      badge: "",
      text: "",
    });
    expect(readinessPillClass("ready")).toBe("");
  });

  it("bloqueada: motivo do servidor + a promessa de que não publica até resolver", () => {
    const note = platformReadinessNote(
      platform({
        state: "blocked",
        ready: false,
        reason: "A integração existe, mas está sem credencial neste ambiente.",
      }),
      "Instagram",
    );

    expect(note.tone).toBe("blocked");
    expect(note.badge).toBe("não publica");
    expect(note.text).toBe(
      "Instagram: A integração existe, mas está sem credencial neste ambiente. Não vai publicar por aqui até resolver.",
    );
    expect(readinessPillClass("blocked")).toContain("destructive");
  });

  it("desligada pela flag: diz desligada, sem prometer conserto de algo quebrado", () => {
    const note = platformReadinessNote(
      platform({
        state: "blocked",
        ready: false,
        reason_code: "platform_switched_off",
        reason: "A publicação nesta plataforma está desligada neste ambiente.",
      }),
      "Instagram",
    );

    expect(note.tone).toBe("blocked");
    expect(note.badge).toBe("desligada");
    expect(note.text).toBe(
      "Instagram: A publicação nesta plataforma está desligada neste ambiente. O que for aprovado para ela fica na fila, sem envio, até ela ser ligada.",
    );
    expect(note.text).not.toMatch(/resolver|integração|credencial|adapt/i);
  });

  it("não verificada: diz que a verificação precisa passar", () => {
    const note = platformReadinessNote(
      platform({
        platform: "whatsapp",
        state: "unknown",
        ready: false,
        reason: "Não foi possível verificar o transporte do WhatsApp agora.",
      }),
      "WhatsApp",
    );

    expect(note.badge).toBe("não verificada");
    expect(note.text).toContain("Não vai publicar por aqui até a verificação passar.");
  });

  it("limitada ainda publica: mostra a limitação, sem prometer bloqueio", () => {
    const note = platformReadinessNote(
      platform({
        state: "degraded",
        ready: true,
        limitation: "Sem imagem pública, o Story não sai.",
      }),
      "Instagram",
    );

    expect(note.tone).toBe("limited");
    expect(note.badge).toBe("limitada");
    expect(note.text).toBe("Instagram: Sem imagem pública, o Story não sai.");
    expect(note.text).not.toContain("Não vai publicar");
  });

  it("ensaio do WhatsApp diz QUANTOS recebem, nunca quem", () => {
    const note = platformReadinessNote(
      platform({
        platform: "whatsapp",
        state: "degraded",
        ready: true,
        limitation: "Ensaio: só 2 contatos recebem. O restante do público não recebe por WhatsApp.",
        canary_recipients: 2,
      }),
      "WhatsApp",
    );

    expect(note.tone).toBe("limited");
    expect(note.badge).toBe("ensaio");
    expect(note.text).toBe("WhatsApp: Ensaio: só 2 contatos recebem.");
    expect(note.text).not.toContain("Não vai publicar");
  });

  it("ensaio com um contato fala no singular", () => {
    expect(canaryText(1)).toBe("Ensaio: só 1 contato recebe.");
    expect(canaryText(3)).toBe("Ensaio: só 3 contatos recebem.");
  });

  it("bloqueio vence a contagem do ensaio", () => {
    const note = platformReadinessNote(
      platform({
        platform: "whatsapp",
        state: "blocked",
        ready: false,
        reason: "O ensaio do WhatsApp está ligado sem nenhum contato escolhido.",
        canary_recipients: 0,
      }),
      "WhatsApp",
    );

    expect(note.badge).toBe("não publica");
  });

  it("simulação local é dita como simulação, não como defeito", () => {
    const note = platformReadinessNote(
      platform({
        state: "degraded",
        source_status: "simulated",
        reason: "Simulação local ativa; nenhum conteúdo sai deste computador.",
      }),
      "Facebook",
    );

    expect(note.badge).toBe("simulação");
    expect(note.text).toContain("nenhum conteúdo sai deste computador");
  });

  it("indexa por ref de plataforma", () => {
    const map = readinessByPlatform([
      platform(),
      platform({ platform: "whatsapp", state: "blocked", ready: false }),
    ]);
    expect(Object.keys(map)).toEqual(["instagram", "whatsapp"]);
    expect(map.whatsapp!.state).toBe("blocked");
  });
});
