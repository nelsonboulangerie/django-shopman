import { beforeEach, expect, it, vi } from "vitest";
import { computed, defineComponent, ref } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import Feeds from "../../app/pages/feeds.vue";

const board = ref<any>(null);
const error = ref<any>(null);
const setCollections = vi.fn();
for (const [key, value] of Object.entries({ computed, ref })) vi.stubGlobal(key, value);
vi.stubGlobal("useHead", vi.fn());
let leave: () => boolean;
vi.stubGlobal("onBeforeRouteLeave", (guard: () => boolean) => { leave = guard; });
vi.stubGlobal("useRuntimeConfig", () => ({ public: { adminBaseUrl: "", djangoBaseUrl: "" } }));
vi.stubGlobal("useFeedBoard", () => ({ board, error, errorMsg: ref(""), pending: ref(false), refresh: vi.fn(), isBusy: () => false, setCollections, setActive: vi.fn(), setRotation: vi.fn() }));
const popover = defineComponent({ props: ["open"], emits: ["update:open"], template: '<div :data-open="open"><button data-open-editor @click="$emit(\'update:open\', true)">Abrir editor</button><slot /></div>' });
const render = () => mount(Feeds, { global: { stubs: { Icon: true, UiToolbar: { template: "<div><slot/><slot name=\"end\"/></div>" }, UiIconButton: true, UiPopover: popover, UiPopoverTrigger: { template: "<div><slot/></div>" }, UiPopoverContent: { template: "<div><slot/></div>" } } } });
beforeEach(() => { board.value = null; error.value = null; setCollections.mockReset(); });

it("a failed first GET never says no feeds exist", () => {
  error.value = { status: 503 };
  const wrapper = render();
  expect(wrapper.text()).toContain("Não foi possível atualizar");
  expect(wrapper.text()).not.toContain("Nenhum feed. Crie");
});

it("failed save retains selected collections and the editor", async () => {
  board.value = { feeds: [{ ref: "tv", name: "TV", collections: [], actions: [{ ref: "collections", enabled: true, payload_schema: { base_revision: "initial" } }], capability: "feed", kind: "google", is_active: true }], all_collections: [{ ref: "bread", name: "Pães", product_count: 1 }] };
  setCollections.mockResolvedValue(false);
  const wrapper = render();
  await wrapper.get("[data-open-editor]").trigger("click");
  await wrapper.get("input[type=checkbox]").setValue(true);
  const apply = wrapper.findAll("button").find((button) => button.text() === "Aplicar")!;
  await apply.trigger("click");
  await flushPromises();
  expect(setCollections).toHaveBeenCalledWith("tv", ["bread"], "initial");
  expect((wrapper.get("input[type=checkbox]").element as HTMLInputElement).checked).toBe(true);
  expect(wrapper.get("[data-open]").attributes("data-open")).toBe("true");
});


it("same-field refresh preserves the draft and requires an explicit resolution", async () => {
  board.value = { feeds: [{ ref: "tv", name: "TV", collections: [], actions: [{ ref: "collections", enabled: true, payload_schema: { base_revision: "initial" } }], capability: "feed", kind: "google", is_active: true }], all_collections: [{ ref: "bread", name: "Pães", product_count: 1 }] };
  const wrapper = render();
  await wrapper.get("[data-open-editor]").trigger("click");
  await wrapper.get("input[type=checkbox]").setValue(true);
  const priorConfirm = window.confirm;
  const confirm = vi.fn(() => false);
  window.confirm = confirm;
  expect(leave()).toBe(false);
  expect(confirm).toHaveBeenCalled();
  window.confirm = priorConfirm;
  board.value.feeds[0].actions[0].payload_schema.base_revision = "changed";
  await flushPromises();
  let apply = wrapper.findAll("button").find((button) => button.text() === "Aplicar")!;
  expect(apply.attributes("disabled")).toBeDefined();
  expect((wrapper.get("input[type=checkbox]").element as HTMLInputElement).checked).toBe(true);
  await wrapper.findAll("button").find((button) => button.text() === "Manter minha seleção")!.trigger("click");
  apply = wrapper.findAll("button").find((button) => button.text() === "Aplicar")!;
  await apply.trigger("click");
  expect(setCollections).toHaveBeenCalledWith("tv", ["bread"], "changed");
});
