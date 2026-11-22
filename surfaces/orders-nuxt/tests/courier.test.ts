import { describe, expect, it } from "vitest";

import {
  courierFailed,
  courierSteps,
  courierTone,
  courierToneBadge,
} from "../app/presentation/courier";

describe("courierSteps", () => {
  it("marks the search phase as current while distributing/waiting", () => {
    for (const letter of ["searching", "grouped", "reassigning"]) {
      const steps = courierSteps(letter);
      expect(steps.map((s) => s.state)).toEqual(["current", "pending", "pending", "pending"]);
    }
  });

  it("advances to accepted when someone takes the ride or is at the shop", () => {
    for (const letter of ["assigned", "at_store"]) {
      const steps = courierSteps(letter);
      expect(steps.map((s) => s.state)).toEqual(["done", "current", "pending", "pending"]);
    }
  });

  it("shows picked-up as current when out for delivery", () => {
    expect(courierSteps("on_route").map((s) => s.state)).toEqual(["done", "done", "current", "pending"]);
  });

  it("completes every step when done", () => {
    expect(courierSteps("done").map((s) => s.state)).toEqual(["done", "done", "done", "done"]);
  });

  it("returns no steps for failed or unknown statuses", () => {
    expect(courierSteps("not_served")).toEqual([]);
    expect(courierSteps("cancelled")).toEqual([]);
    expect(courierSteps("")).toEqual([]);
    // A letra crua de um serviço não é estado: a tela não a entende.
    expect(courierSteps("A")).toEqual([]);
  });

  it("labels the four phases in board order", () => {
    expect(courierSteps("searching").map((s) => s.label)).toEqual([
      "Solicitado",
      "Aceito",
      "Coletado",
      "Entregue",
    ]);
  });
});

describe("courierTone", () => {
  it("maps ride phases to tones", () => {
    expect(courierTone("searching")).toBe("muted");
    expect(courierTone("assigned")).toBe("info");
    expect(courierTone("at_store")).toBe("info");
    expect(courierTone("on_route")).toBe("active");
    expect(courierTone("done")).toBe("success");
    expect(courierTone("not_served")).toBe("danger");
    expect(courierTone("cancelled")).toBe("danger");
    expect(courierTone("")).toBe("muted");
  });

  it("every tone resolves to badge classes", () => {
    for (const letter of ["searching", "assigned", "on_route", "done", "not_served", ""]) {
      expect(courierToneBadge(courierTone(letter))).toBeTruthy();
    }
  });
});

describe("courierFailed", () => {
  it("only not served and cancelled are failures", () => {
    expect(courierFailed("not_served")).toBe(true);
    expect(courierFailed("cancelled")).toBe(true);
    expect(courierFailed("done")).toBe(false);
    expect(courierFailed("on_route")).toBe(false);
  });
});
