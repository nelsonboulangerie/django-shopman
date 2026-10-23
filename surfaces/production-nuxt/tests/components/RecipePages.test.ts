import { computed, defineComponent, h, nextTick, onBeforeUnmount, reactive, ref, watch } from "vue";
import { enableAutoUnmount, flushPromises, mount } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { nuxtUiStubs } from "../support/nuxtUiStubs";
import RecipeHeader from "../../app/components/RecipeHeader.vue";
import RecipeListPage from "../../app/pages/recipes/index.vue";
import RecipeDetailPage from "../../app/pages/recipes/[ref]/index.vue";
import RecipeDuplicatePanel from "../../app/components/RecipeDuplicatePanel.vue";
import RecipeExecutionFormPanel from "../../app/components/RecipeExecutionFormPanel.vue";
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
        slots["filters-primary"]?.(),
        slots["filter-panel"]?.(),
        slots.filters?.(),
        slots["filters-end"]?.(),
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

const OperatorQuickFiltersStub = defineComponent({
  name: "OperatorQuickFilters",
  props: { modelValue: Array, items: Array },
  emits: ["update:modelValue"],
  setup(props, { emit }) {
    return () => h("div", { role: "toolbar" }, (props.items as { key: string; label: string }[]).map((item) =>
      h("button", {
        "data-quick-filter-item": item.key,
        "aria-pressed": (props.modelValue as string[]).includes(item.key),
        onClick: () => emit("update:modelValue", [...(props.modelValue as string[]), item.key]),
      }, item.label),
    ));
  },
});

const OperatorScreenStateStub = defineComponent({
  name: "OperatorScreenState",
  props: { state: String, title: String },
  setup(props, { slots }) {
    return () => h("section", { "data-screen-state": props.state }, [props.title, slots.actions?.()]);
  },
});

const OperatorFilterPanelStub = defineComponent({
  name: "OperatorFilterPanel",
  props: { dimensions: Array, modelValue: Object },
  emits: ["update:modelValue"],
  setup(props, { emit }) {
    return () => h("div", { "data-filter-panel": (props.dimensions as { id: string }[]).map((item) => item.id).join(",") }, [
      h("button", {
        "data-filter-archived": "",
        onClick: () => emit("update:modelValue", { ...(props.modelValue as object), archived: ["true"] }),
      }, "Incluir arquivadas"),
    ]);
  },
});

const OperatorMoreMenuStub = defineComponent({
  name: "OperatorMoreMenu",
  props: { items: Array, label: String },
  setup(props) {
    return () => h("div", [
      h("button", props.label || "Mais ações"),
      ...(props.items as { label: string; onSelect?: () => void }[]).map((item) =>
        h("button", { onClick: item.onSelect }, item.label),
      ),
    ]);
  },
});

const passthrough = (name: string) =>
  defineComponent({ name, setup: (_, { slots }) => () => h("div", { "data-stub": name }, slots.default?.()) });

const OperatorFormShellStub = defineComponent({
  name: "OperatorFormShell",
  props: { open: Boolean, saveDisabled: Boolean, saveDisabledReason: String },
  emits: ["save", "update:open"],
  setup(props, { emit, slots }) {
    return () => props.open
      ? h("section", { "data-form-shell": "", "data-disabled-reason": props.saveDisabledReason }, [
          slots.default?.(),
          h("button", { disabled: props.saveDisabled, onClick: () => emit("save") }, "Salvar"),
        ])
      : null;
  },
});

const stubs = {
  ...nuxtUiStubs,
  Icon: true,
  NuxtLink: { props: ["to"], template: "<a :href='to'><slot /></a>" },
  NuxtSelect: true,
  NuxtSelectMenu: true,
  NuxtPagination: true,
  NuxtCard: passthrough("NuxtCard"),
  OperatorPageHeader: OperatorPageHeaderStub,
  OperatorSuiteSearch: true,
  OperatorQuickFilters: OperatorQuickFiltersStub,
  OperatorFilterPanel: OperatorFilterPanelStub,
  OperatorScreenState: OperatorScreenStateStub,
  OperatorRecordNav: OperatorRecordNavStub,
  OperatorFormShell: OperatorFormShellStub,
  OperatorFormSection: passthrough("OperatorFormSection"),
  OperatorTable: true,
  OperatorMoreMenu: OperatorMoreMenuStub,
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
    is_active: true,
    has_ficha: true,
    is_favorite: false,
    updated_at_display: "",
    ...over,
  } as RecipeEntryCardProjection;
}

const entries = ref<RecipeEntryCardProjection[]>([]);
const canEditRecipes = ref(true);

function installGlobals() {
  vi.stubGlobal("computed", computed);
  vi.stubGlobal("ref", ref);
  vi.stubGlobal("reactive", reactive);
  vi.stubGlobal("nextTick", nextTick);
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
    canEdit: computed(() => canEditRecipes.value),
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
  canEditRecipes.value = true;
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

    const favorites = wrapper.find('[data-quick-filter-item="favorites"]');
    expect(favorites.exists()).toBe(true);
    await favorites.trigger("click");
    await nextTick();

    expect(remember).toHaveBeenLastCalledWith(["pao-a"], { from: "/recipes?favorites=1", label: "Favoritas" });
  });

  it("combines multiple quick filters without losing the active cut", async () => {
    entries.value = [card("sem-sku", { is_favorite: true, output_sku: "" }), card("com-sku", { is_favorite: true })];
    const wrapper = mount(RecipeListPage, { global: { stubs } });
    await flushPromises();

    await wrapper.find('[data-quick-filter-item="favorites"]').trigger("click");
    await wrapper.find('[data-quick-filter-item="without_sku"]').trigger("click");
    await nextTick();

    expect(remember).toHaveBeenLastCalledWith(["sem-sku"], {
      from: "/recipes?without_sku=1&favorites=1",
      label: "Favoritas",
    });
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

  it("offers an explicit edit route outside the card link", async () => {
    entries.value = [card("pao-a")];
    const wrapper = mount(RecipeListPage, { global: { stubs } });
    await flushPromises();

    const edit = wrapper.findAll("a").find((link) => link.text() === "Editar");
    expect(edit?.attributes("href")).toBe("/recipes/pao-a/edit");
    expect(edit?.attributes("aria-label")).toBe("Editar Receita pao-a");
    expect(edit?.element.parentElement?.closest("a")).toBeNull();
  });

  it("does not offer editing without permission or for an archived recipe", async () => {
    entries.value = [card("arquivada", { is_active: false })];
    let wrapper = mount(RecipeListPage, { global: { stubs } });
    await flushPromises();
    expect(wrapper.findAll("a").some((link) => link.text() === "Editar")).toBe(false);

    wrapper.unmount();
    entries.value = [card("ativa")];
    canEditRecipes.value = false;
    wrapper = mount(RecipeListPage, { global: { stubs } });
    await flushPromises();
    expect(wrapper.findAll("a").some((link) => link.text() === "Editar")).toBe(false);
  });

  it("uses the suite filter panel and screen state instead of parallel list controls", async () => {
    const wrapper = mount(RecipeListPage, { global: { stubs } });
    await flushPromises();

    expect(wrapper.find("[data-filter-panel='kind,mode,archived']").exists()).toBe(true);
    expect(wrapper.find('[data-screen-state="empty"]').text()).toContain("Nenhuma receita cadastrada");
    expect(wrapper.findAll('[role="checkbox"]')).toHaveLength(0);
  });

  it("treats archived as an active filter when the list is empty", async () => {
    const wrapper = mount(RecipeListPage, { global: { stubs } });
    await flushPromises();

    await wrapper.find("[data-filter-archived]").trigger("click");
    await nextTick();

    expect(wrapper.find('[data-screen-state="empty"]').text()).toContain("corresponde aos filtros");
    expect(remember).toHaveBeenLastCalledWith([], { from: "/recipes?archived=1", label: "Receitas" });
  });
});

describe("Receita: anterior e próxima no cabeçalho", () => {
  function installEntry(over: Record<string, unknown> = {}, canEdit = true) {
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
      revision: "2026-10-14T02:03:04+00:00",
      execution: {
        exists: false,
        max_started_minutes: null,
        capacity_per_day: "",
        requires_batch_tracking: false,
        shelf_life_days: null,
        shelf_life_reviewed: false,
        shelf_life_reviewed_by: "",
        shelf_life_reviewed_at_display: "",
        production_lifecycle: "",
        lifecycle_options: [],
        revision: "",
      },
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
      is_active: true,
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
      canEdit: computed(() => canEdit),
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
      saveExecution: vi.fn(async () => ({ ok: true })),
      duplicate: vi.fn(async () => ({ ok: true })),
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

  it("offers one direct Editar action in the detail header", async () => {
    routeParams = { ref: "pao-b" };
    installEntry();
    const wrapper = mount(RecipeDetailPage, { global: { stubs } });
    await flushPromises();

    const edit = wrapper.findAll("a").find((link) => link.text() === "Editar");
    expect(edit?.attributes("href")).toBe("/recipes/pao-b/edit");
    expect(wrapper.text()).not.toContain("Editar rascunho");
    expect(wrapper.text()).not.toContain("Nova versão");
  });

  it("does not offer editing without permission or for an archived recipe", async () => {
    routeParams = { ref: "pao-b" };
    installEntry({}, false);
    let wrapper = mount(RecipeDetailPage, { global: { stubs } });
    await flushPromises();
    expect(wrapper.findAll("a").some((link) => link.text() === "Editar")).toBe(false);

    wrapper.unmount();
    installEntry({ is_active: false });
    wrapper = mount(RecipeDetailPage, { global: { stubs } });
    await flushPromises();
    expect(wrapper.findAll("a").some((link) => link.text() === "Editar")).toBe(false);
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
    expect(navigate).toHaveBeenCalledWith("/recipes/pao-b/edit");
  });

  it("shows the archived state and names the return gesture Desarquivar", async () => {
    routeParams = { ref: "pao-b" };
    installEntry({ is_active: false });
    const wrapper = mount(RecipeDetailPage, { global: { stubs } });
    await flushPromises();

    expect(wrapper.text()).toContain("Arquivada");
    const unarchive = wrapper.findAll("button").find((button) => button.text() === "Desarquivar receita");
    expect(unarchive).toBeTruthy();
    await unarchive!.trigger("click");
    await nextTick();

    const dialog = wrapper.find('[data-overlay="NuxtModal"]');
    expect(dialog.text()).toContain("Desarquivar a receita");
    expect(dialog.text()).toContain("Ela volta à lista de receitas e pode receber versões de novo.");
  });
});

describe("Receitas: cadastros turbinados", () => {
  it("duplicates from the served revision and normalizes the new SKU", async () => {
    const source = {
      ref: "pao-b",
      name: "Pão B",
      revision: "2026-10-14T02:03:04+00:00",
      current_version_number: 3,
    } as never;
    const wrapper = mount(RecipeDuplicatePanel, {
      props: { open: true, source },
      global: { stubs },
    });
    await nextTick();
    const inputs = wrapper.findAll("input");
    expect(inputs[0].element.value).toBe("Pão B (cópia)");
    await inputs[2].setValue("sku-novo");
    await wrapper.findAll("button").find((button) => button.text() === "Salvar")!.trigger("click");

    expect(wrapper.emitted("save")?.[0]?.[0]).toEqual({
      name: "Pão B (cópia)",
      outputSku: "SKU-NOVO",
      expectedRevision: "2026-10-14T02:03:04+00:00",
    });
  });

  it("requires a fresh shelf-life review after the number changes", async () => {
    const execution = {
      exists: true,
      max_started_minutes: 90,
      capacity_per_day: "24",
      requires_batch_tracking: true,
      shelf_life_days: 3,
      shelf_life_reviewed: true,
      shelf_life_reviewed_by: "Pablo",
      shelf_life_reviewed_at_display: "hoje",
      production_lifecycle: "standard",
      lifecycle_options: [],
      revision: "2026-10-14T02:03:04+00:00",
    };
    const wrapper = mount(RecipeExecutionFormPanel, {
      props: { execution },
      global: { stubs },
    });
    await nextTick();
    const inputs = wrapper.findAll("input");
    expect(wrapper.find('[role="checkbox"][aria-label="Prazo revisado pelo responsável"]').attributes("aria-checked")).toBe("true");
    await inputs[2].setValue("4");
    await nextTick();
    expect(wrapper.find('[role="checkbox"][aria-label="Prazo revisado pelo responsável"]').attributes("aria-checked")).toBe("false");
    await wrapper.find("form").trigger("submit");

    expect(wrapper.emitted("save")?.[0]?.[0]).toMatchObject({
      shelfLifeDays: 4,
      shelfLifeReviewed: false,
      expectedRevision: "2026-10-14T02:03:04+00:00",
    });
  });

  it("blocks fractional shelf life before it reaches the server", async () => {
    const execution = {
      exists: true,
      max_started_minutes: null,
      capacity_per_day: "",
      requires_batch_tracking: false,
      shelf_life_days: null,
      shelf_life_reviewed: false,
      shelf_life_reviewed_by: "",
      shelf_life_reviewed_at_display: "",
      production_lifecycle: "",
      lifecycle_options: [],
      revision: "rev-1",
    };
    const wrapper = mount(RecipeExecutionFormPanel, {
      props: { execution },
      global: { stubs },
    });
    await nextTick();
    await wrapper.findAll("input")[2].setValue("1.5");
    await nextTick();

    const saveButton = wrapper.findAll("button").find((button) => button.text() === "Salvar configuração")!;
    expect(saveButton.attributes("disabled")).toBeDefined();
    expect(wrapper.text()).toContain("número inteiro");
  });
});
