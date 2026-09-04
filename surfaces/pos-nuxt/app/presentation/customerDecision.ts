// Presentation — A ESCOLHA É DO OPERADOR, o sistema não decide sozinho.
//
// Duas situações do balcão em que o PDV parava de perguntar e agia:
//
//   1. `contact_conflict` — o WhatsApp digitado no formulário de edição já é de
//      OUTRO cadastro. Antes disso, o servidor achava um único candidato e o
//      dono do pedido trocava em SILÊNCIO (e, se o nome do outro fosse
//      placeholder, o nome de quem estava na comanda ainda ia parar no cadastro
//      dele). Trocar de cliente segue legítimo e frequente — mas pela porta da
//      frente, com o operador dizendo sim.
//
//   2. `contact_change` — o contato do cliente ASSOCIADO vai mudar. O cadastro
//      não tinha conserto pelo balcão (o merge só preenchia lacuna) e a única
//      saída era o Admin. Agora tem, com os dois valores nomeados antes de
//      acontecer: "de X para Y".
//
// Sem rede e sem DOM: o componente é dono do I/O, isto é dono da frase e dos
// dois caminhos de um toque.

/** O cadastro em jogo, do lado da tela. */
export interface CustomerDecisionParty {
  ref: string;
  name: string;
  /** O valor do campo em disputa NESTE cadastro (telefone, e-mail ou documento). */
  value: string;
}

export type CustomerDecisionKind = "contact_conflict" | "contact_change";
export type CustomerDecisionField = "phone" | "email" | "tax_id";

export interface CustomerDecision {
  kind: CustomerDecisionKind;
  field: CustomerDecisionField;
  /** O que o operador digitou — o valor que está pedindo passagem. */
  typed: string;
  /** Quem está na comanda agora. */
  current: CustomerDecisionParty | null;
  /** Quem já é dono do valor digitado (só em `contact_conflict`). */
  other: CustomerDecisionParty | null;
}

export interface CustomerDecisionCopy {
  title: string;
  body: string;
  /** Assumir a mudança. */
  confirmLabel: string;
  confirmIcon: string;
  /** Voltar ao que estava — nunca "Cancelar" genérico: diz o que fica. */
  cancelLabel: string;
  cancelIcon: string;
}

/** Como o campo se chama no balcão. `tax_id` é fiscal e nunca vira correção. */
const FIELD_LABEL: Record<CustomerDecisionField, string> = {
  phone: "WhatsApp",
  email: "e-mail",
  tax_id: "CPF/CNPJ",
};

/** O `field` do dialeto de erro (`customer_phone`) traduzido para o da tela. */
const FIELD_FROM_SERVER: Record<string, CustomerDecisionField> = {
  customer_phone: "phone",
  customer_email: "email",
  customer_tax_id: "tax_id",
};

export function decisionFieldLabel(field: CustomerDecisionField): string {
  return FIELD_LABEL[field] || "contato";
}

/** Primeiro nome — no balcão ninguém fala o nome inteiro. */
function firstName(name: string): string {
  return (name || "").trim().split(/\s+/)[0] || "";
}

/**
 * A frase e os dois caminhos. Fala do que ACONTECE, nunca do mecanismo: o
 * operador com cliente na frente não lê explicação de sistema.
 */
export function customerDecisionCopy(decision: CustomerDecision): CustomerDecisionCopy {
  const label = decisionFieldLabel(decision.field);
  const current = decision.current;
  const other = decision.other;

  if (decision.kind === "contact_conflict") {
    const ownerName = other?.name?.trim() || "outro cliente";
    const currentName = current?.name?.trim() || "o cliente da comanda";
    return {
      title: `Este ${label} já é de outro cadastro`,
      body: decision.typed
        ? `${decision.typed} é de ${ownerName}. Na comanda está ${currentName}.`
        : `O ${label} digitado é de ${ownerName}. Na comanda está ${currentName}.`,
      confirmLabel: `Atender ${firstName(ownerName) || ownerName}`,
      confirmIcon: "lucide:user-round-check",
      cancelLabel: `Manter ${firstName(currentName) || currentName}`,
      cancelIcon: "lucide:undo-2",
    };
  }

  const name = current?.name?.trim() || "o cliente";
  const from = current?.value?.trim();
  return {
    title: `Trocar o ${label} de ${name}?`,
    body: from
      ? `De ${from} para ${decision.typed}. O cadastro passa a usar o novo em tudo — mensagem, acompanhamento, próxima venda.`
      : `${decision.typed} passa a ser o ${label} do cadastro — usado em mensagem, acompanhamento e próxima venda.`,
    confirmLabel: `Trocar o ${label}`,
    confirmIcon: "lucide:pencil-line",
    cancelLabel: from ? `Manter ${from}` : "Descartar a mudança",
    cancelIcon: "lucide:undo-2",
  };
}

/** Um candidato como o servidor manda em `error.candidates`. */
export interface ServerConflictCandidate {
  ref: string;
  name: string;
  phone: string;
  email: string;
  tax_id: string;
  matched_by: string[];
  is_current: boolean;
}

function partyValue(candidate: ServerConflictCandidate, field: CustomerDecisionField): string {
  if (field === "email") return candidate.email || "";
  if (field === "tax_id") return candidate.tax_id || "";
  return candidate.phone || "";
}

function party(candidate: ServerConflictCandidate, field: CustomerDecisionField): CustomerDecisionParty {
  return { ref: candidate.ref, name: candidate.name, value: partyValue(candidate, field) };
}

/**
 * Traduz a recusa 422 `customer_conflict` na decisão da tela. Devolve `null`
 * quando o servidor não mandou os dois lados: sem saber QUEM é dono do valor
 * digitado, não há saída de um toque para oferecer — e um painel sem saída é
 * pior que o toast que ele substituiria.
 */
export function conflictDecision(input: {
  field?: string | null;
  candidates?: ServerConflictCandidate[] | null;
  typed?: string;
}): CustomerDecision | null {
  const field = FIELD_FROM_SERVER[String(input.field || "")];
  if (!field) return null;
  const candidates = input.candidates || [];
  const current = candidates.find((row) => row.is_current);
  const other = candidates.find((row) => !row.is_current);
  if (!current || !other) return null;
  return {
    kind: "contact_conflict",
    field,
    typed: (input.typed || partyValue(other, field) || "").trim(),
    current: party(current, field),
    other: party(other, field),
  };
}

/**
 * Comparação de telefone que não inventa troca. O cadastro guarda E.164
 * (`+5543999990000`) e o operador digita como se fala (`43 99999-0000`): sem
 * derrubar o código do país, todo telefone já cadastrado pareceria diferente e
 * a tela perguntaria "trocar?" em cima do número que já estava certo.
 */
export function phoneKey(value: string): string {
  const digits = (value || "").replace(/\D/g, "");
  return digits.length > 11 && digits.startsWith("55") ? digits.slice(2) : digits;
}

/**
 * O contato do cliente associado vai MUDAR? Compara o que está no formulário
 * com o que o cadastro tem hoje, por dígitos (telefone) ou minúsculas (e-mail),
 * para que máscara e caixa não inventem uma troca que ninguém pediu.
 *
 * Campo VAZIO no cadastro não é troca: aí é a lacuna que o merge já preenche
 * sem perguntar. E apagar o campo no formulário também não: sumir com o
 * WhatsApp de alguém pede o Admin, não um campo esvaziado sem querer.
 */
export function contactChangeDecision(input: {
  customerRef: string;
  customerName: string;
  registeredPhone: string;
  typedPhone: string;
  registeredEmail: string;
  typedEmail: string;
}): CustomerDecision | null {
  if (!input.customerRef.trim()) return null;

  const decide = (
    field: CustomerDecisionField,
    registered: string,
    typed: string,
    normalize: (value: string) => string,
  ): CustomerDecision | null => {
    const before = (registered || "").trim();
    const after = (typed || "").trim();
    if (!before || !after) return null;
    if (normalize(before) === normalize(after)) return null;
    return {
      kind: "contact_change",
      field,
      typed: after,
      current: { ref: input.customerRef.trim(), name: input.customerName, value: before },
      other: null,
    };
  };

  return (
    decide("phone", input.registeredPhone, input.typedPhone, phoneKey)
    || decide("email", input.registeredEmail, input.typedEmail, (v) => v.toLowerCase())
  );
}
