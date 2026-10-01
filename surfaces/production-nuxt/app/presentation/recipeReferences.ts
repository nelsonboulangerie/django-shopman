// Fontes da receita (`external_references`: livros, vídeos, artigos) — lógica pura da tela.
// Moram em `RecipeEntry.meta["external_references"]` e se gravam pelo PATCH da
// receita com a lista INTEIRA: adicionar e remover é montar a lista nova aqui e
// mandar. A validação que vale é a do servidor (`recipe_external_references`);
// a da tela só evita mandar o que ele certamente recusa.
import type { ExternalReferenceInput, ExternalReferenceProjection } from "~/types/recipeBook";

export const MAX_REFERENCES = 30;
export const MAX_TITLE = 200;
export const MAX_URL = 500;
export const MAX_NOTE = 500;

/** Link aceitável: http ou https, com host, sem espaço (o mesmo critério do servidor). */
export function isWebUrl(value: string): boolean {
  const url = value.trim();
  if (!url || /\s/.test(url)) return false;
  try {
    const parsed = new URL(url);
    return (parsed.protocol === "http:" || parsed.protocol === "https:") && !!parsed.hostname;
  } catch {
    return false;
  }
}

/** A lista servida de volta na forma de escrita (chave vazia fica de fora). */
export function referencesForPayload(references: readonly ExternalReferenceProjection[]): ExternalReferenceInput[] {
  return references.map((reference) => {
    const item: ExternalReferenceInput = { title: reference.title };
    if (reference.url) item.url = reference.url;
    if (reference.note) item.note = reference.note;
    return item;
  });
}

export interface ReferenceDraft {
  title: string;
  url: string;
  note: string;
}

export function emptyReferenceDraft(): ReferenceDraft {
  return { title: "", url: "", note: "" };
}

/** O que impede gravar o rascunho, campo a campo; vazio = pode gravar. */
export function referenceDraftErrors(draft: ReferenceDraft): Partial<Record<keyof ReferenceDraft, string>> {
  const errors: Partial<Record<keyof ReferenceDraft, string>> = {};
  const title = draft.title.trim();
  const url = draft.url.trim();
  if (!title) errors.title = "Dê um título: o nome do livro, do vídeo ou do artigo.";
  else if (title.length > MAX_TITLE) errors.title = `O título passa de ${MAX_TITLE} caracteres.`;
  if (url && !isWebUrl(url)) errors.url = "O link precisa começar com http:// ou https://.";
  else if (url.length > MAX_URL) errors.url = `O link passa de ${MAX_URL} caracteres.`;
  if (draft.note.trim().length > MAX_NOTE) errors.note = `A nota passa de ${MAX_NOTE} caracteres.`;
  return errors;
}

/** A lista com o rascunho no fim. */
export function withReference(
  references: readonly ExternalReferenceProjection[],
  draft: ReferenceDraft,
): ExternalReferenceInput[] {
  const item: ExternalReferenceInput = { title: draft.title.trim() };
  const url = draft.url.trim();
  const note = draft.note.trim();
  if (url) item.url = url;
  if (note) item.note = note;
  return [...referencesForPayload(references), item];
}

/** A lista sem o item da posição `index`. */
export function withoutReference(
  references: readonly ExternalReferenceProjection[],
  index: number,
): ExternalReferenceInput[] {
  return referencesForPayload(references).filter((_, position) => position !== index);
}
