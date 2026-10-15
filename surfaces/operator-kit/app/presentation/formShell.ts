// Casco de cadastro — a regra pura do estado sujo e a copy do descarte.
//
// O `OperatorFormShell` desenha o casco (seções, aviso do que não foi salvo,
// barra de ação na base, próximo foco e a pergunta antes de descartar); a conta
// entre o RETRATO da abertura e o formulário de agora mora aqui, sem tocar DOM
// nem rede. Quem chama entrega um retrato simples (primitivos, arrays de
// primitivos e objetos simples): o retrato não é um espelho do formulário, é o
// conjunto de campos que o operador reconhece.

export type FormValues = Record<string, unknown>;

function isPlainObject(value: unknown): value is FormValues {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function cloneValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(cloneValue);
  if (isPlainObject(value)) {
    const out: FormValues = {};
    for (const key of Object.keys(value)) out[key] = cloneValue(value[key]);
    return out;
  }
  return value;
}

/** Cópia profunda do retrato, lendo através dos proxies reativos do Vue. */
export function cloneFormValues<T extends FormValues>(values: T): T {
  return cloneValue(values) as T;
}

/** Dois valores de formulário são o mesmo? Campos vazios contam, NaN também. */
export function sameFormValue(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((item, index) => sameFormValue(item, b[index]));
  }
  if (isPlainObject(a) && isPlainObject(b)) {
    const aKeys = Object.keys(a);
    const bKeys = Object.keys(b);
    return (
      aKeys.length === bKeys.length &&
      aKeys.every((key) => Object.prototype.hasOwnProperty.call(b, key) && sameFormValue(a[key], b[key]))
    );
  }
  return Number.isNaN(a) && Number.isNaN(b);
}

/** As chaves que mudaram desde o retrato, na ordem em que aparecem. */
export function changedFieldKeys(baseline: FormValues, current: FormValues): string[] {
  const keys = new Set([...Object.keys(baseline), ...Object.keys(current)]);
  return [...keys].filter((key) => !sameFormValue(baseline[key], current[key]));
}

export function isFormDirty(baseline: FormValues | null, current: FormValues): boolean {
  return baseline === null ? false : changedFieldKeys(baseline, current).length > 0;
}

/** O aviso do que ainda não foi salvo. Sem contagem, a tela não afirma número. */
export function dirtyCountLabel(count: number): string {
  if (count <= 0) return "Alterações não salvas";
  return count === 1 ? "1 alteração não salva" : `${count} alterações não salvas`;
}

/** A pergunta antes de descartar o cadastro, no diálogo da casa (`useConfirm`). */
export const FORM_DISCARD_COPY = {
  title: "Descartar o que você preencheu?",
  description: "O cadastro ainda não foi salvo. O que foi preenchido se perde.",
  confirmLabel: "Descartar e sair",
  cancelLabel: "Continuar preenchendo",
} as const;

export type FormDiscardCopy = {
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
};
