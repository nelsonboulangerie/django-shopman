// O gesto de deslizar uma linha (OperatorSwipeRow): as regras puras.
import { describe, expect, it } from "vitest";

import {
  commitReached,
  revealSettles,
  SWIPE_COMMIT_PX,
  SWIPE_REVEAL_PX,
  swipeAxis,
  swipeDirection,
  swipeOffset,
} from "../app/presentation/swipe";

describe("deslizar uma linha", () => {
  it("a linha só anda na direção do gesto, com resistência depois do limite", () => {
    expect(swipeOffset(40, "left")).toBe(0);
    expect(swipeOffset(-80, "left")).toBe(-80);
    expect(swipeOffset(-(SWIPE_REVEAL_PX + 40), "left")).toBe(
      -(SWIPE_REVEAL_PX + 10),
    );
    expect(swipeOffset(120, "right")).toBe(120);
    expect(swipeOffset(-10, "right")).toBe(0);
  });
  it("a gaveta da esquerda fica aberta só depois da metade", () => {
    expect(revealSettles(-(SWIPE_REVEAL_PX / 2))).toBe(true);
    expect(revealSettles(-(SWIPE_REVEAL_PX / 2 - 1))).toBe(false);
  });
  it("o gesto da direita só vale depois do ponto de compromisso", () => {
    expect(commitReached(SWIPE_COMMIT_PX)).toBe(true);
    expect(commitReached(SWIPE_COMMIT_PX - 1)).toBe(false);
  });
  it("rolar nunca vira deslize: o eixo se decide no começo", () => {
    expect(swipeAxis(4, 3)).toBe("");
    expect(swipeAxis(14, 3)).toBe("x");
    expect(swipeAxis(6, 14)).toBe("y");
    expect(swipeAxis(14, 20)).toBe("y");
  });
  it("cada lado só existe se tiver o que fazer; aberta, a linha só volta", () => {
    const both = { hasActions: true, hasCommit: true, open: false };
    expect(swipeDirection(20, both)).toBe("right");
    expect(swipeDirection(-20, both)).toBe("left");
    expect(swipeDirection(20, { ...both, hasCommit: false })).toBe("");
    expect(swipeDirection(-20, { ...both, hasActions: false })).toBe("");
    expect(swipeDirection(20, { ...both, open: true })).toBe("left");
  });
});
