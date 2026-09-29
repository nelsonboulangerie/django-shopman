import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { computed, ref } from "vue";
import { mount } from "@vue/test-utils";

import ChannelQueueSignal from "../../app/components/ChannelQueueSignal.vue";
import GestorTopBar from "../../app/components/GestorTopBar.vue";
import type { ChannelAttentionProjection } from "../../app/types/channelAttention";

vi.stubGlobal("computed", computed);
vi.stubGlobal("ref", ref);
const attention = ref<ChannelAttentionProjection | null>(null);
vi.stubGlobal("useChannelAttention", () => ({ attention, refresh: vi.fn() }));
vi.stubGlobal("useRoute", () => ({ path: "/" }));
vi.stubGlobal("useRuntimeConfig", () => ({ public: { adminBaseUrl: "" } }));
// A barra pergunta à antessala se mostra Clientes; aqui, a resposta é "não".
vi.stubGlobal("useNuxtData", () => ({ data: ref(null) }));
vi.stubGlobal("useOperatorResourceKey", (resource: string) => `orders:test:${resource}`);
vi.stubGlobal("useFetch", () => ({ data: ref({ authorized: false }) }));

const stubs = { Icon: true, RailToggle: true, NuxtLink: { props: ["to"], template: "<a :data-to='to'><slot /></a>" } };

// O desenho da barra de seções é do kit (`OperatorAppBar`, com teste próprio do ponto
// âmbar). O que cabe ao Gestor — e é o que este arquivo cobra — é ENTREGAR a atenção
// do canal na seção certa. O duble abaixo só expõe o que foi entregue.
const appBarStub = {
  props: ["sections", "label", "current"],
  template: `<header><span
      v-for="section in sections"
      :key="section.key"
      :data-section="section.key"
    ><span v-if="section.attention" :data-channels-attention="section.key">{{ section.attention }}</span></span><slot name="end" /></header>`,
};

const item = (ref_: string, kind: "sale" | "display", state: "off" | "paused" | "diverges", line: string) =>
  ({ ref: ref_, name: ref_, kind, state, line, focus_path: `/feeds?focus=${ref_}` });

function projection(over: Partial<ChannelAttentionProjection> = {}): ChannelAttentionProjection {
  return { count: 0, label: "", items: [], queue: [], can_open_channels: true, ...over };
}

describe("aviso de canal na fila de Pedidos", () => {
  beforeEach(() => { attention.value = projection(); });

  it("estado normal: não existe", () => {
    expect(mount(ChannelQueueSignal, { global: { stubs } }).find("[data-channel-signal]").exists()).toBe(false);
  });

  it("uma linha por canal de venda, cada uma levando ao card do canal", () => {
    attention.value = projection({
      count: 3, label: "2 desligados · 1 divergente",
      queue: [
        item("web", "sale", "off", "Loja online: pedidos desligados — Loja cheia"),
        item("ifood", "sale", "diverges", "iFood fechado com a loja aberta: nenhum pedido do iFood entra"),
      ],
    });
    const wrapper = mount(ChannelQueueSignal, { global: { stubs } });
    const links = wrapper.findAll("[data-channel-signal-link]");
    expect(links.map((link) => link.text())).toEqual([
      "Loja online: pedidos desligados — Loja cheia",
      "iFood fechado com a loja aberta: nenhum pedido do iFood entra",
    ]);
    expect(links.map((link) => link.attributes("data-to"))).toEqual(["/feeds?focus=web", "/feeds?focus=ifood"]);
  });

  it("quem não abre a aba Canais lê, sem link", () => {
    attention.value = projection({ can_open_channels: false, queue: [item("web", "sale", "paused", "Loja online: pedidos pausados até hoje às 10h30")] });
    const wrapper = mount(ChannelQueueSignal, { global: { stubs } });
    expect(wrapper.find("[data-channel-signal-link]").exists()).toBe(false);
    expect(wrapper.get("[data-channel-signal]").text()).toBe("Loja online: pedidos pausados até hoje às 10h30");
  });

  it("a fila monta o aviso de canal, não mais o do iFood sozinho", () => {
    const page = readFileSync(resolve(__dirname, "../../app/pages/index.vue"), "utf8");
    expect(page).toContain("<ChannelQueueSignal />");
    expect(page).not.toContain("IFoodQueueSignal");
  });
});

describe("indicador no item Canais da navegação", () => {
  beforeEach(() => { attention.value = projection(); });

  it("estado normal: nada ao lado de Canais", () => {
    expect(mount(GestorTopBar, { global: { stubs: { ...stubs, OperatorAppBar: appBarStub } } }).find("[data-channels-attention]").exists()).toBe(false);
  });

  it("feed ou canal desligado: ponto âmbar + a contagem", () => {
    attention.value = projection({ count: 2, label: "2 desligados", items: [item("tv-1", "display", "off", "x"), item("web", "sale", "off", "y")] });
    expect(mount(GestorTopBar, { global: { stubs: { ...stubs, OperatorAppBar: appBarStub } } }).get("[data-channels-attention]").text()).toBe("2 desligados");
  });
});
