import { mount } from "@vue/test-utils";
import { defineComponent, h, nextTick, ref } from "vue";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useNowTick } from "../../app/composables/useNowTick";

afterEach(() => {
  vi.useRealTimers();
});

describe("useNowTick: o relógio do servidor", () => {
  it.each([-300000, 300000])("ignora o desvio do dispositivo %s e reancora ao retomar", async (drift) => {
    vi.useFakeTimers({ toFake: ["Date", "performance", "setInterval", "clearInterval"] });
    const server = Date.parse("2026-09-10T12:00:00Z");
    vi.setSystemTime(server + drift);
    const source = ref(new Date(server).toISOString());
    const component = defineComponent({
      setup() {
        const now = useNowTick(() => source.value);
        return () => h("span", String(now.value));
      },
    });
    const wrapper = mount(component);
    expect(Number(wrapper.text())).toBe(server);
    vi.advanceTimersByTime(5000);
    await nextTick();
    expect(Number(wrapper.text())).toBe(server + 5000);
    vi.setSystemTime(server + 900000);
    source.value = new Date(server + 60000).toISOString();
    await nextTick();
    expect(Number(wrapper.text())).toBe(server + 60000);
    wrapper.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
