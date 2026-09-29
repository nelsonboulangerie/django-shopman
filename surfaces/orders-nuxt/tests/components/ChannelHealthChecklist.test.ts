import { beforeEach, describe, expect, it, vi } from "vitest";
import { computed, ref, watch } from "vue";
import { flushPromises, mount } from "@vue/test-utils";

import ChannelHealthChecklist from "../../app/components/ChannelHealthChecklist.vue";
import type { ChannelHealthProjection } from "../../app/types/channelHealth";

for (const [key, value] of Object.entries({ computed, ref, watch })) vi.stubGlobal(key, value);
vi.stubGlobal("useRuntimeConfig", () => ({ public: { djangoBaseUrl: "https://api.loja", adminBaseUrl: "https://admin.loja" } }));
vi.mock("qrcode", () => ({ toCanvas: vi.fn(async () => undefined) }));

const stubs = { Icon: true, NuxtLink: { props: ["to"], template: "<a :data-to='to'><slot /></a>" } };
const render = (health: ChannelHealthProjection | null) => mount(ChannelHealthChecklist, { props: { health }, global: { stubs } });

const tv = (over: Partial<ChannelHealthProjection> = {}): ChannelHealthProjection => ({
  ref: "tv", ready: false, summary: "2 pendências",
  items: [
    { key: "active", state: "ok", label: "Ligado", hint: "", action_label: "", action_target: "", action_path: "" },
    { key: "collections", state: "todo", label: "Nenhuma coleção escolhida: nada a exibir", hint: "", action_label: "Escolher coleções", action_target: "collections", action_path: "" },
    { key: "paired", state: "todo", label: "Nenhuma TV autorizada a mostrar este quadro", hint: "Abra o endereço na TV e entre uma vez com um operador.", action_label: "Parear uma TV", action_target: "pair", action_path: "" },
  ],
  preview: [{ label: "Ver a tela da TV", target: "django", path: "/menuboard/tv/" }],
  ...over,
});

describe("ChannelHealthChecklist", () => {
  beforeEach(() => vi.clearAllMocks());

  it("canal com pendência nasce aberto, pendências primeiro e cada uma com o botão", () => {
    const wrapper = render(tv());
    expect(wrapper.get("[data-health-summary]").text()).toBe("2 pendências");
    const keys = wrapper.findAll("[data-health-item]").map((li) => li.attributes("data-health-item"));
    expect(keys).toEqual(["collections", "paired", "active"]);
    expect(wrapper.get("[data-health-item=paired]").text()).toContain("Parear uma TV");
    expect(wrapper.get("[data-health-item=active]").find("[data-health-action]").exists()).toBe(false);
    expect(wrapper.get("[data-health-preview]").attributes("href")).toBe("https://api.loja/menuboard/tv/");
  });

  it("canal pronto mostra só 'Tudo certo', recolhido", async () => {
    const wrapper = render(tv({ ready: true, summary: "Tudo certo", items: [{ key: "active", state: "ok", label: "Ligado", hint: "", action_label: "", action_target: "", action_path: "" }] }));
    expect(wrapper.get("[data-health-summary]").text()).toBe("Tudo certo");
    expect(wrapper.find("[data-health-items]").exists()).toBe(false);
    await wrapper.findAll("button").find((b) => b.text() === "Ver o que foi conferido")!.trigger("click");
    expect(wrapper.find("[data-health-items]").exists()).toBe(true);
  });

  it("Parear uma TV mostra o endereço e desenha o QR dele", async () => {
    const wrapper = render(tv());
    expect(wrapper.find("[data-health-pairing]").exists()).toBe(false);
    await wrapper.get("[data-health-item=paired] [data-health-action]").trigger("click");
    await flushPromises();
    expect(wrapper.get("[data-health-address]").text()).toBe("https://api.loja/menuboard/tv/");
    const { toCanvas } = await import("qrcode");
    expect(toCanvas).toHaveBeenCalledWith(expect.anything(), "https://api.loja/menuboard/tv/", expect.anything());
  });

  it("Escolher coleções devolve ao card, que abre a escolha de coleções", async () => {
    const wrapper = render(tv());
    await wrapper.get("[data-health-item=collections] [data-health-action]").trigger("click");
    expect(wrapper.emitted("choose-collections")).toHaveLength(1);
  });

  it("recusados do iFood levam ao catálogo já recortado", () => {
    const wrapper = render({
      ref: "ifood", ready: false, summary: "1 pendência", preview: [],
      items: [{ key: "refused", state: "todo", label: "3 produtos recusados pelo iFood", hint: "", action_label: "Ver e corrigir", action_target: "gestor", action_path: "/catalog?surface=ifood&sync=error" }],
    });
    const link = wrapper.get("[data-health-item=refused] [data-health-action]");
    expect(link.text()).toBe("Ver e corrigir");
    expect(link.attributes("data-to")).toBe("/catalog?surface=ifood&sync=error");
  });

  it("sem checklist para o canal, não desenha nada", () => {
    expect(render(null).find("[data-channel-health]").exists()).toBe(false);
  });
});
