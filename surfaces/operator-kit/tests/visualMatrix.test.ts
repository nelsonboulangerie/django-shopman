import { describe, expect, it } from "vitest";

import { OPERATOR_VISUAL_MATRIX, OPERATOR_VISUAL_STATES, selectedOperatorViewports } from "../visual/matrix";

describe("matriz visual transversal", () => {
  it("preserva os nove perfis obrigatórios do WP-UX-13", () => {
    expect(OPERATOR_VISUAL_MATRIX.map(({ label }) => label)).toEqual([
      "1920x1080",
      "1440x900",
      "1366x768",
      "1280x800",
      "1180x820",
      "820x1180",
      "390x844",
      "320x568",
      "1280x800@200%",
    ]);
  });

  it("filtra incrementalmente e recusa id desconhecido", () => {
    expect(selectedOperatorViewports("mobile-standard,desktop-common").map(({ id }) => id)).toEqual([
      "desktop-common",
      "mobile-standard",
    ]);
    expect(() => selectedOperatorViewports("telefone-mágico")).toThrow(/desconhecidos/);
  });

  it("inclui recuperação, camadas, foco e estados extremos", () => {
    expect(OPERATOR_VISUAL_STATES).toEqual(expect.arrayContaining([
      "extreme-content",
      "recoverable-error",
      "session-expired",
      "offline",
      "modal",
      "layered-overlays",
      "keyboard",
      "keyboard-focus",
      "touch",
      "scanner",
      "camera",
      "rotation",
      "multi-selected",
      "first-visit",
      "saved-state",
    ]));
  });
});
