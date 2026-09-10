// Presentation — o cliente num gesto NOMEADO. Transforms puros da busca de
// cliente do PDV: detecção e validação de CPF, máscara, e a decisão do que a
// tecla faz — que é sempre a mesma coisa que o botão visível ao lado dela faz.
// Sem rede e sem DOM: o componente (PosCustomerSearch) é dono do I/O; isto é
// dono da regra e das duas frases que a nomeiam.

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
  | { type: "transfer"; field: "phone"; value: string }
  | { type: "create_name_only"; name: string }
  | { type: "conclude" }
  | { type: "none" };

/** A decisão do Enter na busca, em ordem de intenção:
 *  1 resultado → seleciona; N → seleciona o destacado; 0 + CPF válido → cria/
 *  resolve direto pelo CPF; 0 + telefone → transfere para o cadastro novo;
 *  0 + nome → cadastro SÓ COM O NOME, que é um ato nomeado e não a inércia de
 *  dois Enters; query vazia com cadastro associado → concluir (fecha o modal).
 *
 *  ⚠️ **`hasCustomerRef` é o cadastro DE VERDADE (com ref), não um nome no
 *  formulário.** Enquanto os dois eram a mesma coisa, o Enter com o campo vazio
 *  "concluía" — e concluir, com nome digitado e sem cadastro, CRIAVA um cliente
 *  sem que ninguém tivesse pedido. Dois Enters, um cliente novo, zero perguntas:
 *  é assim que nasce o terceiro "João" da semana. Agora essa tecla cai no mesmo
 *  ato NOMEADO que o botão visível oferece. */
export function enterAction(input: {
  query: string;
  resultsCount: number;
  highlightedIndex: number;
  /** Já existe cadastro associado (com ref): Enter com o campo vazio conclui. */
  hasCustomerRef: boolean;
  /** Nome no formulário ainda SEM cadastro — a criação pendente. */
  pendingName?: string;
}): CustomerSearchEnterAction {
  const query = (input.query || "").trim();
  if (input.resultsCount === 1) return { type: "pick", index: 0 };
  if (input.resultsCount > 1) {
    const index = Math.min(Math.max(input.highlightedIndex, 0), input.resultsCount - 1);
    return { type: "pick", index };
  }
  if (!query) {
    if (input.hasCustomerRef) return { type: "conclude" };
    const pending = (input.pendingName || "").trim();
    return pending ? { type: "create_name_only", name: pending } : { type: "none" };
  }
  if (isValidCpf(query)) return { type: "resolve_cpf", cpf: digitsOnly(query) };
  const digits = digitsOnly(query);
  if (isNumericQuery(query) && (digits.length === 10 || digits.length === 11)) {
    return { type: "transfer", field: "phone", value: digits };
  }
  return { type: "create_name_only", name: query };
}

/** O RESULTADO da tecla, em voz de balcão — o rótulo do botão visível que faz a
 *  mesma coisa. Sai daqui para que a tecla e o botão nunca divirjam: o `<kbd>`
 *  fica de affordance ao lado do rótulo, em vez de a frase explicar a tecla. */
export function enterActionLabel(action: CustomerSearchEnterAction): string {
  if (action.type === "resolve_cpf") return "Cadastrar cliente novo com este CPF";
  if (action.type === "transfer") return `Cadastrar cliente novo com o ${action.value}`;
  if (action.type === "create_name_only") return `Cadastrar «${action.name}» só com o nome`;
  return "";
}

/** A RESSALVA do cadastro só com o nome. Não bloqueia — informa o que fica de
 *  fora, que é o que o operador não tem como adivinhar sozinho. */
export function enterActionCaveat(action: CustomerSearchEnterAction): string {
  if (action.type !== "create_name_only") return "";
  return "Sem WhatsApp: o cliente não recebe aviso de pronto, e um xará vira outro cadastro.";
}

/** Navegação ↑/↓ da lista (padrão combobox, com volta pelas pontas). */
export function moveHighlight(current: number, delta: 1 | -1, resultsCount: number): number {
  if (resultsCount <= 0) return -1;
  const base = current < 0 ? (delta === 1 ? -1 : 0) : current;
  return (base + delta + resultsCount) % resultsCount;
}
