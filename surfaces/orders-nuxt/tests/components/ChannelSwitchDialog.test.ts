import { beforeEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, ref, watch } from "vue";
import { flushPromises, mount } from "@vue/test-utils";

import ChannelSwitchDialog from "../../app/components/ChannelSwitchDialog.vue";
import type { ChannelSwitchProjection } from "../../app/types/feeds";

for (const [key, value] of Object.entries({ computed, ref, watch })) vi.stubGlobal(key, value);

const passthrough = { template: "<div><slot /></div>" };
const managerAuth = defineComponent({
  props: ["open", "action", "managers", "error", "operatorName"],
  emits: ["authorize", "authorizeBadge", "update:open"],
  template: `<div v-if="open" data-manager-auth :data-action="action" :data-error="error">
    <button data-sign @click="$emit('authorize', 'ana', '4321')">Assinar</button>
  </div>`,
});
const stubs = {
  Icon: true,
  UiDialog: { props: ["open"], template: "<div v-if='open' data-dialog><slot /></div>" },
  UiDialogContent: passthrough, UiDialogHeader: passthrough, UiDialogTitle: passthrough,
  UiDialogDescription: passthrough, UiDialogFooter: passthrough,
  ChannelPeriodCalendar: { template: "<div data-calendar-stub />" },
  OperatorManagerAuth: managerAuth,
};

function sw(over: Partial<ChannelSwitchProjection> = {}): ChannelSwitchProjection {
  return {
    is_active: true, state_line: "", closed_by_shop: "", scheduled_line: "",
    title: "Desligar iFood", consequence: "A loja fecha no iFood.",
    periods: [
      { key: "30m", label: "Por 30 minutos", enabled: true, reason: "" },
      { key: "open", label: "Sem prazo (até alguém religar)", enabled: true, reason: "" },
      { key: "custom", label: "Escolher período…", enabled: true, reason: "" },
    ],
    reasons: ["Loja cheia", "Férias"], reason_required: true, enabled: true, disabled_reason: "",
    base_revision: "rev", expected_actor_id: 1, requires_manager_approval: false,
    ...over,
  };
}

const submit = vi.fn();
function render(props: Partial<{ sw: ChannelSwitchProjection }> = {}) {
  return mount(ChannelSwitchDialog, {
    props: { open: true, sw: sw(), managers: [{ username: "ana", name: "Ana" }], viewerName: "Joyce", busy: false, submit, ...props },
    global: { stubs },
  });
}

async function choose(wrapper: ReturnType<typeof render>, period: string, reason?: string) {
  await wrapper.get(`[data-period="${period}"] input`).setValue(true);
  if (reason) await wrapper.findAll("button").find((b) => b.text() === reason)!.trigger("click");
}

describe("ChannelSwitchDialog — um modal só: período, motivo e gerente", () => {
  beforeEach(() => {
    submit.mockReset();
    submit.mockResolvedValue({ ok: true, code: "", message: "" });
  });

  it("não confirma sem período e motivo", async () => {
    const wrapper = render();
    expect(wrapper.get("[data-switch-confirm]").attributes("disabled")).toBeDefined();
    expect(wrapper.get("[data-switch-missing]").text()).toBe("Escolha por quanto tempo.");
    await choose(wrapper, "30m");
    expect(wrapper.get("[data-switch-missing]").text()).toBe("Escolha ou escreva o motivo.");
  });

  it("gerente logado só confirma: o pedido sai sem assinatura", async () => {
    const wrapper = render();
    await choose(wrapper, "30m", "Loja cheia");
    await wrapper.get("[data-switch-confirm]").trigger("click");
    await flushPromises();
    expect(submit).toHaveBeenCalledWith({ is_active: false, period: "30m", reason: "Loja cheia" }, undefined);
    expect(wrapper.emitted("update:open")?.at(-1)).toEqual([false]);
    expect(wrapper.find("[data-manager-auth]").exists()).toBe(false);
  });

  it("quem não é gerente chama um: o diálogo do PDV sobe, e a assinatura vai junto", async () => {
    const wrapper = render({ sw: sw({ requires_manager_approval: true }) });
    await choose(wrapper, "open", "Férias");
    await wrapper.get("[data-switch-confirm]").trigger("click");
    const auth = wrapper.get("[data-manager-auth]");
    expect(auth.attributes("data-action")).toBe("channel_off");
    expect(submit).not.toHaveBeenCalled();
    await wrapper.get("[data-sign]").trigger("click");
    await flushPromises();
    expect(submit).toHaveBeenCalledWith({ is_active: false, period: "open", reason: "Férias" }, { username: "ana", pin: "4321" });
  });

  it("PIN errado fica no diálogo do gerente, com a frase do servidor", async () => {
    submit.mockResolvedValueOnce({ ok: false, code: "manager_approval_invalid", message: "Aprovação gerencial inválida." });
    const wrapper = render({ sw: sw({ requires_manager_approval: true }) });
    await choose(wrapper, "open", "Férias");
    await wrapper.get("[data-switch-confirm]").trigger("click");
    await wrapper.get("[data-sign]").trigger("click");
    await flushPromises();
    expect(wrapper.get("[data-manager-auth]").attributes("data-error")).toBe("Aprovação gerencial inválida.");
    expect(wrapper.emitted("update:open")).toBeUndefined();
  });

  it("ligar não pede motivo e lembra que o horário da loja manda", async () => {
    const wrapper = render({ sw: sw({ is_active: false, reason_required: false, reasons: [], title: "Ligar iFood" }) });
    expect(wrapper.get("[data-switch-shop-hours]").text()).toBe("Ligado, o canal só recebe pedidos dentro do horário da loja.");
    await choose(wrapper, "open");
    expect(wrapper.get("[data-switch-confirm]").text()).toBe("Ligar");
    expect(wrapper.get("[data-switch-confirm]").attributes("disabled")).toBeUndefined();
  });

  it("escolher período abre o calendário", async () => {
    const wrapper = render();
    expect(wrapper.find("[data-calendar-stub]").exists()).toBe(false);
    await choose(wrapper, "custom");
    expect(wrapper.find("[data-calendar-stub]").exists()).toBe(true);
  });
});
