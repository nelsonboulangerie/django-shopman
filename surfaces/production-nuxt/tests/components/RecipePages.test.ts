import { computed, defineComponent, h, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { enableAutoUnmount, flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { nuxtUiStubs } from "../support/nuxtUiStubs";
import RecipeHeader from "../../app/components/RecipeHeader.vue";
import RecipeListPage from "../../app/pages/recipes/index.vue";
import RecipeDetailPage from "../../app/pages/recipes/[ref]/index.vue";
import type { RecipeEntryCardProjection } from "../../app/types/recipeBook";

// As telas de receitas sem o runtime Nuxt: os composables viram dados de teste, as peças
// Nuxt UI viram os stubs da suíte e as do kit (cabeçalho, busca, trilha) viram stubs
// locais que mostram o que importa aqui: o `#status` do cabeçalho e as props da trilha.

const remember = vi.fn();
const replace = vi.fn();
const navigate = vi.fn();
let routeQuery: Record<string, string> = {};
let routeParams: Record<string, string> = {};

const OperatorPageHeaderStub = defineComponent({
  name: "OperatorPageHeader",
  props: { title: String, eyebrow: String },
  setup(props, { slots }) {
    return () =>
      h("header", [
        slots.lead?.(),
        h("h1", props.title),
        h("div", { "data-header-status": "" }, slots.status?.()),
        slots.search?.(),
        slots.actions?.(),
      ]);
  },
});

const OperatorRecordNavStub = defineComponent({
  name: "OperatorRecordNav",
  props: {
    trail: String,
    current: String,
    to: Function,
    previousLabel: String,
    nextLabel: String,
  },
  setup(props) {
    return () => h("nav", { "data-record-nav": props.trail }, `${props.previousLabel} | ${props.nextLabel}`);
  },
});

const passthrough = (name: string) =>
  defineComponent({ name, setup: (_, { slots }) => () => h("div", { "data-stub": name }, slots.default?.()) });

const stubs = {
  ...nuxtUiStubs,
  Icon: true,
  NuxtLink: { props: ["to"], template: "<a :href='to'><slot /></a>" },
  NuxtSelect: true,
  NuxtSelectMenu: true,
  NuxtCard: passthrough("NuxtCard"),
  OperatorPageHeader: OperatorPageHeaderStub,
  OperatorSuiteSearch: true,
  OperatorRecordNav: OperatorRecordNavStub,
  OperatorTable: true,
  // O cabeçalho é o de verdade: é ele que repassa o `#status` ao `OperatorPageHeader`.
  RecipeHeader,
  FormulaLens: true,
  RecipeVersionRating: true,
  RecipeExternalReferences: true,
};

function card(ref_: string, over: Partial<RecipeEntryCardProjection> = {}): RecipeEntryCardProjection {
  return {
    ref: ref_,
    name: `Receita ${ref_}`,
    kind: "bread",
    kind_label: "Pão",
    output_sku: `SKU-${ref_}`,
    output_name: "",
    current_version_number: 1,
    version_count: 1,
    hydration_display: "",
    rating_display: "",
    rating_count: 0,
    draft_count: 0,
    is_archived: false,
    has_ficha: true,
    is_favorite: false,
    updated_at_display: "",
    ...over,
  } as RecipeEntryCardProjection;
}

const entries = ref<RecipeEntryCardProjection[]>([]);

function installGlobals() {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("watch", watch);
  vi.stubGlobal("onBeforeUnmount", onBeforeUnmount);
  vi.stubGlobal("useHead", () => {});
  vi.stubGlobal("navigateTo", navigate);
  vi.stubGlobal("useRoute", () => ({ query: routeQuery, params: routeParams }));
  vi.stubGlobal("useRouter", () => ({ replace }));
  vi.stubGlobal("useSonner", { success: vi.fn(), error: vi.fn() });
  vi.stubGlobal("useRecordTrail", () => ({ trail: computed(() => null), remember, load: vi.fn() }));
  vi.stubGlobal("useRecipeBook", () => ({
    entries,
    kinds: computed(() => [
      { value: "bread", label: "Pão" },
      { value: "cream", label: "Creme" },
    ]),
    canEdit: computed(() => true),
    forbidden: computed(() => false),
    pending: ref(false),
    error: ref(null),
    refresh: vi.fn(),
    toggleFavorite: vi.fn(),
    isFavoriteBusy: () => false,
  }));
}

beforeEach(() => {
  remember.mockReset();
  replace.mockReset();
  navigate.mockReset();
  routeQuery = {};
  routeParams = {};
  entries.value = [];
  installGlobals();
});
afterEach(() => vi.unstubAllGlobals());
enableAutoUnmount(afterEach);

describe("Receitas: a lista grava a trilha que a receita percorre", () => {
  it("records the visible order with the list address and 'Receitas'", async () => {
    entries.value = [card("pao-a"), card("pao-b"), card("creme-c", { kind: "cream", kind_label: "Creme" })];
    mount(RecipeListPage, { global: { stubs } });
    await flushPromises();

    expect(remember).toHaveBeenLastCalledWith(["pao-a", "pao-b", "creme-c"], { from: "/recipes", label: "Receitas" });
  });

  it("keeps the cut: a kind filter narrows the trail and names it", async () => {
    routeQuery = { kind: "cream", q: "creme" };
    entries.value = [card("pao-a"), card("creme-c", { kind: "cream", kind_label: "Creme", name: "Creme de baunilha" })];
    mount(RecipeListPage, { global: { stubs } });
    await flushPromises();

    expect(remember).toHaveBeenLastCalledWith(["creme-c"], { from: "/recipes?q=creme&kind=cream", label: "Creme" });
  });

  it("follows the filters the operator toggles (favorites only)", async () => {
    entries.value = [card("pao-a", { is_favorite: true }), card("pao-b")];
    const wrapper = mount(RecipeListPage, { global: { stubs } });
    await flushPromises();

    const favorites = wrapper.findAll('[role="checkbox"]').find((box) => box.attributes("aria-label") === "Favoritas");
    expect(favorites).toBeTruthy();
    await favorites!.trigger("click");
    await nextTick();

    expect(remember).toHaveBeenLastCalledWith(["pao-a"], { from: "/recipes", label: "Favoritas" });
  });

  it("the star is a pressed-state toggle button, not a native control in the card link", async () => {
    entries.value = [card("pao-a", { is_favorite: true })];
    const wrapper = mount(RecipeListPage, { global: { stubs } });
    await flushPromises();

    const star = wrapper.find('button[aria-pressed="true"]');
    expect(star.exists()).toBe(true);
    expect(star.attributes("aria-label")).toContain("Receita pao-a");
    expect(star.element.closest("a")).toBeNull();
  });
});

describe("Receita: anterior e próxima no cabeçalho", () => {
  function installEntry(over: Record<string, unknown> = {}) {
    const version = {
      id: 1,
      number: 1,
      status: "draft",
      status_label: "Rascunho",
      label: "",
      yield_display: "",
      lens: { items: [] },
      steps: [],
      notes: "",
      source_label: "Manual",
      published_at_display: "",
      created_at_display: "",
      created_by: "",
      formula: {},
      yield_quantity: "1",
      yield_unit: "kg",
    };
    const entry = ref({
      ref: "pao-b",
      name: "Pão B",
      kind: "bread",
      kind_label: "Pão",
      output_sku: "",
      output_name: "",
      ficha_ref: "",
      is_archived: false,
      is_favorite: false,
      notes: "",
      current_version_number: null,
      rating_criteria: [],
      ratings: [],
      external_references: [],
      ...over,
    });
    vi.stubGlobal("useRecipeEntry", () => ({
      entry,
      canEdit: computed(() => true),
      versions: computed(() => [version]),
      currentVersion: computed(() => null),
      versionByNumber: () => null,
      notFound: computed(() => false),
      forbidden: computed(() => false),
      pending: ref(false),
      error: ref(null),
      refresh: vi.fn(),
      busy: ref(false),
      patchEntry: vi.fn(async () => ({ ok: true })),
      createVersion: vi.fn(),
      publish: vi.fn(),
      saveReferences: vi.fn(),
      rateVersion: vi.fn(),
      toggleFavorite: vi.fn(),
      favoriteBusy: ref(false),
    }));
    vi.stubGlobal("useRecipeCompare", () => ({
      rows: computed(() => []),
      metrics: computed(() => []),
      ready: computed(() => false),
      pending: ref(false),
      error: ref(null),
    }));
  }

  it("puts OperatorRecordNav in the header status with the recipe trail and recipe addresses", async () => {
    routeParams = { ref: "pao-b" };
    installEntry();
    const wrapper = mount(RecipeDetailPage, { global: { stubs } });
    await flushPromises();

    const nav = wrapper.findComponent(OperatorRecordNavStub);
    expect(nav.exists()).toBe(true);
    expect(nav.element.closest("[data-header-status]")).not.toBeNull();
    expect(nav.props("trail")).toBe("production-recipes");
    expect(nav.props("current")).toBe("pao-b");
    expect((nav.props("to") as (id: string) => string)("pao-c")).toBe("/recipes/pao-c");
    expect(nav.text()).toBe("Receita anterior | Próxima receita");
  });

  it("publishing without SKU says why and leads to the fix", async () => {
    routeParams = { ref: "pao-b" };
    installEntry();
    const wrapper = mount(RecipeDetailPage, { global: { stubs } });
    await flushPromises();

    const publish = wrapper.findAll("button").find((button) => button.text() === "Publicar");
    await publish!.trigger("click");
    await nextTick();

    const dialog = wrapper.find('[data-overlay="NuxtModal"]');
    expect(dialog.text()).toContain("Associe um SKU antes de publicar.");
    const fix = dialog.findAll("button").find((button) => button.text() === "Associar SKU");
    await fix!.trigger("click");
    await nextTick();

    expect(wrapper.find('[data-overlay="NuxtModal"]').exists()).toBe(false);
    expect(wrapper.find('input[aria-label="SKU do produto"]').exists()).toBe(true);
  });
});
