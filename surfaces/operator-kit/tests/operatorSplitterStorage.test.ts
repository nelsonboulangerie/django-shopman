import { describe, expect, it } from "vitest";

import { createOperatorSplitterStorage, validOperatorSplitterState } from "../app/utils/operatorSplitterStorage";

const valid = JSON.stringify({ "left,right": { expandToSizes: {}, layout: [62, 38] } });

describe("persistência do OperatorSplitter", () => {
  it("aceita somente layouts finitos com o número esperado de panes", () => {
    expect(validOperatorSplitterState(valid, 2)).toBe(true);
    expect(validOperatorSplitterState(JSON.stringify({ key: { layout: [120, -20] } }), 2)).toBe(false);
    expect(validOperatorSplitterState(JSON.stringify({ key: { layout: [100] } }), 2)).toBe(false);
    expect(validOperatorSplitterState("não é JSON", 2)).toBe(false);
  });

  it("remove estado inválido e não o devolve ao USplitter", () => {
    const values = new Map([["reka:key", "{}"]]);
    const storage = createOperatorSplitterStorage(2, {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
      removeItem: (key) => values.delete(key),
    });
    expect(storage.getItem("reka:key")).toBeNull();
    expect(values.has("reka:key")).toBe(false);
    storage.setItem("reka:key", valid);
    expect(storage.getItem("reka:key")).toBe(valid);
  });

  it("é inerte durante SSR", () => {
    const storage = createOperatorSplitterStorage(2, undefined);
    expect(storage.getItem("reka:key")).toBeNull();
    expect(() => storage.setItem("reka:key", valid)).not.toThrow();
  });
});
