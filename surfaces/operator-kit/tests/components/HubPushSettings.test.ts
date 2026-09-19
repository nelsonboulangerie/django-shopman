import { beforeEach, describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import OperatorPushSettings from "../../app/components/OperatorPushSettings.vue";
import { OPERATOR_APPS } from "../../appIdentity";

const holder = vi.hoisted(() => ({ state: null as any }));
vi.mock("../../app/composables/useWebPush", async () => {
  const { ref } = await import("vue");
  holder.state = {
    supported: ref(true), unavailableReason: ref(""), active: ref(false), permission: ref("default"), loading: ref(false), error: ref(""),
    devices: ref([]), categories: ref([{ value: "order", label: "pedidos" }]), currentDevice: ref(null),
    activate: vi.fn(), updateCategories: vi.fn(), removeDevice: vi.fn(),
  };
  return { useWebPush: () => holder.state };
});

describe("HubPushSettings", () => {
  beforeEach(() => {
    const state = holder.state;
    state.active.value = false;
    state.supported.value = true;
    state.unavailableReason.value = "";
    state.permission.value = "default";
    state.devices.value = [];
    state.currentDevice.value = null;
    state.activate.mockReset().mockResolvedValue(true);
    state.updateCategories.mockReset().mockResolvedValue(undefined);
    state.removeDevice.mockReset().mockResolvedValue(undefined);
  });

  it("pede permissão somente depois do toque explícito", async () => {
    const state = holder.state;
    const wrapper = await mountSuspended(OperatorPushSettings);
    expect(state.activate).not.toHaveBeenCalled();
    await wrapper.get("[data-activate-push]").trigger("click");
    expect(state.activate).toHaveBeenCalledOnce();
  });

  // ⚠️ UMA frase cobria duas causas opostas ("Avisos em segundo plano ainda não estão
  // disponíveis neste ambiente"): a instalação sem chave de envio, que só quem cuida do
  // sistema resolve, e o navegador que não entrega aviso com o app fechado, que o
  // operador resolve instalando o app. O operador não tinha como saber qual era a dele.
  it("sem chave de envio: diz que falta configurar e a quem pedir", async () => {
    const state = holder.state;
    state.supported.value = false;
    state.unavailableReason.value = "deploy";
    const wrapper = await mountSuspended(OperatorPushSettings);

    expect(wrapper.find("[data-activate-push]").exists()).toBe(false);
    const text = wrapper.get("[data-push-unavailable='deploy']").text();
    expect(text).toContain("ainda não foi configurado nesta instalação");
    expect(text).toContain("Peça a quem cuida do sistema");
    expect(state.activate).not.toHaveBeenCalled();
  });

  it("navegador sem push: diz o gesto que resolve, com o nome do app", async () => {
    const state = holder.state;
    state.supported.value = false;
    state.unavailableReason.value = "browser";
    const wrapper = await mountSuspended(OperatorPushSettings);

    expect(wrapper.find("[data-activate-push]").exists()).toBe(false);
    const text = wrapper.get("[data-push-unavailable='browser']").text();
    expect(text).toContain("não entrega avisos com o app fechado");
    expect(text).toContain("Tela de Início");
    expect(text).toContain(OPERATOR_APPS.hub.label);
  });

  it("no servidor, sem resposta do navegador ainda, não afirma nenhuma das duas causas", async () => {
    const state = holder.state;
    state.supported.value = false;
    state.unavailableReason.value = "";
    const wrapper = await mountSuspended(OperatorPushSettings);

    expect(wrapper.find("[data-push-unavailable]").exists()).toBe(false);
  });

  it("mostra categorias e permite remover um dispositivo", async () => {
    const state = holder.state;
    const device = { id: 7, endpoint: "https://push.test/7", surface_ref: "hub", device_label: "iPhone", categories: ["order"] };
    state.active.value = true;
    state.devices.value = [device];
    state.currentDevice.value = device;
    const wrapper = await mountSuspended(OperatorPushSettings);

    expect(wrapper.text()).toContain("O que chega aqui");
    expect(wrapper.text()).toContain("iPhone");
    // O `surface_ref` é chave de API; na tela vai o nome do app. E o carimbo da versão
    // do build ("local") saiu daqui: ele não é propriedade do aviso, e colado no título
    // era lido como se fosse. Foi para o rodapé da home, com rótulo.
    expect(wrapper.text()).toContain(OPERATOR_APPS.hub.label);
    expect(wrapper.text()).not.toContain("local");
    // Checkbox da casa (`UiCheckbox`), não o do sistema: é um botão com
    // `role="checkbox"`, e desmarcar é o clique.
    await wrapper.get('[role="checkbox"]').trigger("click");
    expect(state.updateCategories).toHaveBeenCalledWith(device, []);
    await wrapper.get("button.text-xs").trigger("click");
    expect(state.removeDevice).toHaveBeenCalledWith(device);
  });
});
