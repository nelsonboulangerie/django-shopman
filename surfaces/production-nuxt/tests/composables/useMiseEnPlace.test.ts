import { ref } from "vue";
import { beforeEach, describe, expect, it } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import {
  checklistStorageKeys,
  loadChecklist,
  useMiseEnPlace,
} from "~/composables/useMiseEnPlace";

const env = installNuxtGlobals();

describe("useMiseEnPlace", () => {
  beforeEach(() => env.reset());

  it("derives the projection + lines for the day", () => {
    env.fetchData.value = { mise_en_place: { selected_date: "2026-07-06", lines: [{ sku: "FARINHA" }, { sku: "SAL" }] } };
    const { projection, lines } = useMiseEnPlace(ref("2026-07-06"), ref("prep-a"));
    expect(projection.value?.selected_date).toBe("2026-07-06");
    expect(lines.value).toHaveLength(2);
  });

  it("toggles the shift-local 'separado' check and counts it (in-memory, no server write)", () => {
    env.fetchData.value = { mise_en_place: { selected_date: "2026-07-06", lines: [{ sku: "FARINHA" }, { sku: "SAL" }] } };
    const { toggleChecked, isChecked, checkedCount } = useMiseEnPlace(ref("2026-07-06"), ref("prep-a"));

    expect(isChecked("FARINHA")).toBe(false);
    toggleChecked("FARINHA");
    expect(isChecked("FARINHA")).toBe(true);
    expect(checkedCount.value).toBe(1);

    toggleChecked("FARINHA"); // untick
    expect(isChecked("FARINHA")).toBe(false);
    expect(checkedCount.value).toBe(0);
  });

  it("degrades to empty when the payload is null", () => {
    env.fetchData.value = null;
    const { projection, lines } = useMiseEnPlace(ref("2026-07-06"), ref("prep-a"));
    expect(projection.value).toBeNull();
    expect(lines.value).toEqual([]);
  });

  it("scopes local checks by station, date and projection digest", () => {
    const first = checklistStorageKeys({
      stationRef: "prep-a",
      selectedDate: "2026-07-06",
      sourceRevision: "sha256:1111111111111111:mise:2026-07-06:user:1:sig",
    });
    const otherStation = checklistStorageKeys({
      stationRef: "prep-b",
      selectedDate: "2026-07-06",
      sourceRevision: "sha256:1111111111111111:mise:2026-07-06:user:1:sig",
    });
    const otherRevision = checklistStorageKeys({
      stationRef: "prep-a",
      selectedDate: "2026-07-06",
      sourceRevision: "sha256:2222222222222222:mise:2026-07-06:user:1:sig",
    });

    expect(first?.items).not.toBe(otherStation?.items);
    expect(first?.items).not.toBe(otherRevision?.items);
  });

  it("clears the previous revision and never presents local checks as durable facts", () => {
    const values = new Map<string, string>();
    const removed: string[] = [];
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => {
        removed.push(key);
        values.delete(key);
      },
    };
    const base = {
      stationRef: "prep-a",
      selectedDate: "2026-07-06",
    };
    const firstScope = {
      ...base,
      sourceRevision: "sha256:1111111111111111:mise:2026-07-06:user:1:sig",
    };
    const firstKeys = checklistStorageKeys(firstScope)!;
    values.set(firstKeys.activeRevision, firstKeys.digest);
    values.set(firstKeys.items, JSON.stringify(["FARINHA"]));
    expect(loadChecklist(storage, firstScope).checked).toEqual(new Set(["FARINHA"]));

    const changed = loadChecklist(storage, {
      ...base,
      sourceRevision: "sha256:2222222222222222:mise:2026-07-06:user:1:sig",
    });
    expect(changed.revisionChanged).toBe(true);
    expect(changed.checked.size).toBe(0);
    expect(removed).toEqual([firstKeys.items]);
  });
});
