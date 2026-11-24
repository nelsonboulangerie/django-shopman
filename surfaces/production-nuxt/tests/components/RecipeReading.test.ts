import { computed, defineComponent, h, nextTick, ref, watch } from "vue";
import { enableAutoUnmount, flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { nuxtUiStubs } from "../support/nuxtUiStubs";
import RecipeComparePage from "../../app/pages/recipes/compare.vue";
import RecipeReviewPage from "../../app/pages/recipes/review.vue";
import IngredientPicker from "../../app/components/IngredientPicker.vue";
import type { RecipeCompareProjection } from "../../app/types/recipeBook";

// Receitas que se leem (WP-F05): comparar diz qual é qual, o "Conferir" que falhou
// na primeira leitura oferece tentar de novo, e o vazio da busca de insumo leva ao Compras.

const refresh = vi.fn();

const OperatorScreenStateStub = defineComponent({
  name: "OperatorScreenState",
  props: { state: String, what: String },
  emits: ["retry"],
  setup(props, { emit }) {
    return () =>
      h("section", { "data-screen-state": props.state }, [
        props.what,
        h("button", { onClick: () => emit("retry") }, "Tentar de novo"),
      ]);
  },
});

const RecipeHeaderStub = defineComponent({
  name: "RecipeHeader",
  props: { title: String, subtitle: String },
  setup(props) {
    return () => h("header", props.title);
  },
});

const SelectMenuStub = defineComponent({
  name: "NuxtSelectMenu",
  setup(_, { slots }) {
    return () => h("div", { "data-select-menu": "" }, slots.empty?.());
  },
});

const stubs = {
  ...nuxtUiStubs,
  Icon: true,
  NuxtIcon: true,
  NuxtSelectMenu: SelectMenuStub,
  NuxtInputNumber: true,
  NuxtFormField: { template: "<div><slot /></div>" },
  NuxtCard: { template: "<div><slot /></div>" },
  NuxtEmpty: true,
  OperatorTable: true,
  OperatorScreenState: OperatorScreenStateStub,
  RecipeHeader: RecipeHeaderStub,
  NuxtLink: { props: ["to"], template: "<a :href='to'><slot /></a>" },
};

function compare(over: Partial<RecipeCompareProjection> = {}): RecipeCompareProjection {
  return {
    a_title: "Pão francês (versão 1)",
    a_status: "superseded",
    a_status_label: "Substituída",
    a_is_current: false,
    a_when_display: "publicada 02/10/2026 05:40",
    b_title: "Pão francês (versão 2)",
    b_status: "published",
    b_status_label: "Publicada",
    b_is_current: true,
    b_when_display: "publicada 18/11/2026 06:10",
    rows: [],
    metrics: [],
    ...over,
  };
}

let reviewItems = ref<unknown[]>([]);
let reviewError = ref<unknown>(null);
let purchaseUrl = "";

beforeEach(() => {
  refresh.mockReset();
  reviewItems = ref([]);
  reviewError = ref(null);
  purchaseUrl = "";
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("nextTick", nextTick);
  vi.stubGlobal("useHead", () => {});
  vi.stubGlobal("useRoute", () => ({ query: { a: "pao-frances@1", b: "pao-frances@2" }, params: {} }));
  vi.stubGlobal("useRouter", () => ({ replace: vi.fn() }));
  vi.stubGlobal("useTouchPointer", () => false);
  vi.stubGlobal("useRecipeBook", () => ({ entries: ref([]), pending: ref(false) }));
  vi.stubGlobal("useRecipeCompare", () => ({
    ready: computed(() => true),
    compare: computed(() => compare()),
    rows: computed(() => []),
    metrics: computed(() => []),
    pending: ref(false),
    error: ref(null),
    refresh,
  }));
  vi.stubGlobal("useRecipeReview", () => ({
    queue: ref(null),
    items: reviewItems,
    canEdit: computed(() => true),
    forbidden: computed(() => false),
    pending: ref(false),
    error: reviewError,
    refresh,
  }));
  vi.stubGlobal("useIngredientSearch", () => ({
    options: ref([]),
    pending: ref(false),
    run: vi.fn(),
    search: vi.fn(),
    reset: vi.fn(),
  }));
  vi.stubGlobal("useRecipeBookAccess", () => ({
    access: computed(() => ({ can_view: true, can_edit: true, capture_available: false, purchase_url: purchaseUrl })),
  }));
  vi.stubGlobal("useOperatorAppLink", () => ({ attrsFor: () => ({ target: "_blank", rel: "noopener" }) }));
});
afterEach(() => vi.unstubAllGlobals());
enableAutoUnmount(afterEach);

describe("Comparar: qual é qual (P2-20)", () => {
  it("each side names its state, whether it is the current one, and since when", async () => {
    const wrapper = mount(RecipeComparePage, { global: { stubs } });
    await flushPromises();

    const a = wrapper.find('[data-compare-side="a"]').text();
    const b = wrapper.find('[data-compare-side="b"]').text();
    expect(a).toContain("Pão francês (versão 1)");
    expect(a).toContain("Substituída");
    expect(a).toContain("publicada 02/10/2026 05:40");
    expect(a).not.toContain("Atual");
    expect(b).toContain("Publicada");
    expect(b).toContain("Atual");
    expect(b).toContain("publicada 18/11/2026 06:10");
  });
});

describe("Conferir: a primeira leitura falhou", () => {
  it("shows the error state with a retry instead of an empty list", async () => {
    reviewError.value = new Error("offline");
    const wrapper = mount(RecipeReviewPage, { global: { stubs } });
    await flushPromises();

    const state = wrapper.find('[data-screen-state="error"]');
    expect(state.exists()).toBe(true);
    expect(wrapper.find("[data-review-queue]").exists()).toBe(false);
    await state.find("button").trigger("click");
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});

describe("Busca de insumo: o vazio leva ao Compras (#2390)", () => {
  it("offers Abrir o Compras pointing to the materials of the Compras", async () => {
    purchaseUrl = "https://compras.exemplo.test";
    const wrapper = mount(IngredientPicker, { props: { modelValue: "" }, global: { stubs } });
    await flushPromises();

    const empty = wrapper.find("[data-ingredient-empty]");
    expect(empty.text()).toContain("Nenhum insumo com esse nome.");
    const link = empty.findAll("a").find((item) => item.text() === "Abrir o Compras");
    expect(link?.attributes("href")).toBe("https://compras.exemplo.test/base/materials");
  });

  it("without the Compras (who does not operate it) there is no link, only the sentence", async () => {
    const wrapper = mount(IngredientPicker, { props: { modelValue: "" }, global: { stubs } });
    await flushPromises();

    const empty = wrapper.find("[data-ingredient-empty]");
    expect(empty.text()).toContain("Insumo novo se cadastra no Compras.");
    expect(empty.text()).not.toContain("Abrir o Compras");
  });
});
