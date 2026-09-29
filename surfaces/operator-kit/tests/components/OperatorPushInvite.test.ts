import { beforeEach, describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import OperatorPushInvite from "../../app/components/OperatorPushInvite.vue";

const holder = vi.hoisted(() => ({ state: null as any }));
vi.mock("../../app/composables/useWebPush", async () => {
  const { ref } = await import("vue");
  holder.state = {
    supported: ref(true),
    active: ref(false),
    permission: ref("default"),
    loading: ref(false),
    activate: vi.fn(),
  };
  return { useWebPush: () => holder.state };
});

describe("OperatorPushInvite", () => {
  beforeEach(() => {
    holder.state.supported.value = true;
    holder.state.active.value = false;
    holder.state.permission.value = "default";
    holder.state.loading.value = false;
    holder.state.activate.mockReset().mockResolvedValue(true);
  });

  it("não convida nem pede permissão quando o ambiente está sem VAPID", async () => {
    holder.state.supported.value = false;
    const wrapper = await mountSuspended(OperatorPushInvite);
    expect(wrapper.find("[data-operator-push-invite]").exists()).toBe(false);
    expect(holder.state.activate).not.toHaveBeenCalled();
  });

  it("ambiente apto só ativa depois do toque", async () => {
    const wrapper = await mountSuspended(OperatorPushInvite);
    expect(holder.state.activate).not.toHaveBeenCalled();
    await wrapper.get("button").trigger("click");
    expect(holder.state.activate).toHaveBeenCalledOnce();
  });

  // ⚠️ O convite dizia "os avisos DESTA ÁREA" nos seis apps que o montam, e "esta
  // área" não está escrita em lugar nenhum da tela: quem toca não sabe se está
  // ligando os avisos da Cozinha, do PDV ou de todos. O nome sai da identidade
  // canônica, com o artigo contraído — "do PDV", "da Cozinha", "das Compras".
  it.each([
    [{ label: "PDV", article: "o" }, "do PDV"],
    [{ label: "Cozinha", article: "a" }, "da Cozinha"],
    [{ label: "Compras", article: "as" }, "das Compras"],
  ])("nomeia o app no lugar de 'esta área' (%o)", async (identity, expected) => {
    const wrapper = await mountSuspended(OperatorPushInvite, { props: { identity } });
    expect(wrapper.text()).toContain(`só os avisos ${expected}.`);
    expect(wrapper.text()).not.toContain("esta área");
  });
});
