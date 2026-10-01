import { describe, expect, it } from "vitest";

import {
  MAX_REFERENCES,
  emptyReferenceDraft,
  isWebUrl,
  referenceDraftErrors,
  referencesForPayload,
  withReference,
  withoutReference,
} from "~/presentation/recipeReferences";
import type { ExternalReferenceProjection } from "~/types/recipeBook";

const SERVED: ExternalReferenceProjection[] = [
  { title: "Tartine Bread", url: "", host_display: "", note: "p. 48" },
  { title: "Laminação", url: "https://www.youtube.com/watch?v=abc", host_display: "youtube.com", note: "" },
];

describe("isWebUrl", () => {
  it("accepts only http and https with a host, without spaces", () => {
    expect(isWebUrl("https://exemplo.com.br/a")).toBe(true);
    expect(isWebUrl("http://exemplo.com")).toBe(true);
    expect(isWebUrl("javascript:alert(1)")).toBe(false);
    expect(isWebUrl("ftp://exemplo.com")).toBe(false);
    expect(isWebUrl("exemplo.com")).toBe(false);
    expect(isWebUrl("https://exemplo.com/a b")).toBe(false);
    expect(isWebUrl("")).toBe(false);
  });
});

describe("references payload", () => {
  it("serves back the write shape, without empty keys", () => {
    expect(referencesForPayload(SERVED)).toEqual([
      { title: "Tartine Bread", note: "p. 48" },
      { title: "Laminação", url: "https://www.youtube.com/watch?v=abc" },
    ]);
  });

  it("adds the trimmed draft at the end and removes by position", () => {
    const added = withReference(SERVED, { title: "  Artigo  ", url: " https://a.b/c ", note: "  " });
    expect(added).toHaveLength(3);
    expect(added[2]).toEqual({ title: "Artigo", url: "https://a.b/c" });
    expect(withoutReference(SERVED, 0)).toEqual([{ title: "Laminação", url: "https://www.youtube.com/watch?v=abc" }]);
  });
});

describe("referenceDraftErrors", () => {
  it("asks for a title and a web link, and accepts a draft without link", () => {
    expect(referenceDraftErrors(emptyReferenceDraft()).title).toContain("Dê um título");
    expect(referenceDraftErrors({ title: "Livro", url: "javascript:x", note: "" }).url).toContain("http");
    expect(referenceDraftErrors({ title: "Livro", url: "", note: "" })).toEqual({});
    expect(referenceDraftErrors({ title: "x".repeat(201), url: "", note: "" }).title).toContain("200");
    expect(referenceDraftErrors({ title: "Livro", url: "", note: "y".repeat(501) }).note).toContain("500");
  });

  it("matches the server ceiling", () => {
    expect(MAX_REFERENCES).toBe(30);
  });
});
