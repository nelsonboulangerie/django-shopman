import { flushPromises, mount } from "@vue/test-utils";
import { computed, nextTick, onMounted, ref } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import OperatorLogin from "~/components/OperatorLogin.vue";

const fetcher = vi.fn();
const refreshNuxtData = vi.fn();
const reset = vi.fn();

beforeEach(() => {
  fetcher.mockReset().mockResolvedValue({ ok: true });
  refreshNuxtData.mockReset().mockResolvedValue(undefined);
  reset.mockReset();
  Object.assign(globalThis, {
    $fetch: fetcher,
    computed,
    httpErrorMessage: (_error: unknown, fallback: string) => fallback,
    nextTick,
    onMounted,
    ref,
    refreshNuxtData,
    useOperatorSession: () => ({ reset }),
  });
});

function mountLogin(expired = false) {
  return mount(OperatorLogin, {
    props: { expired },
    attachTo: document.body,
    global: { stubs: { Icon: true } },
  });
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("OperatorLogin", () => {
  it("starts on the username and keeps keyboard focus inside the dialog", async () => {
    const wrapper = mountLogin();
    await nextTick();
    const username = wrapper.get<HTMLInputElement>("#operator-login-username");
    const password = wrapper.get<HTMLInputElement>("#operator-login-password");

    expect(document.activeElement).toBe(username.element);
    await username.setValue("gestora");
    await password.setValue("segredo");
    await nextTick();

    const submit = wrapper.get<HTMLButtonElement>('button[type="submit"]');
    submit.element.focus();
    await submit.trigger("keydown", { key: "Tab" });
    expect(document.activeElement).toBe(username.element);

    username.element.focus();
    await username.trigger("keydown", { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(submit.element);
  });

  it("explains expiry and preserves the SPA while reconciling before unlock", async () => {
    const wrapper = mountLogin(true);
    expect(wrapper.text()).toContain("Sua sessão terminou");
    expect(wrapper.text()).toContain("rascunho");
    expect(wrapper.attributes("class")).not.toContain("backdrop");

    await wrapper.find('input[type="text"]').setValue("gestora");
    await wrapper.find('input[type="password"]').setValue("segredo");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(fetcher).toHaveBeenCalledWith("/api/v1/backstage/operator/login/", {
      method: "POST",
      credentials: "same-origin",
      body: { username: "gestora", password: "segredo" },
    });
    expect(refreshNuxtData).toHaveBeenCalledWith("operator-session");
    expect(reset).toHaveBeenCalledOnce();
    expect(refreshNuxtData.mock.invocationCallOrder[0]).toBeLessThan(
      reset.mock.invocationCallOrder[0]!,
    );
  });

  it("associates a failed login with both fields without losing the form", async () => {
    fetcher.mockRejectedValueOnce(new Error("unauthorized"));
    const wrapper = mountLogin();
    await wrapper.get("#operator-login-username").setValue("gestora");
    await wrapper.get("#operator-login-password").setValue("incorreta");
    await wrapper.get("form").trigger("submit");
    await flushPromises();

    expect(wrapper.get("#operator-login-error").attributes("role")).toBe(
      "alert",
    );
    expect(
      wrapper.get("#operator-login-username").attributes("aria-describedby"),
    ).toContain("operator-login-error");
    expect(
      wrapper.get("#operator-login-password").attributes("aria-invalid"),
    ).toBe("true");
  });
});
