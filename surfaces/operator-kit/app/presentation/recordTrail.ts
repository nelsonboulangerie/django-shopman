// A trilha de uma lista: anterior e próximo DENTRO da lista de onde a pessoa veio
// (WP-FASE2-UX-OPERADOR, A9 e peça K5).
//
// A lista grava a ordem que mostra, com o recorte aplicado (a busca, o escopo, a
// ordenação); o detalhe lê a trilha e diz "3 de 18". "18" são os 18 que a pessoa via, não
// os pedidos do dia. Sem trilha, ou com o registro fora dela (aberto por link, por outro
// app, por uma lista que já mudou), o par não aparece: navegação que mente é pior que
// navegação nenhuma.
//
// Funções puras: o componente (`OperatorRecordNav`) e o composable (`useRecordTrail`) só
// desenham e guardam o que elas decidem.

/** A ordem que a lista mostrava, como a pessoa a viu. */
export interface RecordTrail {
  /** Os identificadores, na ordem da tela. */
  ids: string[];
  /** O endereço da lista com o recorte (`fullPath`): para onde o "voltar" leva. */
  from: string;
  /** O nome da lista ("Pedidos", "Histórico"), para o nome acessível do par. */
  label: string;
}

/** Onde o registro está na trilha. */
export interface RecordTrailPosition {
  /** Posição a partir de 0. */
  index: number;
  total: number;
  previous: string | null;
  next: string | null;
}

/** Trilha maior que isto não é lista de tela: é o banco. Corta para não pesar a sessão. */
export const RECORD_TRAIL_MAX = 500;

/** A posição do registro na trilha, ou `null` quando não há par a mostrar. */
export function recordTrailPosition(
  trail: RecordTrail | null | undefined,
  id: string,
): RecordTrailPosition | null {
  if (!trail || !id) return null;
  const index = trail.ids.indexOf(id);
  // Fora da trilha, ou sozinho nela: nada a percorrer.
  if (index < 0 || trail.ids.length < 2) return null;
  return {
    index,
    total: trail.ids.length,
    previous: index > 0 ? trail.ids[index - 1]! : null,
    next: index < trail.ids.length - 1 ? trail.ids[index + 1]! : null,
  };
}

/** "3 de 18". */
export function recordTrailCount(position: RecordTrailPosition): string {
  return `${position.index + 1} de ${position.total}`;
}

/** A trilha pronta para guardar: sem vazio, sem repetido, no máximo `RECORD_TRAIL_MAX`. */
export function recordTrailOf(ids: readonly string[], from: string, label: string): RecordTrail {
  const seen = new Set<string>();
  const clean: string[] = [];
  for (const id of ids) {
    if (!id || seen.has(id)) continue;
    seen.add(id);
    clean.push(id);
    if (clean.length >= RECORD_TRAIL_MAX) break;
  }
  return { ids: clean, from, label };
}

/** Lê uma trilha guardada (JSON da sessão do navegador); qualquer coisa estranha é `null`. */
export function parseRecordTrail(raw: string | null | undefined): RecordTrail | null {
  if (!raw) return null;
  try {
    const data = JSON.parse(raw) as Partial<RecordTrail>;
    if (!Array.isArray(data.ids) || typeof data.from !== "string" || typeof data.label !== "string") {
      return null;
    }
    return recordTrailOf(
      data.ids.filter((id): id is string => typeof id === "string"),
      data.from,
      data.label,
    );
  } catch {
    return null;
  }
}
