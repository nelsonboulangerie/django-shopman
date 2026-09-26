// O selo do item do rail: uma contagem curta que sobrevive aos 3 estados. Some quando
// vazio (zero não é selo), é só visual (o nome acessível é de quem monta o item) e
// troca de lugar conforme o rail mostra ou não o rótulo.
import { mountSuspended } from "@nuxt/test-utils/runtime";
import { afterEach, describe, expect, it } from "vitest";
import type { VueWrapper } from "vue";

import RailItem from "../../app/components/RailItem.vue";

const mounted: VueWrapper[] = [];

async function mountItem(props: Record<string, unknown>) {
  const wrapper = await mountSuspended(RailItem, {
    props: { icon: "package", label: "Encomendas", ...props },
    global: { stubs: { Icon: true } },
  });
  mounted.push(wrapper as unknown as VueWrapper);
  return wrapper;
}

afterEach(() => {
  for (const wrapper of mounted.splice(0)) wrapper.unmount();
  useRailState().set("compact");
});

describe("RailItem — selo", () => {
  it("sem selo não desenha nada a mais", async () => {
    useRailState().set("compact");
    const wrapper = await mountItem({});
    expect(wrapper.find("[data-rail-badge]").exists()).toBe(false);
  });

  it("no compacto, o selo fica no canto do ícone e é só visual", async () => {
    useRailState().set("compact");
    const wrapper = await mountItem({ badge: "3", ariaLabel: "Encomendas — 3 para entregar hoje" });
    const badge = wrapper.get("[data-rail-badge]");
    expect(badge.text()).toBe("3");
    expect(badge.attributes("aria-hidden")).toBe("true");
    expect(wrapper.attributes("aria-label")).toBe("Encomendas — 3 para entregar hoje");
  });

  it("no estendido, o selo vai para o fim da linha, depois do rótulo", async () => {
    useRailState().set("extended");
    const wrapper = await mountItem({ badge: "12" });
    expect(wrapper.findAll("[data-rail-badge]")).toHaveLength(1);
    expect(wrapper.text()).toBe("Encomendas12");
  });
});
