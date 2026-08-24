// Presentation — o cliente em dois Enters. Transforms puros da busca de cliente
// do PDV: detecção e validação de CPF, máscara, a decisão do que o Enter faz e a
// transferência da query para o campo certo do cadastro. Sem rede e sem DOM — o
// componente (PosCustomerSearch) é dono do I/O; isto é dono da regra.

export function digitsOnly(value: string): string {
  return (value || "").replace(/\D/g, "");
}

/** A query "tem cara de número": só dígitos e pontuação de máscara. */
export function isNumericQuery(query: string): boolean {
  const trimmed = (query || "").trim();
  if (!trimmed) return false;
  return /^[\d\s().\-/+]+$/.test(trimmed) && digitsOnly(trimmed).length > 0;
}

/** CPF válido: 11 dígitos com verificadores corretos (sequência repetida não vale). */
export function isValidCpf(value: string): boolean {
  const digits = digitsOnly(value);
  if (digits.length !== 11) return false;
  if (/^(\d)\1{10}$/.test(digits)) return false;
  const verifier = (count: number): number => {
    let sum = 0;
    for (let i = 0; i < count; i += 1) sum += Number(digits[i]) * (count + 1 - i);
    const mod = (sum * 10) % 11;
    return mod === 10 ? 0 : mod;
  };
  return verifier(9) === Number(digits[9]) && verifier(10) === Number(digits[10]);
}

/** Máscara completa de CPF: 000.000.000-00 (só para 11 dígitos). */
export function formatCpf(value: string): string {
  const digits = digitsOnly(value);
  if (digits.length !== 11) return value;
  return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
}

/** Eco do input: quando a digitação numérica fecha um CPF VÁLIDO, o campo ganha a
 *  máscara (idempotente; digitação parcial e telefone seguem crus). */
export function maskQueryIfCpf(query: string): string {
  if (!isNumericQuery(query)) return query;
  if (!isValidCpf(query)) return query;
  return formatCpf(query);
}

/** Estado do aviso de CPF sob o campo: só fala quando há 11 dígitos numéricos. */
export function cpfHint(query: string): "" | "valid" | "invalid" {
  if (!isNumericQuery(query)) return "";
  if (digitsOnly(query).length !== 11) return "";
  return isValidCpf(query) ? "valid" : "invalid";
}

/** Rabo do CPF para confirmação visual sem expor o documento inteiro: "···789-00". */
export function cpfTail(value: string): string {
  const digits = digitsOnly(value);
  if (digits.length !== 11) return "";
  return `···${digits.slice(6, 9)}-${digits.slice(9)}`;
}

export type CustomerSearchEnterAction =
  | { type: "pick"; index: number }
  | { type: "resolve_cpf"; cpf: string }
  | { type: "transfer"; field: "phone" | "name"; value: string }
  | { type: "conclude" }
  | { type: "none" };

/** A decisão do Enter na busca, em ordem de intenção:
 *  1 resultado → seleciona; N → seleciona o destacado; 0 + CPF válido → cria/
 *  resolve direto pelo CPF; 0 + telefone/nome → transfere para o cadastro novo;
 *  query vazia com cliente já associado → concluir (fecha o modal). */
export function enterAction(input: {
  query: string;
  resultsCount: number;
  highlightedIndex: number;
  hasCustomer: boolean;
}): CustomerSearchEnterAction {
  const query = (input.query || "").trim();
  if (input.resultsCount === 1) return { type: "pick", index: 0 };
  if (input.resultsCount > 1) {
    const index = Math.min(Math.max(input.highlightedIndex, 0), input.resultsCount - 1);
    return { type: "pick", index };
  }
  if (!query) return input.hasCustomer ? { type: "conclude" } : { type: "none" };
  if (isValidCpf(query)) return { type: "resolve_cpf", cpf: digitsOnly(query) };
  const digits = digitsOnly(query);
  if (isNumericQuery(query) && (digits.length === 10 || digits.length === 11)) {
    return { type: "transfer", field: "phone", value: digits };
  }
  return { type: "transfer", field: "name", value: query };
}

/** Navegação ↑/↓ da lista (padrão combobox, com volta pelas pontas). */
export function moveHighlight(current: number, delta: 1 | -1, resultsCount: number): number {
  if (resultsCount <= 0) return -1;
  const base = current < 0 ? (delta === 1 ? -1 : 0) : current;
  return (base + delta + resultsCount) % resultsCount;
}
