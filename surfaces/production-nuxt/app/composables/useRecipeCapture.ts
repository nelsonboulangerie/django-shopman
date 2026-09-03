// Leitura automática de uma anotação ou foto — POST recipes/capture/ devolve o
// rascunho estruturado (nome, língua, rendimento, ingredientes casados com
// candidatos, passos). A foto é redimensionada NO NAVEGADOR (canvas, maior lado
// ≤ 1600 px) antes de subir como base64: a ficha fotografada no celular tem 12 MP
// e o provedor não precisa disso.
//
// 503 NÃO é erro: é "sem leitura automática neste ambiente" (credencial ausente,
// RecipeCaptureNotConfigured) — a tela oferece a porta manual em vez de um beco.
// 502 (provedor falhou) e o resto são erro comum, com a mensagem do servidor.
import type { CaptureImagePayload, CaptureResponse, RecipeCaptureDraftProjection } from "~/types/recipeBook";
import { downscaleTarget, outputMediaType, splitDataUrl } from "~/presentation/recipeBook";

export type CaptureState = "idle" | "reading" | "done" | "unavailable" | "error";

export const CAPTURE_UNAVAILABLE_MESSAGE = "Sem leitura automática neste ambiente: preencha à mão.";

export type ImageEncoder = (file: File) => Promise<CaptureImagePayload>;

/** Redimensiona no canvas e devolve `{data_base64, media_type}`. Só navegador. */
export async function encodeImageForCapture(file: File): Promise<CaptureImagePayload> {
  const bitmap = await createImageBitmap(file);
  try {
    const target = downscaleTarget(bitmap.width, bitmap.height);
    const canvas = document.createElement("canvas");
    canvas.width = target.width;
    canvas.height = target.height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("canvas indisponível");
    context.drawImage(bitmap, 0, 0, target.width, target.height);
    const mediaType = outputMediaType(file.type);
    const parts = splitDataUrl(canvas.toDataURL(mediaType, 0.85));
    if (!parts) throw new Error("não foi possível codificar a imagem");
    return parts;
  } finally {
    bitmap.close();
  }
}

export function useRecipeCapture(options: { encode?: ImageEncoder } = {}) {
  const encode = options.encode ?? encodeImageForCapture;

  const state = ref<CaptureState>("idle");
  const draft = ref<RecipeCaptureDraftProjection | null>(null);
  const error = ref("");
  const reading = computed(() => state.value === "reading");
  const unavailable = computed(() => state.value === "unavailable");

  async function request(body: Record<string, unknown>): Promise<RecipeCaptureDraftProjection | null> {
    if (state.value === "reading") return null;
    state.value = "reading";
    error.value = "";
    try {
      const response = await $fetch<CaptureResponse>("/api/v1/backstage/recipes/capture/", {
        method: "POST",
        body,
      });
      draft.value = response.draft;
      state.value = "done";
      return response.draft;
    } catch (err) {
      if (httpError(err).status === 503) {
        state.value = "unavailable";
        error.value = "";
        return null;
      }
      state.value = "error";
      error.value = httpErrorMessage(err, "Não foi possível ler a receita. Tente de novo ou preencha à mão.");
      return null;
    }
  }

  function captureText(text: string, languageHint = ""): Promise<RecipeCaptureDraftProjection | null> {
    const body: Record<string, unknown> = { text };
    if (languageHint) body.language_hint = languageHint;
    return request(body);
  }

  async function captureImage(file: File, languageHint = ""): Promise<RecipeCaptureDraftProjection | null> {
    if (state.value === "reading") return null;
    let image: CaptureImagePayload;
    try {
      image = await encode(file);
    } catch {
      state.value = "error";
      error.value = "Não foi possível preparar a foto. Tente outra imagem ou preencha à mão.";
      return null;
    }
    const body: Record<string, unknown> = { image };
    if (languageHint) body.language_hint = languageHint;
    return request(body);
  }

  function reset(): void {
    state.value = "idle";
    draft.value = null;
    error.value = "";
  }

  return { state, draft, error, reading, unavailable, captureText, captureImage, reset };
}
