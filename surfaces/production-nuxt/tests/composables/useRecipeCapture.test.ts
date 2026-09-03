import { beforeEach, describe, expect, it, vi } from "vitest";
import { installNuxtGlobals } from "../../../operator-kit/tests/support/composableEnv";
import { useRecipeCapture } from "~/composables/useRecipeCapture";

const env = installNuxtGlobals();

const DRAFT = {
  name: "Pain de campagne",
  kind: "bread",
  language: "fr",
  yield_quantity: "2",
  yield_unit: "kg",
  items: [{ name: "Farinha T65", original_text: "farine T65", quantity: "1000", unit: "g", role: "flour", sku: "FARINHA-T65", match_confidence: "alta", candidates: [] }],
  steps: [],
  notes: "",
  formula: {},
};

describe("useRecipeCapture", () => {
  beforeEach(() => env.reset());

  it("captureText POSTs the note and lands on the draft", async () => {
    env.fetchMock.mockResolvedValueOnce({ draft: DRAFT });
    const capture = useRecipeCapture();
    const draft = await capture.captureText("1 kg farine T65…", "fr");
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/recipes/capture/",
      expect.objectContaining({ method: "POST", body: { text: "1 kg farine T65…", language_hint: "fr" } }),
    );
    expect(draft?.name).toBe("Pain de campagne");
    expect(capture.state.value).toBe("done");
    expect(capture.draft.value?.language).toBe("fr");
    expect(capture.error.value).toBe("");
  });

  it("503 is the 'unavailable' state, not an error", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 503, data: { detail: "Leitura automática não configurada." } });
    const capture = useRecipeCapture();
    const draft = await capture.captureText("qualquer coisa");
    expect(draft).toBeNull();
    expect(capture.state.value).toBe("unavailable");
    expect(capture.unavailable.value).toBe(true);
    expect(capture.error.value).toBe("");
    expect(env.sonner.error).not.toHaveBeenCalled();
  });

  it("502 (provider failure) is a real error with the server message", async () => {
    env.fetchMock.mockRejectedValueOnce({ status: 502, data: { detail: "O provedor não respondeu." } });
    const capture = useRecipeCapture();
    await capture.captureText("x");
    expect(capture.state.value).toBe("error");
    expect(capture.error.value).toBe("O provedor não respondeu.");
  });

  it("captureImage encodes the file (downscaled) and sends {image: {data_base64, media_type}}", async () => {
    const encode = vi.fn().mockResolvedValue({ data_base64: "AAAA", media_type: "image/jpeg" });
    env.fetchMock.mockResolvedValueOnce({ draft: DRAFT });
    const capture = useRecipeCapture({ encode });
    const file = { name: "ficha.jpg", type: "image/jpeg" } as File;
    const draft = await capture.captureImage(file);
    expect(encode).toHaveBeenCalledWith(file);
    expect(env.fetchMock).toHaveBeenCalledWith(
      "/api/v1/backstage/recipes/capture/",
      expect.objectContaining({ method: "POST", body: { image: { data_base64: "AAAA", media_type: "image/jpeg" } } }),
    );
    expect(draft?.name).toBe("Pain de campagne");
  });

  it("captureImage: a file the browser cannot decode is an error before any request", async () => {
    const encode = vi.fn().mockRejectedValue(new Error("decode"));
    const capture = useRecipeCapture({ encode });
    const draft = await capture.captureImage({ name: "x.heic", type: "image/heic" } as File);
    expect(draft).toBeNull();
    expect(capture.state.value).toBe("error");
    expect(env.fetchMock).not.toHaveBeenCalled();
  });

  it("reset returns to idle and clears the draft", async () => {
    env.fetchMock.mockResolvedValueOnce({ draft: DRAFT });
    const capture = useRecipeCapture();
    await capture.captureText("x");
    capture.reset();
    expect(capture.state.value).toBe("idle");
    expect(capture.draft.value).toBeNull();
  });
});
