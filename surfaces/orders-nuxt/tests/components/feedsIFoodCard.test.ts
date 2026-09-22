import { beforeEach, expect, it, vi } from "vitest";
import { computed, ref, toValue } from "vue";
import { mount } from "@vue/test-utils";
import Feeds from "../../app/pages/feeds.vue";

// O controle da loja no iFood mora no card do canal iFood (aba Canais); o sinal da
// aba Pedidos chega com `?focus=ifood` e o card vai para a linha de foco.
const board = ref<any>(null);
const query = ref<Record<string, string>>({});
const focusSources: unknown[] = [];
for (const [key, value] of Object.entries({ computed, ref })) vi.stubGlobal(key, value);
vi.stubGlobal("useHead", vi.fn());
vi.stubGlobal("onBeforeRouteLeave", vi.fn());
vi.stubGlobal("useRoute", () => ({ get query() { return query.value; } }));
vi.stubGlobal("useNextFocus", (source: unknown) => { focusSources.push(source); return { reveal: vi.fn() }; });
vi.stubGlobal("useRuntimeConfig", () => ({ public: { adminBaseUrl: "", djangoBaseUrl: "" } }));
vi.stubGlobal("useFeedBoard", () => ({ board, error: ref(null), errorMsg: ref(""), pending: ref(false), refresh: vi.fn(), isBusy: () => false, setCollections: vi.fn(), switchChannel: vi.fn(), setRotation: vi.fn() }));

const channel = (ref_: string, name: string) => ({
  ref: ref_, name, projection_enabled: true, diagnostic: "Envio configurado.", synced: 3, pending: 0, errors: 0,
  retracted: 0, skipped: 1, observed: 4, catalog_path: "/catalog",
});
const render = () => mount(Feeds, {
  global: {
    stubs: {
      Icon: true, NuxtLink: { template: "<a><slot /></a>" }, ReadFreshness: true, UiIconButton: true,
      UiToolbar: { template: "<div><slot/><slot name=\"end\"/></div>" },
      IFoodChannelStore: { template: "<div data-ifood-store-stub />" },
    },
  },
});

beforeEach(() => {
  query.value = {};
  focusSources.length = 0;
  board.value = { feeds: [], all_collections: [], catalog_channels: [channel("ifood", "iFood"), channel("web", "Loja online")] };
});

it("só o card do iFood carrega a loja no iFood; todo card é alvo de foco pelo ref", () => {
  const wrapper = render();
  const ifood = wrapper.get("[data-channel-card='ifood']");
  const web = wrapper.get("[data-channel-card='web']");
  expect(ifood.find("[data-ifood-store-stub]").exists()).toBe(true);
  expect(web.find("[data-ifood-store-stub]").exists()).toBe(false);
  expect(ifood.attributes("data-focus-target")).toBe("ifood");
  expect(web.attributes("data-focus-target")).toBe("web");
});

it("a frase da seção diz de que é o registro de envio, sem negar o estado lido do iFood", () => {
  const text = render().text();
  expect(text).not.toContain("Não representam o estado atual da loja na plataforma");
  expect(text).toContain("Envio de produtos: o que a casa registrou ao mandar o catálogo a cada canal.");
  expect(text).toContain("Envio de produtos: 3 sincronizados");
});

it("chegando com ?focus=<ref> o foco é o card daquele canal; ref desconhecido ou ausente, nenhum", () => {
  render();
  expect(toValue(focusSources[0] as any)).toBeNull();
  for (const [focus, expected] of [["ifood", "ifood"], ["web", "web"], ["fantasma", null]] as const) {
    query.value = { focus };
    focusSources.length = 0;
    render();
    expect(toValue(focusSources[0] as any)).toBe(expected);
  }
});
