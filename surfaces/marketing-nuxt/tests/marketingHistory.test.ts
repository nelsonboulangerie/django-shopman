import { describe, expect, it } from "vitest";
import {
  HISTORY_FILTERS,
  HISTORY_FILTER_ALL,
  historyActiveFilters,
  historyFilterQueryValue,
  historyFilterValue,
  historyActorLabel,
  historyAnnouncementId,
  historyHref,
  historyLinkLabel,
  historyOccurredAt,
  historySubject,
} from "~/presentation/marketingHistory";
import type {
  AnnouncementProjectionV2,
  MarketingActionProjectionV2,
} from "~/types/campaign";

function announcement(
  over: Partial<AnnouncementProjectionV2> = {},
): AnnouncementProjectionV2 {
  return {
    ref: "announcement:42",
    decision_actor_policy: "operator",
    facts: {
      trigger: "production_finished",
      product_ref: "product:PAO-01",
    },
    created_at: "2026-09-08T09:00:00-03:00",
    approved_at: "2026-09-08T09:05:00-03:00",
    rejected_at: null,
    published_at: "2026-09-08T09:06:00-03:00",
    settled_at: "2026-09-08T09:07:00-03:00",
    ...over,
  } as AnnouncementProjectionV2;
}

function action(
  kind: MarketingActionProjectionV2["kind"],
  enabled = true,
): MarketingActionProjectionV2 {
  return {
    kind,
    enabled,
    resource_ref: "announcement:42",
  } as MarketingActionProjectionV2;
}

describe("apresentação do histórico canônico", () => {
  it("names the operational subject without exposing body or PII", () => {
    expect(historySubject(announcement())).toBe(
      "Produção concluída · Produto PAO-01",
    );
    // ⚠️ O gestor fala "Pão francês", não "PAO-01". O rótulo vem de
    // `options.products`; sem ele, o SKU segue, anunciado como "Produto".
    expect(historySubject(announcement(), { "PAO-01": "Pão francês" })).toBe(
      "Produção concluída · Pão francês",
    );
    expect(historySubject(announcement(), { "OUTRO-01": "Outro" })).toBe(
      "Produção concluída · Produto PAO-01",
    );
    expect(historyActorLabel("operator")).toBe("Decisão de uma pessoa");
    expect(historyActorLabel("automation")).toBe("Disparo automático");
  });

  it("uses the latest meaningful immutable result timestamp", () => {
    expect(historyOccurredAt(announcement())).toBe("2026-09-08T09:07:00-03:00");
    expect(
      historyOccurredAt(
        announcement({
          settled_at: null,
          published_at: null,
          rejected_at: "2026-09-08T09:08:00-03:00",
        }),
      ),
    ).toBe("2026-09-08T09:08:00-03:00");
  });

  it("offers resolution copy only for an enabled contextual recovery", () => {
    expect(historyLinkLabel([], "announcement:42")).toBe("Ver resultado");
    expect(
      historyLinkLabel(
        [action("retry_failed_delivery", false)],
        "announcement:42",
      ),
    ).toBe("Ver resultado");
    expect(
      historyLinkLabel(
        [action("reconcile_unknown_delivery")],
        "announcement:42",
      ),
    ).toBe("Abrir e resolver");
  });

  it("only turns a canonical positive announcement ref into a detail route", () => {
    expect(historyAnnouncementId("announcement:42")).toBe(42);
    expect(historyAnnouncementId("campaign:42")).toBeNull();
    expect(historyHref("announcement:42")).toBe("/announcements/42");
    expect(historyHref("announcement:0")).toBe("/history");
  });
});

describe("recortes de Enviados", () => {
  it("são os quatro de hoje, cada um com um 'sem recorte' que o Select aceita", () => {
    expect(HISTORY_FILTERS.map((filter) => filter.label)).toEqual([
      "Situação",
      "Plataforma",
      "Criado em",
      "Origem da decisão",
    ]);
    for (const filter of HISTORY_FILTERS) {
      // O Select do Nuxt UI (Reka) recusa item de valor vazio.
      expect(filter.options.every((option) => option.value !== "")).toBe(true);
      expect(filter.options[0]!.value).toBe(HISTORY_FILTER_ALL);
    }
    expect(
      HISTORY_FILTERS.find((filter) => filter.name === "period")!.options.map(
        (option) => option.value,
      ),
    ).toEqual(["all", "today", "7d", "30d"]);
  });

  it("vai e volta da URL sem mudar o contrato do backend", () => {
    expect(historyFilterValue("")).toBe("all");
    expect(historyFilterValue(undefined)).toBe("all");
    expect(historyFilterValue("7d")).toBe("7d");
    expect(historyFilterQueryValue("all")).toBe("");
    expect(historyFilterQueryValue("instagram")).toBe("instagram");
  });

  it("vira um chip por recorte fora do padrão, com o nome do recorte", () => {
    expect(historyActiveFilters({ period: "all" })).toEqual([]);
    expect(
      historyActiveFilters({
        outcome: "",
        platform: "instagram",
        period: "7d",
        actor: "automation",
      }),
    ).toEqual([
      { name: "platform", label: "Plataforma: Instagram" },
      { name: "period", label: "Criado em: Últimos 7 dias" },
      { name: "actor", label: "Origem da decisão: Automação" },
    ]);
    expect(historyActiveFilters({ outcome: "desconhecido" })).toEqual([]);
  });
});
