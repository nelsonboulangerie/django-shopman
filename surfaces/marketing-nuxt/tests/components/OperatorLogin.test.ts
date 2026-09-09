import { flushPromises, mount } from "@vue/test-utils";
import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
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
    httpErrorMessage: (_error: unknown, fallback: string) => fallback,
    ref,
    refreshNuxtData,
    useOperatorSession: () => ({ reset }),
  });
});

function mountLogin(expired = false) {
  return mount(OperatorLogin, {
    props: { expired },
    global: { stubs: { Icon: true } },
  });
}

describe("OperatorLogin", () => {
  it("explains expiry and preserves the SPA while reconciling before unlock", async () => {
    const wrapper = mountLogin(true);
    expect(wrapper.text()).toContain("Sua sessão terminou");
    expect(wrapper.text()).toContain("rascunho");
    expect(wrapper.attributes("class")).not.toContain("backdrop");

    await wrapper.find('input[type="text"]').setValue("gestora");
    await wrapper.find('input[type="password"]').setValue("segredo");
    await wrapper.find("form").trigger("submit");
    await flushPromises();

    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/backstage/operator/login/",
      {
        method: "POST",
        credentials: "same-origin",
        body: { username: "gestora", password: "segredo" },
      },
    );
    expect(refreshNuxtData).toHaveBeenCalledWith("operator-session");
    expect(reset).toHaveBeenCalledOnce();
    expect(refreshNuxtData.mock.invocationCallOrder[0]).toBeLessThan(
      reset.mock.invocationCallOrder[0]!,
    );
  });
});
