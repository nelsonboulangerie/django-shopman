import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OperatorLogin from "../../app/components/OperatorLogin.vue";
import OperatorLoginForm from "../../app/components/OperatorLoginForm.vue";

const { fetchMock, refreshSession, resetSession } = vi.hoisted(() => ({
  fetchMock: vi.fn(),
  refreshSession: vi.fn(),
  resetSession: vi.fn(),
}));

mockNuxtImport("$fetch", () => fetchMock);
mockNuxtImport("refreshNuxtData", () => refreshSession);
mockNuxtImport("useOperatorSession", () => () => ({ reset: resetSession }));

const mounted: VueWrapper[] = [];

async function mountLogin(props: Record<string, unknown> = {}) {
  const wrapper = await mountSuspended(OperatorLogin, {
    props: { reloadOnSuccess: false, ...props },
    attachTo: document.body,
    global: { stubs: { Icon: true } },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

beforeEach(() => {
  fetchMock.mockReset();
  refreshSession.mockReset().mockResolvedValue(undefined);
  resetSession.mockReset();
});

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  document.body.innerHTML = "";
});

describe("OperatorLogin", () => {
  it("abre com foco em Usuário, campos acessíveis e submit bloqueado", async () => {
    const wrapper = await mountLogin();
    const form = wrapper.getComponent(OperatorLoginForm);
    const inputs = form.findAll("input");

    expect(document.activeElement).toBe(inputs[0]!.element);
    expect(inputs[0]!.attributes()).toMatchObject({
      type: "text",
      autocomplete: "username",
    });
    expect(form.get('label[for="operator-login-username"]').text()).toBe(
      "Usuário",
    );
    expect(inputs[1]!.attributes()).toMatchObject({
      type: "password",
      autocomplete: "current-password",
    });
    expect(form.get('label[for="operator-login-password"]').text()).toBe(
      "Senha",
    );
    expect(form.get('button[type="submit"]').attributes("disabled")).toBe("");
  });

  it("submete uma vez, apara só o usuário e anuncia sucesso", async () => {
    let resolve!: (value: unknown) => void;
    fetchMock.mockImplementationOnce(
      () => new Promise((done) => (resolve = done)),
    );
    const wrapper = await mountLogin({ loginUrl: "/login/custom" });
    const form = wrapper.getComponent(OperatorLoginForm);
    const [username, password] = form.findAll("input");
    await username!.setValue("  ana  ");
    await password!.setValue(" senha com espaço ");

    await form.get("form").trigger("submit");
    await form.get("form").trigger("submit");

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith("/login/custom", {
      method: "POST",
      credentials: "same-origin",
      body: { username: "ana", password: " senha com espaço " },
    });
    expect(form.get('button[type="submit"]').text()).toBe("Entrando…");
    expect(form.get('button[type="submit"]').attributes("disabled")).toBe("");

    resolve({ ok: true });
    await flushPromises();

    expect(refreshSession).toHaveBeenCalledWith("operator-session");
    expect(resetSession).toHaveBeenCalledOnce();
    expect(wrapper.emitted("success")).toHaveLength(1);
  });

  it("mostra a mensagem do servidor e libera nova tentativa", async () => {
    fetchMock.mockRejectedValueOnce({
      status: 403,
      data: { detail: "Usuário ou senha inválidos." },
    });
    const wrapper = await mountLogin();
    const form = wrapper.getComponent(OperatorLoginForm);
    const [username, password] = form.findAll("input");
    await username!.setValue("ana");
    await password!.setValue("errada");
    await form.get("form").trigger("submit");
    await flushPromises();

    expect(form.get("[data-operator-login-error]").text()).toBe(
      "Usuário ou senha inválidos.",
    );
    expect(
      form.get('button[type="submit"]').attributes("disabled"),
    ).toBeUndefined();
    expect(resetSession).not.toHaveBeenCalled();
    expect(wrapper.emitted("success")).toBeUndefined();
  });

  it("preserva a variante page/touch e a cópia específica do app", async () => {
    const wrapper = await mountLogin({
      mode: "page",
      largeFields: true,
      title: "Entre para operar o caixa",
      description: "Acesse com sua conta autorizada a operar o caixa.",
      icon: "lucide:lock-keyhole",
    });

    expect(wrapper.text()).toContain("Entre para operar o caixa");
    expect(wrapper.text()).toContain(
      "Acesse com sua conta autorizada a operar o caixa.",
    );
    expect(wrapper.findAll("input")).toHaveLength(2);
    expect(wrapper.get(".iconify").classes()).toContain(
      "i-lucide:lock-keyhole",
    );
  });

  // Identidade do app no gate: o PNG da família PWA, com ícone canônico quando
  // a identidade não fornece imagem.
  it("com iconSrc mostra o PNG do app e sem imagem usa o Lucide", async () => {
    const wrapper = await mountLogin({
      icon: "lucide:layout-grid",
      iconSrc: "/pwa/pwa-64x64.png?v=3",
    });
    const img = wrapper.getComponent(OperatorLoginForm).get("img");
    expect(img.attributes("src")).toBe("/pwa/pwa-64x64.png?v=3");
    expect(img.attributes("alt") ?? "").toBe("");
    wrapper.unmount();
    const fallback = await mountLogin({
      icon: "lucide:layout-grid",
      iconSrc: "",
    });
    expect(
      fallback
        .getComponent(OperatorLoginForm)
        .findAll(".iconify")
        .some((node) => node.classes().includes("i-lucide:layout-grid")),
    ).toBe(true);
  });
});
