import { mockNuxtImport, mountSuspended } from "@nuxt/test-utils/runtime";
import { flushPromises, type VueWrapper } from "@vue/test-utils";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OperatorLogin from "../../app/components/OperatorLogin.vue";

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
    const inputs = wrapper.findAll("input");

    expect(document.activeElement).toBe(inputs[0]!.element);
    expect(inputs[0]!.attributes()).toMatchObject({
      type: "text",
      autocomplete: "username",
      "aria-label": "Usuário",
    });
    expect(inputs[1]!.attributes()).toMatchObject({
      type: "password",
      autocomplete: "current-password",
      "aria-label": "Senha",
    });
    expect(inputs[0]!.classes()).toContain("h-11");
    expect(wrapper.get('button[type="submit"]').attributes("disabled")).toBe(
      "",
    );
  });

  it("submete uma vez, apara só o usuário e anuncia sucesso", async () => {
    let resolve!: (value: unknown) => void;
    fetchMock.mockImplementationOnce(
      () => new Promise((done) => (resolve = done)),
    );
    const wrapper = await mountLogin({ loginUrl: "/login/custom" });
    const [username, password] = wrapper.findAll("input");
    await username!.setValue("  ana  ");
    await password!.setValue(" senha com espaço ");

    await wrapper.get("form").trigger("submit");
    await wrapper.get("form").trigger("submit");

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith("/login/custom", {
      method: "POST",
      credentials: "same-origin",
      body: { username: "ana", password: " senha com espaço " },
    });
    expect(wrapper.get('button[type="submit"]').text()).toBe("Entrando…");
    expect(wrapper.get('button[type="submit"]').attributes("disabled")).toBe(
      "",
    );

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
    const [username, password] = wrapper.findAll("input");
    await username!.setValue("ana");
    await password!.setValue("errada");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get('[role="alert"]').text()).toBe(
      "Usuário ou senha inválidos.",
    );
    expect(
      wrapper.get('button[type="submit"]').attributes("disabled"),
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
    expect(wrapper.get("input").classes()).toContain("h-12");
    expect(wrapper.get('button[type="submit"]').classes()).toContain("h-14");
    expect(wrapper.get("form").classes()).not.toContain("bg-card");
    expect(wrapper.getComponent({ name: "Icon" }).attributes("name")).toBe(
      "lucide:lock-keyhole",
    );
  });
});
