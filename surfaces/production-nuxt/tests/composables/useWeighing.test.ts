import { ref } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { allocateColdWeighingProjection, useWeighing } from "~/composables/useWeighing";

const env = installNuxtGlobals();

describe("useWeighing", () => {
  beforeEach(() => env.reset());

  it("derives tickets + date display", () => {
    env.fetchData.value = {
      weighing: { selected_date_display: "domingo", tickets: [{ code: "D06" }, { code: "D07" }] },
    };
    const { tickets, dateDisplay } = useWeighing(ref("2026-07-06"));
    expect(tickets.value).toHaveLength(2);
    expect(dateDisplay.value).toBe("domingo");
  });

  it("degrades to empty when the payload is null", () => {
    env.fetchData.value = null;
    const { tickets, dateDisplay } = useWeighing(ref("2026-07-06"));
    expect(tickets.value).toEqual([]);
    expect(dateDisplay.value).toBe("");
  });

  it("a massa velha é escolha por preparo e troca as linhas pela mistura final no teto", () => {
    const ticket = {
      ticket_ref: "prep-a",
      recipe_ref: "massa",
      output_sku: "MASSA",
      ingredients: [
        { sku: "FARINHA", name: "Farinha", target_display: "1000 g", quantity_display: "1000 g", annotation: "" },
      ],
      old_dough: {
        cap_pct: "20",
        cap_display: "20%",
        old_dough_display: "344 g",
        old_dough_g: "344",
        lines: [{ sku: "FARINHA", target_display: "800 g", target_g: "800" }],
      },
    };
    env.fetchData.value = { weighing: { selected_date_display: "segunda", tickets: [ticket] } };
    const weighing = useWeighing(ref("2026-07-06"));

    expect(weighing.usesOldDough("prep-a")).toBe(false);
    expect(weighing.rowsFor(ticket as never, "prep-a").map((row) => row.target)).toEqual(["1000 g"]);

    weighing.setOldDough("prep-a", true);
    expect(weighing.usesOldDough("prep-a")).toBe(true);
    expect(weighing.usesOldDough("prep-b")).toBe(false);
    expect(weighing.rowsFor(ticket as never, "prep-a").map((row) => row.target)).toEqual(["344 g", "800 g"]);

    weighing.setOldDough("prep-a", false);
    expect(weighing.rowsFor(ticket as never, "prep-a").map((row) => row.target)).toEqual(["1000 g"]);
  });

  it("allocates a cold revision once through its projected POST action", async () => {
    const cold = {
      selected_date: "2026-07-06",
      selected_date_display: "segunda",
      selected_position_ref: "",
      selected_base_recipe: "",
      codes_ready: false,
      tickets: [{ recipe_ref: "massa", blind_code: "" }],
      generated_at: "2026-07-06T09:00:00Z",
      source_revision: "sha256:cold:weighing:2026-07-06:user:1",
      fresh_until: "2026-07-06T09:01:30Z",
      contract_version: 1,
      actions: [
        {
          ref: "allocate_blind_codes:2026-07-06::",
          kind: "allocate_blind_codes",
          enabled: true,
          href: "/api/v1/backstage/production/weighing/blind-codes/",
          proof: "signed-proof",
        },
      ],
    };
    env.fetchMock.mockResolvedValue({
      weighing: { ...cold, codes_ready: true },
    });

    const attempts = new Set<string>();
    const ready = await allocateColdWeighingProjection(cold, attempts);
    await allocateColdWeighingProjection(cold, attempts);

    expect(ready?.weighing.codes_ready).toBe(true);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/production/weighing/blind-codes/",
      expect.objectContaining({ method: "POST" }),
    );
    expect(env.fetchMock).toHaveBeenCalledTimes(1);
  });
});
