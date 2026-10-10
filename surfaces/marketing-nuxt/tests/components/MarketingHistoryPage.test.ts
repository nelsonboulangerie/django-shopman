import { mount, RouterLinkStub } from "@vue/test-utils";
import { computed, onMounted, ref, watch } from "vue";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import HistoryPage from "~/pages/history.vue";
import OperatorScreenState from "../../../operator-kit/app/components/OperatorScreenState.vue";

// Enviados na fase 2: os quatro recortes viram `NuxtSelect` rotulados no `#filters` do
// cabeçalho (no celular, o painel "Filtros"), cada recorte fora do padrão vira chip
// removível, e o erro com lista na tela mantém as linhas e diz isso.
const filters = ref<Record<string, string>>({ period: "all" });
const announcements = ref<unknown[]>([]);
const error = ref<unknown>(null);
const loadMoreError = ref<unknown>(null);
const loading = ref(false);
const hasMore = ref(false);
const setFilter = vi.fn();
const clearFilters = vi.fn();
const refresh = vi.fn();
const loadMore = vi.fn();

const announcement = {
  ref: "announcement:42",
  state: "approved",
  decision_actor_policy: "operator",
  facts: { trigger: "production_finished", product_ref: "product:PAO-01" },
  created_at: "2026-10-08T09:00:00-03:00",
  approved_at: "2026-10-08T09:05:00-03:00",
  published_at: "2026-10-08T09:06:00-03:00",
  settled_at: "2026-10-08T09:07:00-03:00",
  delivery: { state: "succeeded", platforms: [] },
};

const HeaderStub = {
  props: ["title", "actions", "actionsLabel", "activeFilters", "clearFilters", "alerts"],
  template:
    '<header><h1>{{ title }}</h1><slot name="status" /><div data-filters><slot name="filters" /></div><slot name="filters-end" /></header>',
};

beforeAll(() => {
  Object.assign(globalThis, {
    computed,
    ref,
    watch,
    onMounted,
    onKeyStroke: () => undefined,
    useHead: () => undefined,
    useCampaigns: () => ({ products: ref([]) }),
    useMarketingLiveStatus: () =>
      computed(() => ({ tone: "live", label: "Ao vivo", time: "10:03", detail: "" })),
    useCampaignHistory: () => ({
      announcements,
      actions: ref([]),
      filters,
      hasActiveFilters: computed(
        () =>
          Object.entries(filters.value).some(
            ([key, value]) => Boolean(value) && !(key === "period" && value === "all"),
          ),
      ),
      hasMore,
      shopTimezone: ref("America/Sao_Paulo"),
      loading,
      loadingMore: ref(false),
      error,
      loadMoreError,
      loadMore,
      refresh,
      setFilter,
      clearFilters,
    }),
  });
});

beforeEach(() => {
  filters.value = { period: "all" };
  announcements.value = [announcement];
  error.value = null;
  loadMoreError.value = null;
  loading.value = false;
  hasMore.value = false;
  for (const fn of [setFilter, clearFilters, refresh, loadMore]) fn.mockReset();
});

function render() {
  return mount(HistoryPage, {
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

describe("Enviados", () => {
  it("põe os quatro recortes como Select rotulado, e a escolha vai para a URL", async () => {
    const wrapper = render();
    const fields = wrapper.findAll("[data-filters] [data-history-chip]");
    const selects = wrapper.findAll("[data-filters] select");

    expect(selects).toHaveLength(4);
    expect(fields.map((field) => field.get("span").text())).toEqual([
      "Situação",
      "Plataforma",
      "Criado em",
      "Origem da decisão",
    ]);
    expect(wrapper.find("[data-filters] button").exists()).toBe(false);

    await selects[2]!.setValue("7d");
    expect(setFilter).toHaveBeenCalledWith("period", "7d");
    await selects[1]!.setValue("all");
    expect(setFilter).toHaveBeenLastCalledWith("platform", "");
  });

  it("mostra cada recorte fora do padrão como chip removível, e Limpar limpa todos", () => {
    filters.value = { period: "7d", platform: "instagram" };
    const header = render().getComponent(HeaderStub);
    const chips = header.props("activeFilters") as Array<{
      label: string;
      remove: () => void;
    }>;

    expect(chips.map((chip) => chip.label)).toEqual([
      "Plataforma: Instagram",
      "Criado em: Últimos 7 dias",
    ]);
    chips[1]!.remove();
    expect(setFilter).toHaveBeenCalledWith("period", "");
    (header.props("clearFilters") as () => void)();
    expect(clearFilters).toHaveBeenCalledTimes(1);
    expect(header.props("actionsLabel")).toBe("Mais ações de Enviados");
  });

  it("no erro com lista na tela, as linhas ficam e o aviso diz isso", () => {
    error.value = new Error("offline");
    const wrapper = render();
    const alerts = wrapper.getComponent(HeaderStub).props("alerts") as Array<{
      title: string;
      description: string;
    }>;

    expect(wrapper.find("[data-history-row]").exists()).toBe(true);
    expect(alerts).toHaveLength(1);
    expect(alerts[0]!.description).toContain("continuam na tela");
  });

  it("carrega mais por botão, e o erro da página seguinte fica junto dele", async () => {
    hasMore.value = true;
    loadMoreError.value = new Error("offline");
    const wrapper = render();

    await wrapper.get("[data-history-load-more]").trigger("click");
    expect(loadMore).toHaveBeenCalledTimes(1);
    expect(wrapper.get("[role='alert']").text()).toContain(
      "Não foi possível carregar a próxima página.",
    );
  });

  it("diz quando nada combina com os filtros e oferece limpar", async () => {
    announcements.value = [];
    filters.value = { period: "today" };
    const wrapper = render();

    expect(wrapper.get("[data-history-empty]").text()).toContain(
      "Nenhum resultado combina com os filtros.",
    );
    await wrapper.get("[data-history-empty] button").trigger("click");
    expect(clearFilters).toHaveBeenCalledTimes(1);
  });
});
