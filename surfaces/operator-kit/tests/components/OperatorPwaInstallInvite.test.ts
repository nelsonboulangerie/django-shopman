import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import type { VueWrapper } from "@vue/test-utils";
import { nextTick } from "vue";
import OperatorPwaInstallInvite from "../../app/components/OperatorPwaInstallInvite.vue";
import { OPERATOR_APPS } from "../../appIdentity";
import { installPlan, type InstallPlan } from "../../app/utils/installGuide";

const POS = OPERATOR_APPS.pos;

const IPHONE_SAFARI =
  "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1";

const NONE: InstallPlan = {
  kind: "none",
  invite: false,
  steps: [],
  os: "unknown",
  browser: "unknown",
};
const PROMPT: InstallPlan = {
  kind: "prompt",
  invite: true,
  steps: [],
  os: "android",
  browser: "chrome",
};

const state = vi.hoisted(() => ({
  plan: undefined as unknown as { value: InstallPlan },
  canInvite: undefined as unknown as { value: boolean },
  install: vi.fn(),
  dismiss: vi.fn(),
  dismissAsDone: vi.fn(),
}));

const session = vi.hoisted(() => ({
  value: { operator: { id: 1, username: "bia", name: "Bia" }, locked: false, authorized: true } as unknown,
}));
mockNuxtImport("useNuxtData", () => () => ({ data: session }));
const INSIDE = { operator: { id: 1, username: "bia", name: "Bia" }, locked: false, authorized: true };

const mounted: VueWrapper[] = [];

async function mountInvite(
  app = "pos",
  identity: (typeof OPERATOR_APPS)[keyof typeof OPERATOR_APPS] = POS,
) {
  const wrapper = await mountSuspended(OperatorPwaInstallInvite, {
    props: { app, identity },
    attachTo: document.body,
  });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

function bodyButton(label: string): HTMLButtonElement {
  const button = [
    ...document.body.querySelectorAll<HTMLButtonElement>("button"),
  ].find((candidate) => candidate.textContent?.trim() === label);
  if (!button) throw new Error(`Botão ${label} não encontrado`);
  return button;
}

vi.mock("../../app/composables/usePwaInstall", async () => {
  const { ref } = await import("vue");
  // Literal aqui dentro: a fábrica é içada para o topo do arquivo e não enxerga
  // constante declarada depois dela.
  state.plan = ref({
    kind: "none",
    invite: false,
    steps: [],
    os: "unknown",
    browser: "unknown",
  });
  state.canInvite = ref(false);
  return { usePwaInstall: () => state };
});

describe("OperatorPwaInstallInvite", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    state.plan.value = NONE;
    state.canInvite.value = false;
    state.install.mockReset().mockResolvedValue(true);
    state.dismiss.mockReset();
    state.dismissAsDone.mockReset();
    session.value = INSIDE;
  });

  afterEach(() => {
    for (const wrapper of mounted.splice(0)) wrapper.unmount();
    document.body.innerHTML = "";
  });

  // Beta 05/11 (CEN-15): o convite cobria o login antes de alguém entrar.
  it("não aparece no login, na trava nem no acesso negado: só dentro do app", async () => {
    state.plan.value = PROMPT;
    state.canInvite.value = true;
    for (const fora of [
      null,
      { operator: null, locked: true, authorized: false },
      { ...INSIDE, locked: true },
      { ...INSIDE, authorized: false },
    ]) {
      session.value = fora;
      await mountInvite();
      expect(document.body.querySelector("[data-operator-pwa-install]")).toBeNull();
      for (const wrapper of mounted.splice(0)) wrapper.unmount();
      document.body.innerHTML = "";
    }

    session.value = INSIDE;
    await mountInvite();
    expect(document.body.querySelector("[data-operator-pwa-install]")).not.toBeNull();
  });

  it("espera a oferta de vincular o dispositivo sair da tela (PDV2-25)", async () => {
    state.plan.value = PROMPT;
    state.canInvite.value = true;
    const offerOpen = useState<boolean>("station-setup-offer-open", () => false);
    offerOpen.value = true;
    await mountInvite();
    expect(document.body.querySelector("[data-operator-pwa-install]")).toBeNull();
    offerOpen.value = false;
    await nextTick();
    await nextTick();
    expect(document.body.querySelector("[data-operator-pwa-install]")).not.toBeNull();
  });

  it("fica ausente quando não há caminho acionável aqui", async () => {
    await mountInvite();
    expect(
      document.body.querySelector("[data-operator-pwa-install]"),
    ).toBeNull();
  });

  it("ensina o gesto DESTE navegador, sem prometer instalação automática", async () => {
    state.plan.value = installPlan({
      userAgent: IPHONE_SAFARI,
      canPrompt: false,
    });
    state.canInvite.value = true;
    await mountInvite();

    expect(
      document.body.querySelector("[data-operator-install-steps]"),
    ).not.toBeNull();
    expect(document.body.textContent).toContain("Compartilhar");
    expect(document.body.textContent).toContain("Adicionar à Tela de Início");
    expect(document.body.textContent).toContain(
      `Acesse ${POS.article} ${POS.label} direto da tela inicial do seu dispositivo.`,
    );
    expect(document.body.textContent).not.toContain("Instalar");
  });

  it("chama o app pelo nome, numa frase só", async () => {
    // Os oito diziam "Instale Shopman": a marca no lugar do app. O título é a mensagem
    // inteira (dono, 14/11), sem parágrafo de apoio.
    state.plan.value = PROMPT;
    state.canInvite.value = true;
    await mountInvite();
    expect(document.body.textContent).toContain(
      `Acesse ${POS.article} ${POS.label} direto da tela inicial do seu dispositivo.`,
    );
    expect(document.body.textContent).not.toContain("Shopman");

    for (const wrapper of mounted.splice(0)) wrapper.unmount();
    document.body.innerHTML = "";
    await mountInvite("kds", OPERATOR_APPS.kds);
    expect(document.body.textContent).toContain("Acesse a Cozinha direto da tela inicial");
    expect(document.body.textContent).not.toContain("caixa");
  });

  it("só chama o prompt do navegador após clique", async () => {
    state.plan.value = PROMPT;
    state.canInvite.value = true;
    await mountInvite();
    expect(state.install).not.toHaveBeenCalled();
    bodyButton("Instalar").click();
    expect(state.install).toHaveBeenCalledOnce();
    await vi.waitFor(() => expect(state.dismissAsDone).toHaveBeenCalledOnce());
  });

  it("no caminho manual, 'já instalei' encerra de vez e 'agora não' só adia", async () => {
    state.plan.value = installPlan({
      userAgent: IPHONE_SAFARI,
      canPrompt: false,
    });
    state.canInvite.value = true;
    await mountInvite();

    bodyButton("Já instalei").click();
    expect(state.dismissAsDone).toHaveBeenCalledOnce();
    expect(state.install).not.toHaveBeenCalled();

    bodyButton("Agora não").click();
    expect(state.dismiss).toHaveBeenCalledOnce();
  });
});
