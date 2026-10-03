import { mount, RouterLinkStub } from "@vue/test-utils";
import { computed, ref } from "vue";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import MarketingDecisionQueue from "~/components/MarketingDecisionQueue.vue";
import type { DecisionItem, DecisionQueue } from "~/types/decisions";

const NOW = Date.parse("2026-10-03T10:03:00-03:00");
const queue = ref<DecisionQueue | null>(null);
const error = ref<unknown>(null);
const refresh = vi.fn();

function item(over: Partial<DecisionItem>): DecisionItem {
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

beforeAll(() => {
  Object.assign(globalThis, {
    computed,
    useMarketingDecisions: () => ({
      queue,
      items: computed(() => queue.value?.items ?? []),
      automaticChecks: computed(() => queue.value?.automatic_checks ?? []),
      shopTimezone: ref("America/Sao_Paulo"),
      nowMs: ref(NOW),
      loading: ref(false),
      error,
      refresh,
    }),
  });
});

beforeEach(() => {
  error.value = null;
  refresh.mockReset();
  queue.value = {
    generated_at: "2026-10-03T10:03:00-03:00",
    shop_timezone: "America/Sao_Paulo",
    items: [
      item({}),
      item({
        ref: "retry_failed:announcement:9",
        kind: "retry_failed",
        announcement_id: 9,
        product_name: "Pain au chocolat",
        platform_refs: ["instagram"],
        reach: { posts: 1, people: 0 },
        deadline_at: "2026-10-03T11:40:00-03:00",
        failures: [
          {
            platform_ref: "instagram",
            delivery_kind: "publication",
            count: 1,
            reason_code: "instagram_prepare_transport_failure",
          },
        ],
        href: "/announcements/9#result",
      }),
    ],
    automatic_checks: [
      {
        ref: "check:announcement:7:google_business",
        announcement_id: 7,
        campaign_name: "Pão de queijo",
        platform_ref: "google_business",
        delivery_kind: "publication",
        state: "confirmed",
        target_count: 1,
        checked_at: "2026-10-03T09:58:00-03:00",
        href: "/announcements/7#result",
      },
    ],
    scheduled: [],
    scheduled_today_count: 2,
    active_campaign_count: 3,
  };
});

function render() {
  return mount(MarketingDecisionQueue, {
    global: {
      stubs: {
        Icon: true,
        NuxtLink: RouterLinkStub,
        UiIconButton: true,
        UiButton: {
          props: ["to", "variant"],
          template:
            '<a :href="to" :data-variant="variant" v-bind="$attrs"><slot /></a>',
        },
      },
    },
  });
}

describe("MarketingDecisionQueue", () => {
  it("lista cada decisão por prazo, com o mais urgente em destaque", () => {
    const wrapper = render();
    const cards = wrapper.findAll("[data-decision]");

    expect(cards.map((card) => card.attributes("data-decision-kind"))).toEqual([
      "review",
      "retry_failed",
    ]);
    expect(wrapper.text()).toContain("2 pedem você");
    expect(cards[0]!.text()).toContain("Lote pronto: Croissant");
    expect(cards[0]!.text()).toContain("Instagram, Facebook e WhatsApp (86 pessoas)");
    expect(cards[0]!.text()).toContain("Decide até 10:15");
    expect(cards[0]!.text()).toContain("faltam 12 min");
    expect(cards[0]!.classes()).toContain("border-primary/70");
    expect(cards[1]!.classes()).not.toContain("border-primary/70");
  });

  it("tem um gesto só por cartão, que abre o lugar onde a decisão já é tomada", () => {
    const wrapper = render();
    const reviews = wrapper.findAll("[data-decision-review]");

    expect(reviews.map((link) => link.attributes("href"))).toEqual([
      "/announcements/12#review",
      "/announcements/9#result",
    ]);
    expect(reviews.map((link) => link.text())).toEqual(["Revisar", "Revisar"]);
    expect(reviews[0]!.attributes("data-variant")).toBe("default");
    expect(reviews[1]!.attributes("data-variant")).toBe("outline");
  });

  it("escreve o motivo da falha no cartão", () => {
    const failure = render().findAll("[data-decision]")[1]!;

    expect(failure.text()).toContain("Falhou no Instagram · 1 postagem");
    expect(failure.text()).toContain("A conexão com a plataforma caiu antes do envio.");
    expect(failure.text()).toContain("Repetir até 11:40");
  });

  it("mostra o incerto conferido sozinho e a linha de agendados", () => {
    const wrapper = render();

    expect(wrapper.get("[data-automatic-check]").text()).toContain(
      "O sistema consultou sem reenviar: publicado às 09:58 · automático",
    );
    const line = wrapper.get("[data-decisions-scheduled-line]");
    expect(line.text()).toContain("+2 agendados hoje · 3 campanhas ligadas");
    expect(line.getComponent(RouterLinkStub).props("to")).toBe("/scheduled");
  });

  it("não confunde fila vazia com fila que não carregou", () => {
    queue.value = null;
    error.value = new Error("offline");
    const failed = render();
    expect(failed.get("[role='alert']").text()).toContain(
      "Isso não quer dizer que nada pede você.",
    );
  });
});
