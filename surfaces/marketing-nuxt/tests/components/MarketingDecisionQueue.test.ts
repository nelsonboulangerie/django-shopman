import { mount, RouterLinkStub } from "@vue/test-utils";
import { computed, ref } from "vue";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import MarketingDecisionQueue from "~/components/MarketingDecisionQueue.vue";
import type { DecisionItem, DecisionQueue } from "~/types/decisions";
// O estado da tela entra de verdade: as frases são do kit, e é delas que a fila depende.
import OperatorScreenState from "../../../operator-kit/app/components/OperatorScreenState.vue";

const NOW = Date.parse("2026-10-03T10:03:00-03:00");
const queue = ref<DecisionQueue | null>(null);
const error = ref<unknown>(null);
const loading = ref(false);
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
    ref,
    // A tecla R atualiza a fila (V6-MKT); sem runtime Nuxt, o atalho é inerte.
    onKeyStroke: () => undefined,
    useMarketingDecisions: () => ({
      queue,
      items: computed(() => queue.value?.items ?? []),
      automaticChecks: computed(() => queue.value?.automatic_checks ?? []),
      shopTimezone: ref("America/Sao_Paulo"),
      nowMs: ref(NOW),
      loading,
      error,
      refresh,
    }),
    useMarketingLiveStatus: () =>
      computed(() => ({ tone: "live", label: "Ao vivo", time: "10:03", detail: "" })),
  });
});

beforeEach(() => {
  error.value = null;
  loading.value = false;
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

// O cabeçalho da suíte tem teste próprio no kit; aqui, o que a tela entrega a ele: o
// título, o estado, a ação primária e as ações declaradas como dados.
const HeaderStub = {
  props: ["title", "actions", "phoneActions", "actionsLabel"],
  template:
    '<header><h1>{{ title }}</h1><slot name="status" /><slot name="actions" /></header>',
};

function render() {
  return mount(MarketingDecisionQueue, {
    global: {
      components: { OperatorScreenState },
      stubs: {
        Icon: true,
        NuxtLink: RouterLinkStub,
        OperatorLiveStatus: true,
        OperatorPageHeader: HeaderStub,
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
    expect(cards[0]!.text()).toContain("Instagram, Facebook e WhatsApp (86 clientes)");
    expect(cards[0]!.text()).toContain("Decide até 10:15");
    expect(cards[0]!.text()).toContain("faltam 12 min");
    // O mais urgente tem destaque (v4: o anel na cor da ação).
    expect(cards[0]!.attributes("data-decision-focus")).toBe("true");
    expect(cards[0]!.get("[data-decision-card]").classes()).toContain("ring-primary");
    expect(cards[1]!.attributes("data-decision-focus")).toBeUndefined();
    expect(cards[1]!.get("[data-decision-card]").classes()).not.toContain("ring-primary");
    expect(wrapper.get("h1").text()).toBe("Decisões");
  });

  it("tem um gesto só por cartão, que abre o lugar onde a decisão já é tomada", () => {
    const wrapper = render();
    const reviews = wrapper.findAll("[data-decision-review]");

    expect(reviews.map((link) => link.attributes("href"))).toEqual([
      "/announcements/12#review",
      "/announcements/9#result",
    ]);
    expect(reviews.map((link) => link.text())).toEqual(["Revisar", "Revisar"]);
    // Cheio só no mais urgente: o estado ativo do botão, nunca a troca de variante.
    expect(reviews.map((link) => link.attributes("variant"))).toEqual(["outline", "outline"]);
    expect(reviews.map((link) => link.attributes("active"))).toEqual(["true", "false"]);
    expect(reviews[0]!.attributes("active-variant")).toBe("solid");
  });

  it("escreve o motivo da falha no cartão, num aviso de erro", () => {
    const failure = render().findAll("[data-decision]")[1]!;

    expect(failure.text()).toContain("Falhou no Instagram · 1 envio");
    expect(failure.get("[role='alert']").text()).toContain(
      "A conexão com a plataforma caiu antes do envio.",
    );
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

  it("leva a ação primária ao cabeçalho, e o resto ao ⋯ com Atualizar (R)", () => {
    const wrapper = render();
    const header = wrapper.getComponent(HeaderStub);

    expect(wrapper.get("[data-decisions-primary]").attributes("href")).toBe(
      "/settings/campaigns",
    );
    expect(header.props("actionsLabel")).toBe("Mais ações de Decisões");
    const desk = header.props("actions") as Array<Record<string, unknown>>;
    expect(desk.map((action) => action.label)).toEqual([
      "Modelos de texto",
      "Enviados",
      "Atualizar",
    ]);
    // No celular a primária disputa a vaga de ícone; na mesa ela é o botão cheio.
    const phone = header.props("phoneActions") as Array<Record<string, unknown>>;
    expect(phone[0]).toMatchObject({
      label: "Preparar disparo",
      to: "/settings/campaigns",
      priority: 1,
    });
    const update = desk.find((action) => action.label === "Atualizar")!;
    expect(update.kbds).toEqual(["R"]);
    (update.onSelect as () => void)();
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("diz que não há decisão esperando, no padrão da suíte", () => {
    queue.value = { ...queue.value!, items: [], automatic_checks: [] };
    const wrapper = render();

    expect(wrapper.find("[data-decision]").exists()).toBe(false);
    expect(wrapper.get("[data-decisions-empty]").text()).toContain(
      "Nenhuma decisão espera você agora.",
    );
  });

  it("não confunde fila vazia com fila que não carregou", async () => {
    queue.value = null;
    loading.value = true;
    expect(render().get("[data-operator-screen-state='loading']").text()).toContain(
      "Carregando as decisões",
    );

    loading.value = false;
    error.value = new Error("offline");
    const failed = render();
    const alert = failed.get("[role='alert']");
    expect(alert.text()).toContain("Não foi possível carregar as decisões");
    expect(alert.text()).toContain("Isso não quer dizer que nada pede você.");
    await alert.get("button").trigger("click");
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
