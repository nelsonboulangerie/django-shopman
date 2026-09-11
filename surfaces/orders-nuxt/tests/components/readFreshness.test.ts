import { computed, ref, watch, onMounted, onBeforeUnmount, nextTick } from "vue";
import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";

for (const [name, value] of Object.entries({ computed, ref, watch, onMounted, onBeforeUnmount })) vi.stubGlobal(name, value);
const { default: ReadFreshness } = await import("../../app/components/ReadFreshness.vue");

describe("leitura útil e transporte são estados distintos", () => {
  it.each([-300000, 300000])("relógio local deslocado %s não altera a idade; SSE vivo não esconde erro", async drift => {
    vi.useFakeTimers({ toFake: ["Date", "performance", "setInterval", "clearInterval"] });
    const generated = "2026-09-11T12:00:00Z";
    vi.setSystemTime(Date.parse(generated) + drift);
    const wrapper = mount(ReadFreshness, { props: { metadata: { generated_at: generated, contract_version: 1 }, realtime: "live" } });
    try {
      expect(wrapper.text()).toContain("há 0 s");
      vi.advanceTimersByTime(5000);
      await nextTick();
      expect(wrapper.text()).toContain("há 5 s");
      await wrapper.setProps({ failed: true });
      expect(wrapper.text()).toContain("atualização falhou");
      expect(wrapper.text()).toContain("Conexão:");
      expect(wrapper.get("time").attributes("datetime")).toBe(generated);
    } finally { wrapper.unmount(); vi.useRealTimers(); }
  });
});
