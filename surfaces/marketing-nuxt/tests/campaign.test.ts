import { describe, expect, it } from "vitest";
import {
  audienceRulesSummary,
  audienceSummary,
  displayHashtag,
  expiryLabel,
  expiryTone,
  isStillReviewable,
  parseHashtags,
  platformsSummary,
  announcementOutcome,
  approvalBody,
  approvalMessage,
  mergeAudienceRules,
  resultLabel,
  resultTone,
  shortDateTime,
  vipSummary,
} from "~/presentation/campaign";
import type { Announcement, PlatformResult } from "~/types/campaign";

function result(platform: string, status: string): PlatformResult {
  return { platform, label: platform, status, detail: "", url: "" };
}

describe("audienceSummary", () => {
  it("lists each source and closes with the deduplicated total", () => {
    expect(audienceSummary({ favorites_count: 12, bought_count: 28, alerts_count: 3, total: 43 }))
      .toBe("12 favoritos, 28 recompra, 3 alertas = 43 clientes");
  });

  it("uses the backend total instead of summing the parts", () => {
    // Quem favoritou E recompra é uma pessoa só: somar (12+28) mentiria pra cima.
    expect(audienceSummary({ favorites_count: 12, bought_count: 28, total: 30 }))
      .toBe("12 favoritos, 28 recompra = 30 clientes");
  });

  it("omits sources that resolved to nobody", () => {
    expect(audienceSummary({ favorites_count: 5, alerts_count: 0, total: 5 }))
      .toBe("5 favoritos = 5 clientes");
  });

  it("says nobody rather than showing a zero", () => {
    expect(audienceSummary({ total: 0 })).toBe("Ninguém para avisar por enquanto");
    expect(audienceSummary(undefined)).toBe("Ninguém para avisar por enquanto");
  });

  it("agrees in the singular", () => {
    expect(audienceSummary({ alerts_count: 1, total: 1 })).toBe("1 alertas = 1 cliente");
  });

  it("falls back to the bare total when no source is broken out", () => {
    expect(audienceSummary({ total: 7 })).toBe("7 clientes");
  });
});

describe("vipSummary", () => {
  it("states the head start", () => {
    expect(vipSummary({ vip_count: 4, vip_delay_minutes: 15 })).toBe("4 VIPs recebem 15 min antes");
  });

  it("stays silent when there is no head start to talk about", () => {
    expect(vipSummary({ vip_count: 4, vip_delay_minutes: 0 })).toBe("");
    expect(vipSummary({ vip_count: 0, vip_delay_minutes: 15 })).toBe("");
    expect(vipSummary(undefined)).toBe("");
  });
});

describe("expiryLabel", () => {
  it("reads in minutes under an hour and in hours above it", () => {
    expect(expiryLabel(12)).toBe("Expira em 12 min");
    expect(expiryLabel(59)).toBe("Expira em 59 min");
    expect(expiryLabel(90)).toBe("Expira em 1 h");
  });

  it("says the deadline passed instead of showing zero", () => {
    expect(expiryLabel(0)).toBe("Expirou");
  });

  it("stays silent for announcements with no deadline", () => {
    expect(expiryLabel(-1)).toBe("");
  });
});

describe("expiryTone", () => {
  it("escalates as the window closes", () => {
    expect(expiryTone(5)).toBe("urgent");
    expect(expiryTone(25)).toBe("warning");
    expect(expiryTone(120)).toBe("calm");
  });

  it("does not shout when there is no deadline", () => {
    expect(expiryTone(-1)).toBe("none");
  });
});

describe("announcementOutcome", () => {
  it("only calls it published when every platform published", () => {
    expect(announcementOutcome([result("instagram", "published"), result("facebook", "published")]))
      .toBe("published");
  });

  it("treats a mixed result as partial, not as success", () => {
    expect(announcementOutcome([result("instagram", "failed"), result("facebook", "published")]))
      .toBe("partial");
  });

  it("reports a total failure as failed", () => {
    expect(announcementOutcome([result("instagram", "failed")])).toBe("failed");
  });

  it("counts a WhatsApp-only wave as published once it was sent", () => {
    expect(announcementOutcome([result("whatsapp", "sent")])).toBe("published");
  });

  it("counts a still-queued platform as pending", () => {
    expect(announcementOutcome([result("instagram", "queued"), result("facebook", "pending_manual")]))
      .toBe("pending");
  });

  it("treats a announcement with no targeted platform as pending", () => {
    expect(announcementOutcome([])).toBe("pending");
  });
});

describe("resultTone", () => {
  it("maps a manual pending to pending, never to failure", () => {
    // Sem credencial, o announcement fica pending_manual DE PROPÓSITO — não é erro.
    expect(resultTone("pending_manual")).toBe("pending");
    expect(resultTone("published")).toBe("ok");
    expect(resultTone("failed")).toBe("fail");
  });

  it("treats the WhatsApp `sent` as a success, not as an unknown", () => {
    // O handler grava `sent` para a onda de WhatsApp; ler isso como pendente
    // deixaria um announcement inteiramente entregue parecendo travado.
    expect(resultTone("sent")).toBe("ok");
    expect(resultLabel("sent")).toBe("enviado");
  });

  it("shows an unmapped status verbatim instead of swallowing it", () => {
    expect(resultLabel("mystery")).toBe("mystery");
  });
});

describe("hashtags", () => {
  it("reads with a single # no matter how it was stored", () => {
    expect(displayHashtag("padaria")).toBe("#padaria");
    expect(displayHashtag("##padaria")).toBe("#padaria");
    expect(displayHashtag("  ")).toBe("");
  });

  it("parses whatever the gestor pasted", () => {
    expect(parseHashtags("#padaria #fornada")).toEqual(["padaria", "fornada"]);
    expect(parseHashtags("padaria, fornada")).toEqual(["padaria", "fornada"]);
    expect(parseHashtags("  #padaria \n fornada  ")).toEqual(["padaria", "fornada"]);
    expect(parseHashtags("")).toEqual([]);
  });
});

describe("audienceRulesSummary", () => {
  const labels = {
    priceTiers: { atacado: "Atacado" },
    segments: { loyal_customer: "Cliente fiel" },
  };

  it("spells out the sources in order", () => {
    expect(audienceRulesSummary({ favorites: true, alerts: true, bought_within_days: 90 }))
      .toBe("Favoritos, alertas, recompra em 90 dias");
  });

  it("appends the VIP head start", () => {
    expect(audienceRulesSummary({ favorites: true, vip_first_minutes: 15 }))
      .toBe("Favoritos, melhores clientes 15 min antes");
  });

  // ⚠️ O resumo conhecia só três das nove regras. Uma campanha para "cliente fiel" ou
  // para o grupo atacado — configurada, funcionando, alcançando gente — aparecia na lista
  // como "sem audiência". Mentia sobre a decisão mais importante da campanha.
  it("spells out the audiences the manager chooses, not only the event ones", () => {
    expect(audienceRulesSummary({ price_tiers: ["atacado"] }, labels)).toBe("Atacado");
    expect(audienceRulesSummary({ rfm_segments: ["loyal_customer"] }, labels))
      .toBe("Cliente fiel");
    expect(audienceRulesSummary({ churn_risk_min: 0.7 })).toBe("Quem está sumindo");
    expect(audienceRulesSummary({ birthday_today: true })).toBe("Aniversariantes de hoje");
  });

  // Somar e cruzar as MESMAS regras alcançam gente diferente, então o resumo não pode
  // desenhar as duas coisas igual.
  it("says when the rules are crossed instead of added", () => {
    const rules = { price_tiers: ["atacado"], rfm_segments: ["loyal_customer"] };
    expect(audienceRulesSummary(rules, labels)).toBe("Atacado, Cliente fiel");
    expect(audienceRulesSummary({ ...rules, match: "all" as const }, labels))
      .toBe("Cruzando Atacado, Cliente fiel");
  });

  it("does not say 'crossed' with a single rule, where it would mean nothing", () => {
    expect(audienceRulesSummary({ price_tiers: ["atacado"], match: "all" }, labels))
      .toBe("Atacado");
  });

  // Rótulo tem dono no servidor (`CustomerGroup.name`, `RFM_SEGMENTS`). Sem mapa, o ref
  // cru é honesto; inventar tradução aqui é o que cria o segundo dono.
  it("falls back to the raw ref instead of inventing a label", () => {
    expect(audienceRulesSummary({ price_tiers: ["atacado"] })).toBe("atacado");
  });

  it("is explicit when the rule notifies nobody directly", () => {
    expect(audienceRulesSummary({})).toBe("Sem público definido");
    expect(audienceRulesSummary(undefined)).toBe("Sem público definido");
  });
});

describe("platformsSummary", () => {
  const labels = { instagram: "Instagram", google_business: "Google Meu Negócio" };

  it("uses the labels and keeps the chosen order", () => {
    expect(platformsSummary(["google_business", "instagram"], labels))
      .toBe("Google Meu Negócio, Instagram");
  });

  it("falls back to the ref when a label is unknown", () => {
    expect(platformsSummary(["mastodon"], labels)).toBe("mastodon");
  });

  it("says none instead of rendering an empty string", () => {
    expect(platformsSummary([], labels)).toBe("Nenhuma plataforma");
  });
});

describe("shortDateTime", () => {
  it("returns empty for a missing or unparseable date, never Invalid Date", () => {
    expect(shortDateTime("")).toBe("");
    expect(shortDateTime("amanhã")).toBe("");
  });

  it("formats a real ISO timestamp", () => {
    expect(shortDateTime("2026-07-18T07:30:00-03:00")).toMatch(/\d{2}\/\d{2}/);
  });
});

describe("isStillReviewable", () => {
  const announcement = (over: Partial<Announcement>) =>
    ({ status: "pending_review", expires_in_minutes: 30, ...over }) as Announcement;

  it("accepts a pending announcement inside its window", () => {
    expect(isStillReviewable(announcement({}))).toBe(true);
  });

  it("accepts a pending announcement with no deadline", () => {
    expect(isStillReviewable(announcement({ expires_in_minutes: -1 }))).toBe(true);
  });

  it("refuses one whose deadline already passed", () => {
    // O sweeper roda em ciclos de minutos: a tela não pode oferecer "Publicar"
    // num card que venceu entre um fetch e outro.
    expect(isStillReviewable(announcement({ expires_in_minutes: 0 }))).toBe(false);
  });

  it("refuses one that was already decided", () => {
    expect(isStillReviewable(announcement({ status: "published" }))).toBe(false);
  });
});

describe("approvalMessage", () => {
  it("says scheduled when the SERVER scheduled", () => {
    // ⚠️ O toast dizia "publicado" sempre. Uma campanha com janela de horas preferidas
    // faz o servidor AGENDAR, e o gestor fechava a tela achando que já estava no ar.
    expect(approvalMessage({ scheduled: true })).toBe("Anúncio agendado.");
  });

  it("says published when the server dispatched", () => {
    expect(approvalMessage({ scheduled: false })).toBe("Anúncio publicado.");
  });

  it("does not invent a schedule when the server said nothing", () => {
    expect(approvalMessage({})).toBe("Anúncio publicado.");
    expect(approvalMessage(null)).toBe("Anúncio publicado.");
    expect(approvalMessage(undefined)).toBe("Anúncio publicado.");
  });
});

describe("approvalBody", () => {
  it("asks to publish NOW when no date was set", () => {
    // ⚠️ Sem isto, "Publicar" não publicava: o anúncio nascia com data na próxima
    // janela da campanha, a aprovação respeitava a agenda e nada era despachado.
    expect(approvalBody({})).toEqual({ publish_now: true });
    expect(approvalBody({ publish_at: "" })).toEqual({
      publish_at: "",
      publish_now: true,
    });
  });

  it("respects a date the manager actually set", () => {
    expect(approvalBody({ publish_at: "2026-09-01T07:00" })).toEqual({
      publish_at: "2026-09-01T07:00",
    });
  });

  it("carries the rest of the edits through untouched", () => {
    expect(approvalBody({ body: "Saiu do forno", publish_at: "" })).toEqual({
      body: "Saiu do forno",
      publish_at: "",
      publish_now: true,
    });
  });
});

describe("mergeAudienceRules", () => {
  it("keeps the keys the form does not own", () => {
    // ⚠️ O gestor abria "Editar" numa campanha configurada no Admin, mudava só o nome
    // e salvava: o PATCH sobrescreve o JSON inteiro e dez chaves sumiam.
    const original = {
      favorites: false,
      match: "all",
      tags: ["vip", "padaria"],
      rfm_segment: "champions",
      min_orders: 3,
    };
    const resultado = mergeAudienceRules(original, { favorites: true, alerts: false });

    expect(resultado.match).toBe("all");
    expect(resultado.tags).toEqual(["vip", "padaria"]);
    expect(resultado.rfm_segment).toBe("champions");
    expect(resultado.min_orders).toBe(3);
  });

  it("lets the form win on the keys it owns", () => {
    const resultado = mergeAudienceRules({ favorites: false }, { favorites: true, alerts: true });
    expect(resultado.favorites).toBe(true);
    expect(resultado.alerts).toBe(true);
  });

  it("removes an owned key the form turned off", () => {
    // "0 dias" e ausência dizem a mesma coisa ao serviço, mas ausência é o que o
    // resto do código espera ver — e preservar o valor antigo seria não desligar.
    const resultado = mergeAudienceRules(
      { favorites: true, bought_within_days: 30, vip_first_minutes: 15 },
      { favorites: true, alerts: false },
    );
    expect("bought_within_days" in resultado).toBe(false);
    expect("vip_first_minutes" in resultado).toBe(false);
  });

  it("works on a campaign that had no rules yet", () => {
    expect(mergeAudienceRules(null, { favorites: true, alerts: false })).toEqual({
      favorites: true,
      alerts: false,
    });
    expect(mergeAudienceRules(undefined, { favorites: false, alerts: true })).toEqual({
      favorites: false,
      alerts: true,
    });
  });
});
