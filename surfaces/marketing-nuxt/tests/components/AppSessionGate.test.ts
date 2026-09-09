import { mount } from "@vue/test-utils";
import { ref, type Slot } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MarketingApp from "../../app/app.vue";

const lock = vi.fn();
const refreshSession = vi.fn();
let state = "anonymous";
let canIdentify = false;
let unavailable = false;

beforeEach(() => {
  state = "anonymous";
  canIdentify = false;
  unavailable = false;
  Object.assign(globalThis, {
    useHead: vi.fn(),
    useRuntimeConfig: () => ({ public: { operatorHubUrl: "/apps/" } }),
    useOperatorLock: () => ({
      canIdentify: ref(canIdentify),
      sessionState: ref(state),
      sessionUnavailable: ref(unavailable),
      operator: ref(null),
      lock,
      refresh: refreshSession,
    }),
  });
});

function mountApp() {
  const ProtectedPage = {
    template: '<div data-testid="protected-page">protegido</div>',
  };
  return mount(MarketingApp, {
    global: {
      stubs: {
        CampaignTopBar: true,
        Icon: true,
        NuxtPage: {
          setup(_props: unknown, { slots }: { slots: { default?: Slot } }) {
            return () => slots.default?.({ Component: ProtectedPage });
          },
        },
        NuxtRouteAnnouncer: true,
        OfflineBanner: true,
        OperatorLock: true,
        OperatorLogin: true,
        OperatorRail: true,
        UiSonner: true,
      },
    },
  });
}

describe("Marketing app session gate", () => {
  it("does not mount the protected route for an anonymous operator", () => {
    const wrapper = mountApp();

    expect(wrapper.find('[data-testid="protected-page"]').exists()).toBe(false);
    expect(wrapper.findComponent({ name: "OperatorLogin" }).exists()).toBe(
      true,
    );
  });

  it("mounts the protected route only after capability authentication", () => {
    state = "authenticated";
    canIdentify = true;
    const wrapper = mountApp();

    expect(wrapper.find('[data-testid="protected-page"]').exists()).toBe(true);
  });

  it("keeps the route closed when the session endpoint is unavailable", () => {
    unavailable = true;
    const wrapper = mountApp();

    expect(wrapper.find('[data-testid="protected-page"]').exists()).toBe(false);
    expect(wrapper.text()).toContain("nenhum dado de Marketing foi carregado");
  });
});
