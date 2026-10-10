import { describe, expect, it } from "vitest";
import {
  automaticCheckLine,
  deadlinePresentation,
  decisionTitle,
  departureVerb,
  destinationsLine,
  failureHeadline,
  failureReason,
  queueHeadline,
  reachLine,
  scheduledSummary,
} from "~/presentation/decisions";
import type { AutomaticCheck, DecisionItem } from "~/types/decisions";

const TZ = "America/Sao_Paulo";
// 03/10/2026 10:03 em São Paulo.
const NOW = Date.parse("2026-10-03T10:03:00-03:00");

function item(over: Partial<DecisionItem> = {}): DecisionItem {
  return {
    ref: "review:announcement:12",
    kind: "review",
    announcement_id: 12,
    announcement_version: 3,
    campaign_name: "Fornada de pães",
    trigger: "production_finished",
    product_name: "Croissant",
    platform_refs: ["instagram", "facebook", "whatsapp"],
    reach: { posts: 2, people: 86 },
    deadline_at: "2026-10-03T10:15:00-03:00",
    scheduled_for: null,
    created_at: "2026-10-03T10:01:00-03:00",
    failures: [],
    href: "/announcements/12#review",
    ...over,
  };
}

function check(over: Partial<AutomaticCheck> = {}): AutomaticCheck {
  return {
    ref: "check:announcement:9:google_business",
    announcement_id: 9,
    campaign_name: "Pão de queijo",
    platform_ref: "google_business",
    delivery_kind: "publication",
    state: "confirmed",
    target_count: 1,
    checked_at: "2026-10-03T09:58:00-03:00",
    href: "/announcements/9#result",
    ...over,
  };
}

describe("fila de decisões: o cartão", () => {
  it("diz a ocasião e o produto no título", () => {
    expect(decisionTitle(item())).toBe("Lote pronto: Croissant");
    expect(decisionTitle(item({ product_name: "" }))).toBe("Fornada de pães");
    expect(decisionTitle(item({ product_name: "", campaign_name: "" }))).toBe(
      "Lote pronto",
    );
  });

  it("separa postagens de pessoas e nunca soma as duas", () => {
    expect(destinationsLine(item().platform_refs, item().reach)).toBe(
      "Instagram, Facebook e WhatsApp (86 clientes)",
    );
    expect(destinationsLine(["instagram"], { posts: 1, people: 0 })).toBe(
      "Instagram",
    );
    expect(reachLine({ posts: 2, people: 86 })).toBe("2 postagens · 86 pessoas");
    expect(reachLine({ posts: 1, people: 1 })).toBe("1 postagem · 1 pessoa");
    expect(reachLine({ posts: 2, people: 86 })).not.toContain("88");
  });

  it("mostra o prazo com hora e quanto falta, no fuso da loja", () => {
    const shown = deadlinePresentation(item(), TZ, NOW);
    expect(shown).toEqual({
      label: "Decide até 10:15",
      detail: "faltam 12 min",
      tone: "urgent",
    });
    expect(
      deadlinePresentation(
        item({ deadline_at: "2026-10-03T10:50:00-03:00" }),
        TZ,
        NOW,
      ).tone,
    ).toBe("soon");
    expect(
      deadlinePresentation(item({ deadline_at: null }), TZ, NOW).label,
    ).toBe("Sem prazo para decidir");
  });

  it("diz quando dispara o anúncio de hora marcada com o verbo da grandeza", () => {
    const scheduled = item({
      scheduled_for: "2026-10-03T17:30:00-03:00",
      deadline_at: "2026-10-03T17:00:00-03:00",
      platform_refs: ["whatsapp"],
      reach: { posts: 0, people: 142 },
    });
    expect(deadlinePresentation(scheduled, TZ, NOW)).toMatchObject({
      label: "Envia hoje às 17:30",
      detail: "decide até 17:00",
    });
    expect(departureVerb(["instagram"])).toBe("Publica");
    expect(departureVerb(["whatsapp"])).toBe("Envia");
    expect(departureVerb(["instagram", "whatsapp"])).toBe("Dispara");
  });

  it("escreve a falha com onde, quanto e o motivo", () => {
    const failed = item({
      kind: "retry_failed",
      reach: { posts: 1, people: 0 },
      failures: [
        {
          platform_ref: "instagram",
          delivery_kind: "publication",
          count: 1,
          reason_code: "instagram_prepare_transport_failure",
        },
      ],
      deadline_at: "2026-10-03T11:40:00-03:00",
    });
    expect(failureHeadline(failed)).toBe("Falhou no Instagram · 1 envio");
    expect(failureReason(failed.failures[0]!, "retry_failed")).toBe(
      "A conexão com a plataforma caiu antes do envio. Nada foi disparado.",
    );
    expect(deadlinePresentation(failed, TZ, NOW).label).toBe(
      "Repetir até 11:40",
    );
    expect(
      failureReason(
        { ...failed.failures[0]!, reason_code: "codigo_que_ninguem_conhece" },
        "retry_failed",
      ),
    ).toContain("repetir só para quem não recebeu");
  });

  it("o incerto que pede pessoa diz que consultar de novo não reenvia", () => {
    const uncertain = item({
      kind: "reconcile_unknown",
      reach: { posts: 0, people: 3 },
      failures: [
        {
          platform_ref: "whatsapp",
          delivery_kind: "direct_message",
          count: 3,
          reason_code: "",
        },
      ],
      deadline_at: null,
    });
    expect(failureHeadline(uncertain)).toBe(
      "Resultado incerto no WhatsApp · 3 envios",
    );
    expect(failureReason(uncertain.failures[0]!, "reconcile_unknown")).toContain(
      "não reenvia",
    );
  });
});

describe("fila de decisões: a casa", () => {
  it("diz quantas decisões e em que ordem", () => {
    expect(queueHeadline(3)).toEqual({
      strong: "3 pedem você",
      rest: "o prazo mais curto primeiro",
    });
    expect(queueHeadline(1)).toEqual({ strong: "1 pede você", rest: "" });
    expect(queueHeadline(0).strong).toBe("Nada pede você agora");
  });

  it("resume agendados e campanhas numa linha só", () => {
    expect(scheduledSummary(2, 3)).toBe("+2 agendados hoje · 3 campanhas ligadas");
    expect(scheduledSummary(1, 1)).toBe("+1 agendado hoje · 1 campanha ligada");
    expect(scheduledSummary(0, 0)).toBe(
      "Nenhum agendado hoje · nenhuma campanha ligada",
    );
  });

  it("mostra o incerto como consultado sem reenviar, automático", () => {
    expect(automaticCheckLine(check(), TZ, NOW)).toEqual({
      title: "Google: resultado incerto.",
      detail:
        "O sistema consultou sem reenviar: publicado às 09:58 · automático",
    });
    expect(
      automaticCheckLine(
        check({ checked_at: "2026-10-02T18:10:00-03:00" }),
        TZ,
        NOW,
      ).detail,
    ).toBe(
      "O sistema consultou sem reenviar: publicado ontem às 18:10 · automático",
    );
    expect(
      automaticCheckLine(check({ state: "checking", checked_at: null }), TZ, NOW)
        .detail,
    ).toBe("O sistema está consultando sem reenviar · automático");
    const message = check({
      platform_ref: "whatsapp",
      delivery_kind: "direct_message",
      state: "failed",
      target_count: 3,
    });
    expect(automaticCheckLine(message, TZ, NOW).detail).toBe(
      "O sistema consultou sem reenviar: não foi entregue (3 pessoas) · automático",
    );
  });
});
