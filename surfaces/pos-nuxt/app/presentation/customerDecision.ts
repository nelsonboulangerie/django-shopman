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

//   3. `inactive_owner` — o valor digitado está preso num cadastro DESATIVADO.
//      O resolve do servidor só enxerga cliente ativo, mas os UNIQUEs do banco
//      enxergam todos: o operador via "já é de outro cadastro", não achava esse
//      cadastro na busca e a venda parava. Aqui ele tem nome e uma saída.
//
//   4. `candidate_list` — dois ou mais intrusos, por campos diferentes. Não há
//      UM campo culpado para nomear, e antes disso a recusa caía num toast que
//      sumia. O payload rico já vinha do servidor: a tela mostra a lista.
//
// E a terceira saída, que vale para o conflito de contato: os dois cadastros
// são a MESMA pessoa. Nem atender o outro, nem manter quem está — unificar.

export type CustomerDecisionKind =
  | "contact_conflict"
  | "contact_change"
  | "inactive_owner"
  | "candidate_list";
export type CustomerDecisionField = "phone" | "email" | "tax_id";

export interface CustomerDecision {
  kind: CustomerDecisionKind;
  /** Vazio quando não há UM campo culpado (`candidate_list`). */
  field: CustomerDecisionField | "";
  /** O que o operador digitou — o valor que está pedindo passagem. */
  typed: string;
  /** Quem está na comanda agora. */
  current: CustomerDecisionParty | null;
  /** Quem já é dono do valor digitado (só quando há UM dono). */
  other: CustomerDecisionParty | null;
  /** Todos os lados, como o servidor mandou — a lista de `candidate_list`. */
  candidates?: ServerConflictCandidate[];
}

/** Um botão a mais no painel, quando o caso pede. */
export interface CustomerDecisionAction {
  label: string;
  icon: string;
}

export interface CustomerDecisionCopy {
  title: string;
  body: string;
  /** Assumir a mudança. Vazio em `candidate_list`: lá a escolha é por linha. */
  confirmLabel: string;
  confirmIcon: string;
  /** Voltar ao que estava — nunca "Cancelar" genérico: diz o que fica. */
  cancelLabel: string;
  cancelIcon: string;
  /** A TERCEIRA saída: os dois cadastros são a MESMA pessoa. */
  merge: CustomerDecisionAction | null;
  /** A saída que o merge não dá: o dono é um cadastro desativado. */
  release: CustomerDecisionAction | null;
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

export function decisionFieldLabel(field: CustomerDecisionField | ""): string {
  return FIELD_LABEL[field as CustomerDecisionField] || "contato";
}

/** "É a mesma pessoa" — a saída que resolve o cadastro duplicado de vez. */
const MERGE_ACTION: CustomerDecisionAction = {
  label: "É a mesma pessoa — unificar cadastros",
  icon: "lucide:combine",
};

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

  const currentName = current?.name?.trim() || "o cliente da comanda";
  const keepLabel = `Manter ${firstName(currentName) || currentName}`;

  if (decision.kind === "contact_conflict") {
    const ownerName = other?.name?.trim() || "outro cliente";
    return {
      title: `Este ${label} já é de outro cadastro`,
      body: decision.typed
        ? `${decision.typed} é de ${ownerName}. Na comanda está ${currentName}.`
        : `O ${label} digitado é de ${ownerName}. Na comanda está ${currentName}.`,
      confirmLabel: `Atender ${firstName(ownerName) || ownerName}`,
      confirmIcon: "lucide:user-round-check",
      cancelLabel: keepLabel,
      cancelIcon: "lucide:undo-2",
      // A terceira saída só existe quando os dois lados são cadastros VIVOS:
      // o `MergeService` recusa unificar com qualquer um deles desativado.
      merge: MERGE_ACTION,
      release: null,
    };
  }

  if (decision.kind === "inactive_owner") {
    // ⚠️ Aqui NÃO se oferece "atender o outro": o cadastro está desativado, e
    // nem aparece na busca. Nem "unificar": o Core recusa merge com um lado
    // inativo. A saída é soltar o contato do cadastro morto.
    const ownerName = other?.name?.trim() || "um cadastro desativado";
    return {
      title: `Este ${label} está preso num cadastro desativado`,
      body: `${decision.typed || `O ${label} digitado`} está em ${ownerName}, que não está mais ativo. `
        + `Liberar solta o ${label} desse cadastro e a venda segue com ${currentName}.`,
      confirmLabel: `Liberar o ${label}`,
      confirmIcon: "lucide:unlock",
      cancelLabel: keepLabel,
      cancelIcon: "lucide:undo-2",
      merge: null,
      release: { label: `Liberar o ${label}`, icon: "lucide:unlock" },
    };
  }

  if (decision.kind === "candidate_list") {
    return {
      title: "Os dados apontam para cadastros diferentes",
      body: "Telefone, CPF/CNPJ e e-mail digitados são de pessoas diferentes. "
        + "Escolha quem você está atendendo, ou volte e revise os campos.",
      // Sem par confirmar/cancelar: a escolha é por LINHA, na lista.
      confirmLabel: "",
      confirmIcon: "",
      cancelLabel: keepLabel,
      cancelIcon: "lucide:undo-2",
      merge: null,
      release: null,
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
    merge: null,
    release: null,
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
  /** O dono é um cadastro DESATIVADO — invisível na busca do operador. */
  owner_inactive?: boolean;
}

function partyValue(candidate: ServerConflictCandidate, field: CustomerDecisionField | ""): string {
  if (field === "email") return candidate.email || "";
  if (field === "tax_id") return candidate.tax_id || "";
  return candidate.phone || "";
}

function party(candidate: ServerConflictCandidate, field: CustomerDecisionField | ""): CustomerDecisionParty {
  return { ref: candidate.ref, name: candidate.name, value: partyValue(candidate, field) };
}

/** Como o candidato se apresenta na LISTA: o que dele bateu com o digitado. */
export function candidateSubtitle(candidate: ServerConflictCandidate): string {
  const parts = [candidate.phone, candidate.email, candidate.tax_id].filter(Boolean);
  return parts.join(" · ");
}

/**
 * Traduz a recusa 422 `customer_conflict` na decisão da tela.
 *
 * Devolve `null` só quando não há candidato nenhum — aí não existe nada a
 * mostrar. Nos demais casos SEMPRE há painel, porque o toast que sumia era a
 * queixa: recusa que exige decisão não pode desaparecer sozinha.
 */
export function conflictDecision(input: {
  field?: string | null;
  candidates?: ServerConflictCandidate[] | null;
  typed?: string;
}): CustomerDecision | null {
  const candidates = input.candidates || [];
  if (!candidates.length) return null;
  const field = FIELD_FROM_SERVER[String(input.field || "")] || "";
  const current = candidates.find((row) => row.is_current) || null;
  const intruders = candidates.filter((row) => !row.is_current);
  const other = intruders[0] || null;

  // Sem UM campo culpado (dois ou mais intrusos, por campos diferentes) a tela
  // renderiza a LISTA: o servidor já mandou os lados, e antes disso tudo isso
  // virava um toast genérico que sumia.
  if (!field || !current || !other) {
    return {
      kind: "candidate_list",
      field,
      typed: (input.typed || "").trim(),
      current: current ? party(current, field) : null,
      other: other ? party(other, field) : null,
      candidates,
    };
  }

  return {
    // Dono DESATIVADO tem copy e saída próprias: atender não dá (não aparece na
    // busca) e unificar o Core recusa.
    kind: other.owner_inactive ? "inactive_owner" : "contact_conflict",
    field,
    typed: (input.typed || partyValue(other, field) || "").trim(),
    current: party(current, field),
    other: party(other, field),
    candidates,
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

// ---------------------------------------------------------------------------
// Depois de unificar: a única tela que diz que dá para VOLTAR atrás.
//
// O balcão unifica dois cadastros no meio de uma venda — é destrutivo, e o
// servidor já devolve o comprovante (`audit_id`) e o prazo (`undo_deadline`,
// 24h). O PDV recebia os dois e jogava fora: o operador terminava a venda sem
// saber que existe desfazer, e a janela fechava sozinha.
//
// ⚠️ Sem LINK para o Admin, e isso é decisão, não esquecimento. Desfazer exige
// `shop.manage_customers`, que o Caixa — justamente quem unifica no balcão —
// não tem: o link levaria ao 403 para a maioria de quem lê a frase. E mesmo
// para o gerente, o PDV é desktop-first e a venda está em curso; tirar alguém
// da comanda aberta para outra aba é pior do que dizer onde a tela fica. A
// frase nomeia o caminho ("Clientes → Unificações de cadastro") e o dono do
// gesto; quem tem a permissão sabe chegar lá quando a venda acabar.

/** O que a unificação moveu, como o servidor conta. */
export interface CustomerMergeMigrated {
  contact_points: number;
  orders: number;
}

function countLabel(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

/**
 * O prazo do desfazer no formato que se lê de relance, no meio de uma venda:
 * "hoje às 14:32", "amanhã às 09:05" — e a data por extenso se algum dia a
 * janela passar de 24h. Devolve vazio quando não há prazo utilizável.
 */
export function mergeUndoDeadlineLabel(raw: string | null | undefined, now: Date = new Date()): string {
  const deadline = new Date(String(raw || ""));
  if (Number.isNaN(deadline.getTime())) return "";

  const hour = deadline.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  const days = Math.round(
    (new Date(deadline.getFullYear(), deadline.getMonth(), deadline.getDate()).getTime()
      - new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime())
    / 86_400_000,
  );
  if (days === 0) return `hoje às ${hour}`;
  if (days === 1) return `amanhã às ${hour}`;
  return `${deadline.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })} às ${hour}`;
}

/**
 * A frase abaixo do "Cadastros unificados": o que mudou de dono e até quando
 * dá para voltar atrás.
 *
 * Sem prazo utilizável, o desfazer NÃO é prometido. "Dá para desfazer" sem
 * dizer até quando é meia promessa — e o prazo é a metade que importa, porque
 * ele fecha sozinho.
 */
export function customerMergeDescription(input: {
  migrated?: CustomerMergeMigrated | null;
  undoDeadline?: string | null;
  now?: Date;
}): string {
  const parts: string[] = [];

  const migrated = input.migrated;
  if (migrated) {
    const contatos = countLabel(migrated.contact_points, "contato", "contatos");
    const pedidos = countLabel(migrated.orders, "pedido", "pedidos");
    parts.push(`${contatos} e ${pedidos} passaram para este cadastro.`);
  }

  const prazo = mergeUndoDeadlineLabel(input.undoDeadline, input.now);
  if (prazo) {
    parts.push(`Dá para desfazer até ${prazo} — com o gerente, em Clientes → Unificações de cadastro.`);
  }

  return parts.join(" ");
}
