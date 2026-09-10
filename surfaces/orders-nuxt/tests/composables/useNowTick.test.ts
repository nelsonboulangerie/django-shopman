// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from "vitest";
import { computed, defineComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { mount } from "@vue/test-utils";

for (const [key, value] of Object.entries({ computed, ref, watch, onMounted, onBeforeUnmount })) vi.stubGlobal(key, value);
afterEach(() => { vi.useRealTimers(); });

describe("server clock", () => {
  it.each([-300000, 300000])("ignores browser drift %s and reanchors after resume", async (drift) => {
    vi.useFakeTimers({ toFake: ["Date", "performance", "setInterval", "clearInterval"] });
    const server = Date.parse("2026-09-10T12:00:00Z");
    vi.setSystemTime(server + drift);
    const source = ref(new Date(server).toISOString());
    const { useNowTick } = await import("../../app/composables/useNowTick");
    const component = defineComponent({ setup() { return { now: useNowTick(() => source.value) }; }, template: "<span>{{ now }}</span>" });
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
