import { beforeEach, describe, expect, it, vi } from "vitest";
import { mountSuspended } from "@nuxt/test-utils/runtime";
import OperatorPwaInstallInvite from "../../app/components/OperatorPwaInstallInvite.vue";
import { OPERATOR_APPS } from "../../appIdentity";
import { installPlan, type InstallPlan } from "../../app/utils/installGuide";

const POS = OPERATOR_APPS.pos;

const IPHONE_SAFARI =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1";

const NONE: InstallPlan = { kind: "none", invite: false, steps: [], os: "unknown", browser: "unknown" };
const PROMPT: InstallPlan = { kind: "prompt", invite: true, steps: [], os: "android", browser: "chrome" };

const state = vi.hoisted(() => ({
  plan: undefined as unknown as { value: InstallPlan },
  canInvite: undefined as unknown as { value: boolean },
  install: vi.fn(),
  dismiss: vi.fn(),
  dismissAsDone: vi.fn(),
}));

vi.mock("../../app/composables/usePwaInstall", async () => {
  const { ref } = await import("vue");
  // Literal aqui dentro: a fábrica é içada para o topo do arquivo e não enxerga
  // constante declarada depois dela.
  state.plan = ref({ kind: "none", invite: false, steps: [], os: "unknown", browser: "unknown" });
  state.canInvite = ref(false);
  return { usePwaInstall: () => state };
});

describe("OperatorPwaInstallInvite", () => {
  beforeEach(() => {
    state.plan.value = NONE;
    state.canInvite.value = false;
    state.install.mockReset().mockResolvedValue(true);
    state.dismiss.mockReset();
    state.dismissAsDone.mockReset();
  });

  it("fica ausente quando não há caminho acionável aqui", async () => {
    const wrapper = await mountSuspended(OperatorPwaInstallInvite, { props: { app: "pos", identity: POS } });
    expect(wrapper.find("[data-operator-pwa-install]").exists()).toBe(false);
  });

  it("ensina o gesto DESTE navegador, sem prometer instalação automática", async () => {
    state.plan.value = installPlan({ userAgent: IPHONE_SAFARI, canPrompt: false });
    state.canInvite.value = true;
    const wrapper = await mountSuspended(OperatorPwaInstallInvite, { props: { app: "pos", identity: POS } });

    expect(wrapper.find("[data-operator-install-steps]").exists()).toBe(true);
    expect(wrapper.text()).toContain("Compartilhar");
    expect(wrapper.text()).toContain("Adicionar à Tela de Início");
    expect(wrapper.text()).toContain(`Coloque ${POS.article} ${POS.label} na tela inicial`);
    expect(wrapper.text()).not.toContain("Instalar");
  });

  it("chama o app pelo nome e diz o que ELE passa a fazer", async () => {
    // Os oito diziam "Instale Shopman" e "Abra o caixa direto da tela inicial" — marca
    // no lugar do app, e a copy do balcão no B.I., na Cozinha e no Marketing.
    state.plan.value = PROMPT;
    state.canInvite.value = true;
    const wrapper = await mountSuspended(OperatorPwaInstallInvite, { props: { app: "pos", identity: POS } });
    expect(wrapper.text()).toContain(`Instale ${POS.article} ${POS.label}`);
    expect(wrapper.text()).toContain(POS.install);
    expect(wrapper.text()).not.toContain("Shopman");

    const kds = await mountSuspended(OperatorPwaInstallInvite, {
      props: { app: "kds", identity: OPERATOR_APPS.kds },
    });
    expect(kds.text()).toContain("Instale a Cozinha");
    expect(kds.text()).not.toContain("caixa");
  });

  it("só chama o prompt do navegador após clique", async () => {
    state.plan.value = PROMPT;
    state.canInvite.value = true;
    const wrapper = await mountSuspended(OperatorPwaInstallInvite, { props: { app: "pos", identity: POS } });
    expect(state.install).not.toHaveBeenCalled();
    await wrapper.get("button.bg-primary").trigger("click");
    expect(state.install).toHaveBeenCalledOnce();
    await vi.waitFor(() => expect(state.dismissAsDone).toHaveBeenCalledOnce());
  });

  it("no caminho manual, 'já instalei' encerra de vez e 'agora não' só adia", async () => {
    state.plan.value = installPlan({ userAgent: IPHONE_SAFARI, canPrompt: false });
    state.canInvite.value = true;
    const wrapper = await mountSuspended(OperatorPwaInstallInvite, { props: { app: "pos", identity: POS } });

    await wrapper.get("button.bg-primary").trigger("click");
    expect(state.dismissAsDone).toHaveBeenCalledOnce();
    expect(state.install).not.toHaveBeenCalled();

    await wrapper.get("button.text-muted-foreground").trigger("click");
    expect(state.dismiss).toHaveBeenCalledOnce();
  });
});
