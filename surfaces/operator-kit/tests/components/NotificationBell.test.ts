// O sino da caixa pessoal.
//
// Os dois testes que importam aqui não são de renderização: são as promessas que
// o dono cobrou. (1) NÃO INTERROMPE — nada aparece por cima de quem está
// atendendo até alguém clicar. (2) REALCE, NUNCA SILO — o suspeito fica na mesma
// lista, marcado, e não numa aba que esconde o resto.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ref } from "vue";

import NotificationBell from "../../app/components/NotificationBell.vue";

const ROTINA = {
  pk: 1,
  category: "sign_in" as const,
  title: "Sua conta foi usada (PIN)",
  message: "29/08 às 09:12 · pdv-main",
  action_url: "/account/sign-ins",
  action_data: { sign_in_event_id: 1, anomalies: [], highlight: false },
  is_actionable: true,
  is_read: false,
  created_at: "2026-08-29T09:12:00Z",
  created_at_display: "29/08 às 09:12",
};

const SUSPEITO = {
  ...ROTINA,
  pk: 2,
  title: "Sua conta foi usada (crachá)",
  message: "29/08 às 03:40 · pdv-main\nAtenção: entrou com crachá.",
  action_data: { sign_in_event_id: 2, anomalies: ["badge"], highlight: true },
};

const items = ref<unknown[]>([]);
const unread = ref(0);
const signIns = ref<unknown[]>([]);
const markRead = vi.fn();
const loadSignIns = vi.fn();

vi.mock("../../app/composables/useNotifications", () => ({
  useNotifications: () => ({
    items,
    unread,
    loading: ref(false),
    refresh: vi.fn(),
    markRead,
    signIns,
    loadSignIns,
    realtime: ref("live"),
  }),
}));

let mounted: Awaited<ReturnType<typeof mountSuspended>> | null = null;
const mount = async () =>
  (mounted = await mountSuspended(NotificationBell, {
    global: { stubs: { Icon: true } },
  }));

describe("NotificationBell", () => {
  beforeEach(() => {
    items.value = [];
    unread.value = 0;
    signIns.value = [];
    markRead.mockReset();
    loadSignIns.mockReset();
  });

  afterEach(() => {
    mounted?.unmount();
    mounted = null;
  });

  it("NÃO interrompe: nada de painel aberto sem alguém pedir", async () => {
    items.value = [SUSPEITO];
    unread.value = 1;
    const wrapper = await mount();

    // Mesmo com aviso destacado por ler, a tela do operador segue livre.
    expect(wrapper.find("[data-notification-panel]").exists()).toBe(false);
  });

  it("o contador é discreto e some quando não há nada", async () => {
    const wrapper = await mount();
    expect(wrapper.find("[data-notification-count]").exists()).toBe(false);

    unread.value = 3;
    await wrapper.vm.$nextTick();
    expect(wrapper.find("[data-notification-count]").text()).toBe("3");
  });

  it("REALCE, NUNCA SILO: rotina e suspeito na MESMA lista", async () => {
    items.value = [ROTINA, SUSPEITO];
    unread.value = 2;
    const wrapper = await mount();
    await wrapper.find("button").trigger("click");

    const linhas = wrapper.findAll("[data-notification-item]");
    expect(linhas).toHaveLength(2);
    // Nada foi escondido; o que muda é a marca.
    expect(linhas[0]!.attributes("data-highlight")).toBeUndefined();
    expect(linhas[1]!.attributes("data-highlight")).toBe("true");
  });

  it("o suspeito mostra o motivo, não só uma cor", async () => {
    items.value = [SUSPEITO];
    const wrapper = await mount();
    await wrapper.find("button").trigger("click");

    expect(wrapper.text()).toContain("entrou com crachá");
  });

  it("caixa vazia diz que está vazia", async () => {
    const wrapper = await mount();
    await wrapper.find("button").trigger("click");

    expect(wrapper.text()).toContain("Nada por aqui");
  });

  it("marcar como lida não navega para lugar nenhum", async () => {
    items.value = [ROTINA];
    const wrapper = await mount();
    await wrapper.find("button").trigger("click");
    await wrapper.findAll("button").find((b) => b.text() === "Marcar como lida")!.trigger("click");

    expect(markRead).toHaveBeenCalledWith(1);
  });

  it("'Meus acessos' abre o log no MESMO painel — não manda para outro domínio", async () => {
    items.value = [ROTINA];
    signIns.value = [
      {
        pk: 9,
        method: "badge",
        method_display: "crachá",
        outcome: "success",
        outcome_display: "entrou",
        station_ref: "pdv-main",
        station_display: "pdv-main",
        ip_address: "",
        created_at: "",
        created_at_display: "29/08 às 06:12",
        anomalies: ["badge"],
        anomaly_labels: ["entrou com crachá"],
        highlight: true,
      },
    ];
    const wrapper = await mount();
    await wrapper.find("button").trigger("click");
    await wrapper.find("[data-see-sign-ins]").trigger("click");

    expect(loadSignIns).toHaveBeenCalled();
    const linhas = wrapper.findAll("[data-sign-in-item]");
    expect(linhas).toHaveLength(1);
    expect(linhas[0]!.attributes("data-highlight")).toBe("true");
    expect(wrapper.text()).toContain("crachá · pdv-main");
    // Nenhum link para fora: o log da própria conta mora aqui.
    expect(wrapper.findAll("a")).toHaveLength(0);
  });
});
