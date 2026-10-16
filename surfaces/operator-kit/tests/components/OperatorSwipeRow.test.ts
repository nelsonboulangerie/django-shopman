import { mountSuspended } from "@nuxt/test-utils/runtime";
import { describe, expect, it } from "vitest";
import { h } from "vue";

import OperatorSwipeRow from "../../app/components/OperatorSwipeRow.vue";

// Deslizar uma linha no toque (F7): para a direita faz o gesto principal depois do
// ponto de compromisso; para a esquerda revela as ações; o mouse não desliza.

const COMMIT = { label: "Entregar U13 a Ana", icon: "lucide:hand-platter" };
const ACTIONS = [
  { key: "assign", label: "Atender", icon: "lucide:user-plus", tone: "info" as const },
];

async function mountRow(props: Record<string, unknown>) {
  return mountSuspended(OperatorSwipeRow, {
    props: { label: "Pedido U13", ...props },
    slots: { default: () => h("p", { "data-content": "" }, "U13 Ana") },
  });
}

function slide(
  el: Element,
  steps: number[],
  pointerType = "touch",
  release = true,
) {
  const at = (type: string, x: number) =>
    el.dispatchEvent(
      new PointerEvent(type, {
        bubbles: true,
        pointerId: 3,
        pointerType,
        clientX: x,
        clientY: 20,
      }),
    );
  at("pointerdown", 10);
  for (const dx of steps) at("pointermove", 10 + dx);
  if (release) at("pointerup", 10 + (steps.at(-1) ?? 0));
}

describe("OperatorSwipeRow", () => {
  it("à direita, passou do ponto: faz o gesto (uma vez)", async () => {
    const row = await mountRow({ commit: COMMIT });
    slide(row.get("[data-swipe-label]").element, [20, 60, 120]);
    await row.vm.$nextTick();
    expect(row.emitted("commit")).toHaveLength(1);
  });

  it("à direita, soltou antes do ponto: a linha volta e nada acontece", async () => {
    const row = await mountRow({ commit: COMMIT });
    slide(row.get("[data-swipe-label]").element, [20, 60]);
    await row.vm.$nextTick();
    expect(row.emitted("commit")).toBeUndefined();
    expect(row.find("[data-swipe-commit]").exists()).toBe(false);
  });

  it("no meio do gesto mostra o que vai acontecer, fora da árvore acessível", async () => {
    const row = await mountRow({ commit: COMMIT });
    slide(row.get("[data-swipe-label]").element, [20, 120], "touch", false);
    await row.vm.$nextTick();
    const layer = row.get("[data-swipe-commit]");
    expect(layer.text()).toBe("Entregar U13 a Ana");
    expect(layer.attributes("aria-hidden")).toBe("true");
    expect(row.get("[data-swipe-row]").attributes("data-swipe-armed")).toBe("true");
  });

  it("o mouse não desliza", async () => {
    const row = await mountRow({ commit: COMMIT });
    slide(row.get("[data-swipe-label]").element, [20, 60, 120], "mouse");
    await row.vm.$nextTick();
    expect(row.emitted("commit")).toBeUndefined();
  });

  it("sem gesto principal, a direita não anda; a esquerda abre as ações", async () => {
    const row = await mountRow({ actions: ACTIONS });
    const content = row.get("[data-swipe-label]");
    slide(content.element, [20, 120]);
    await row.vm.$nextTick();
    expect(row.emitted("commit")).toBeUndefined();
    expect(content.attributes("style")).toContain("translateX(0px)");
    slide(content.element, [-20, -80]);
    await row.vm.$nextTick();
    expect(row.get("[data-swipe-row]").attributes("data-swipe-open")).toBe("true");
    await row.get("[data-swipe-action='assign']").trigger("click");
    expect(row.emitted("pick")?.[0]).toEqual(["assign"]);
  });

  it("parada, a linha não anima nem recorta nada (redução de movimento e menu ⋯)", async () => {
    const row = await mountRow({ commit: COMMIT, actions: ACTIONS });
    expect(row.get("[data-swipe-label]").classes()).toContain(
      "motion-safe:transition-transform",
    );
    expect(row.get("[data-swipe-row]").classes()).not.toContain("overflow-hidden");
  });
});
