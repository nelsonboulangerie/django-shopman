import { expect, it, vi } from "vitest";
import { ref } from "vue";
import { useDragReorder } from "../../app/composables/useDragReorder";
vi.stubGlobal("ref", ref);

it("arraste conserva o conjunto visto no início apesar de uma leitura posterior", () => {
  const first = document.createElement("div");
  first.setAttribute("data-dragkey", "A");
  const second = document.createElement("div");
  second.setAttribute("data-dragkey", "B");
  document.body.append(first, second);
  const point = vi.spyOn(document, "elementFromPoint").mockReturnValue(second);
  let keys = ["A", "B", "C"];
  const commit = vi.fn();
  const start = vi.fn();
  const drag = useDragReorder(() => keys, commit, start);
  try {
    drag.onPointerDown("A", { pointerType: "mouse", button: 0, currentTarget: first, clientX: 0, clientY: 0, pointerId: 1 } as unknown as PointerEvent);
    keys = ["C", "B", "A"];
    first.dispatchEvent(new PointerEvent("pointermove", { clientX: 20, clientY: 0, pointerId: 1 }));
    first.dispatchEvent(new PointerEvent("pointerup", { clientX: 20, clientY: 0, pointerId: 1 }));
    expect(start).toHaveBeenCalledTimes(1);
    expect(commit).toHaveBeenCalledWith(["B", "A", "C"]);
    expect(document.body.style.userSelect).toBe("");
  } finally { point.mockRestore(); first.remove(); second.remove(); }
});

it("teclado e arraste produzem a mesma ordem, sem sair dos limites", () => {
  const commit = vi.fn();
  const start = vi.fn();
  const drag = useDragReorder(() => ["A", "B", "C"], commit, start);
  const down = new KeyboardEvent("keydown", { key: "ArrowDown", cancelable: true });
  drag.onKeyDown("A", down);
  expect(down.defaultPrevented).toBe(true);
  expect(commit).toHaveBeenCalledWith(["B", "A", "C"]);
  expect(start).toHaveBeenCalledTimes(1);
  drag.onKeyDown("A", new KeyboardEvent("keydown", { key: "ArrowUp" }));
  drag.onKeyDown("C", new KeyboardEvent("keydown", { key: "ArrowDown" }));
  expect(commit).toHaveBeenCalledTimes(1);
});
