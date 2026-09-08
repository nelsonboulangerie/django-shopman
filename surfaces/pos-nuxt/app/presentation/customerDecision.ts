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
//      cadastro na busca e a venda parava. Aqui ele tem nome e uma saída — e
//      vale INCLUSIVE sem ninguém na comanda, que é o caso mais comum dele (a
//      venda anônima com o e-mail da nota). Ali a recusa chega com um lado só,
//      caía no formato de lista, e na lista "Atender este" nasce desabilitado
//      para dono desativado: nome à vista e nenhum botão que resolvesse.
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
  /**
   * O valor em briga veio do COMPROVANTE (e-mail da nota / CPF na nota), não do
   * painel do cliente.
   *
   * Muda a saída, não a briga. No painel o valor é identidade e descartá-lo
   * significa voltar ao do cadastro; no comprovante ele é o destino da nota que
   * o cliente pediu — e a saída certa é parar de tentar SALVAR sem tirar o valor
   * do campo.
   */
  fromReceipt?: boolean;
}

/** Um botão a mais no painel, quando o caso pede. */
export interface CustomerDecisionAction {
  label: string;
  icon: string;
  /**
   * A SEGUNDA palavra, quando o botão é destrutivo. Vazia quando não é.
   *
   * Liberar apaga o contato do cadastro desativado e não tem desfazer: a
   * fricção mora aqui, no ato, e não num passo posterior. O que a frase pode
   * prometer — que dá para reconstruir — é o rastro que o servidor grava antes
   * de apagar (`ContactRelease`).
   */
  prompt?: string;
}

/**
 * ONDE, na tela, mora o valor que brigou.
 *
 * O servidor acusa o campo no dialeto dele (`customer_email`), e a tela tem
 * DOIS e-mails e DOIS documentos: o do painel do cliente, que é identidade, e o
 * do comprovante, que é destino da nota. A recusa não distingue — quem sabe de
 * qual dos dois veio é a tela, pela mesma precedência do servidor (o campo do
 * painel primeiro; o do comprovante quando o painel está vazio).
 *
 * Sem isto o painel mostrava o telefone numa briga de e-mail, e "Manter Ana"
 * limpava o campo errado: o operador tentava de novo e batia na mesma parede.
 */
export type ConflictTypedField =
  | "customer_phone"
  | "customer_email"
  | "customer_tax_id"
  | "receipt_email"
  | "invoice_tax_id"
  | "";

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
  /**
   * A saída que o merge não dá: o dono é um cadastro DESATIVADO.
   *
   * É o botão que a tela renderiza para liberar — no painel do `inactive_owner`
   * e, na lista, em cada linha de dono desativado. Não se repete no
   * `confirmLabel`: dois botões com o mesmo rótulo fazem o próximo a mexer achar
   * que existem duas ações.
   */
  release: CustomerDecisionAction | null;
  /**
   * Confirmar exige uma SEGUNDA palavra — só onde o gesto troca identidade.
   *
   * ⚠️ O atrito é assimétrico de propósito, e o lado sem atrito é o que segura o
   * lado com atrito de pé. "Não, é só a nota" é o caso mais frequente do balcão
   * (a nota no CPF do marido) e sai num toque, sem reconfirmação: se a fricção
   * caísse no caminho comum, o operador aprenderia a clicar no reflexo e a
   * proteção viraria decoração.
   */
  requiresConfirmation: boolean;
  /** A pergunta da reconfirmação. Vazia quando não há atrito. */
  confirmPrompt: string;
}

/** Nenhum atrito no confirmar — o padrão de quase toda decisão. */
const SEM_ATRITO = { requiresConfirmation: false, confirmPrompt: "" };

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

/** O campo do dialeto de erro traduzido para o da tela. */
export function decisionFieldFromServer(field?: string | null): CustomerDecisionField | "" {
  return FIELD_FROM_SERVER[String(field || "")] || "";
}

/**
 * QUAL campo da tela brigou, e com que valor.
 *
 * A precedência é a MESMA do servidor (`fill_email = customer_email or
 * receipt_email`): o campo do painel do cliente ganha, e o do comprovante só
 * entra quando o painel está vazio. Se as duas réguas divergirem, o painel
 * nomeia um valor e a ação limpa outro — que é exatamente o beco que isto fecha.
 */
export function conflictTypedSource(input: {
  field: CustomerDecisionField | "";
  customerPhone?: string;
  customerEmail?: string;
  customerTaxId?: string;
  receiptEmail?: string;
  invoiceTaxId?: string;
}): { typedField: ConflictTypedField; typed: string } {
  const trimmed = (value?: string) => (value || "").trim();
  const pick = (
    panelField: ConflictTypedField,
    panel: string,
    receiptField: ConflictTypedField,
    receipt: string,
  ): { typedField: ConflictTypedField; typed: string } => {
    if (panel) return { typedField: panelField, typed: panel };
    if (receipt) return { typedField: receiptField, typed: receipt };
    return { typedField: panelField, typed: "" };
  };

  const phone = trimmed(input.customerPhone);
  const email = trimmed(input.customerEmail);
  const taxId = trimmed(input.customerTaxId);

  if (input.field === "phone") return { typedField: "customer_phone", typed: phone };
  if (input.field === "email") return pick("customer_email", email, "receipt_email", trimmed(input.receiptEmail));
  if (input.field === "tax_id") return pick("customer_tax_id", taxId, "invoice_tax_id", trimmed(input.invoiceTaxId));
  // Sem campo culpado não há o que nomear: sobra a ordem em que o balcão digita.
  return { typedField: "", typed: phone || email || taxId };
}

/** "É a mesma pessoa" — a saída que resolve o cadastro duplicado de vez. */
const MERGE_ACTION: CustomerDecisionAction = {
  label: "É a mesma pessoa — unificar cadastros",
  icon: "lucide:combine",
};

/** "Liberar" — a saída do contato preso num cadastro desativado.
 *
 *  Opt-in e com segunda palavra: o gesto APAGA o contato do cadastro
 *  desativado, e apagar não tem desfazer. O que a promessa de reconstrução
 *  sustenta é o rastro gravado no servidor antes do apagamento — o valor, o
 *  tipo, de qual ficha saiu, quem liberou e quando. */
function releaseAction(label: string, ownerName: string): CustomerDecisionAction {
  const de = ownerName ? ` de ${ownerName}` : " desativado";
  return {
    label: `Liberar o ${label}`,
    icon: "lucide:unlock",
    prompt: `Liberar apaga este ${label} do cadastro${de}. `
      + "Fica registrado quem liberou e o que foi solto, então dá para refazer o cadastro depois. Confirmar?",
  };
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

  const currentName = current?.name?.trim() || "o cliente da comanda";
  // Sem ninguém na comanda não há quem "manter": a venda anônima produzia
  // "Manter o" — o primeiro nome de "o cliente da comanda". O que o operador
  // faz ali é descartar o que digitou.
  const keepLabel = current
    ? `Manter ${firstName(currentName) || currentName}`
    : `Descartar este ${label}`;

  if (decision.kind === "contact_conflict") {
    const ownerName = other?.name?.trim() || "outro cliente";
    const ownerFirst = firstName(ownerName) || ownerName;

    // ⚠️ CPF que já é de OUTRO cadastro não é probabilidade, é CERTEZA: o
    // servidor sabe de quem é o documento, e o dono está nomeado ali. Então a
    // pergunta certa não é "atender o outro?" (uma escolha de mecanismo) — é a
    // única pergunta que o balcão realmente precisa responder: DE QUEM É ESTA
    // VENDA. Trocar o dono é o gesto grande e leva reconfirmação; a resposta
    // frequente — "é só a nota" — é um toque e não muda cadastro nenhum.
    //
    // PDV é superfície de OPERADOR, e por isso o dono pode ser nomeado aqui. Na
    // loja não poderia (#553): lá dizer "este CPF é do João" contaria a um
    // estranho de quem é um documento.
    if (decision.field === "tax_id") {
      return {
        title: `Este CPF é de outro cadastro`,
        body: `${decision.typed || "O CPF informado"} é de ${ownerName}. `
          + (current
            ? `Na comanda está ${currentName}.`
            : "Ninguém está identificado na comanda."),
        confirmLabel: `Sim, a venda é de ${ownerFirst}`,
        confirmIcon: "lucide:user-round-check",
        // A saída do caso comum: a nota sai no CPF pedido e o cadastro não muda.
        cancelLabel: decision.fromReceipt ? "Não, é só a nota" : keepLabel,
        cancelIcon: "lucide:undo-2",
        merge: MERGE_ACTION,
        release: null,
        requiresConfirmation: true,
        confirmPrompt: `Passar esta venda para o cadastro de ${ownerFirst}?`,
      };
    }

    return {
      title: `Este ${label} já é de outro cadastro`,
      body: decision.typed
        ? `${decision.typed} é de ${ownerName}. Na comanda está ${currentName}.`
        : `O ${label} digitado é de ${ownerName}. Na comanda está ${currentName}.`,
      confirmLabel: `Atender ${ownerFirst}`,
      confirmIcon: "lucide:user-round-check",
      cancelLabel: keepLabel,
      cancelIcon: "lucide:undo-2",
      // A terceira saída só existe quando os dois lados são cadastros VIVOS:
      // o `MergeService` recusa unificar com qualquer um deles desativado.
      merge: MERGE_ACTION,
      release: null,
      ...SEM_ATRITO,
    };
  }

  if (decision.kind === "inactive_owner") {
    // ⚠️ Aqui NÃO se oferece "atender o outro": o cadastro está desativado, e
    // nem aparece na busca. Nem "unificar": o Core recusa merge com um lado
    // inativo. A saída é soltar o contato do cadastro morto — e ela é o botão
    // `release`, uma vez só. Antes ela vinha DUAS: no `confirmLabel` e no
    // `release`, e só o primeiro era renderizado.
    const ownerName = other?.name?.trim() || "um cadastro desativado";
    return {
      title: `Este ${label} está preso num cadastro desativado`,
      body: `${decision.typed || `O ${label} digitado`} está em ${ownerName}, que não está mais ativo. `
        + (current
          ? `Liberar solta o ${label} desse cadastro e a venda segue com ${currentName}.`
          : `Liberar solta o ${label} desse cadastro e a venda segue.`),
      confirmLabel: "",
      confirmIcon: "",
      cancelLabel: keepLabel,
      cancelIcon: "lucide:undo-2",
      merge: null,
      release: releaseAction(label, ownerName),
      ...SEM_ATRITO,
    };
  }

  if (decision.kind === "candidate_list") {
    // Dono desativado na LISTA: "Atender este" não existe para ele (não aparece
    // nem na busca), e sem a liberação a linha ficava com um botão desabilitado
    // e nada mais — o operador via o nome de quem segura o contato e não tinha
    // um único botão que resolvesse.
    const hasInactive = (decision.candidates || []).some((row) => !row.is_current && row.owner_inactive);
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
      release: decision.field && hasInactive ? releaseAction(label, "") : null,
      ...SEM_ATRITO,
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
    ...SEM_ATRITO,
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

/** O valor do campo em disputa NESTE candidato — o que a liberação solta. */
export function candidateValue(
  candidate: ServerConflictCandidate,
  field: CustomerDecisionField | "",
): string {
  if (field === "email") return candidate.email || "";
  if (field === "tax_id") return candidate.tax_id || "";
  return candidate.phone || "";
}

function party(candidate: ServerConflictCandidate, field: CustomerDecisionField | ""): CustomerDecisionParty {
  return { ref: candidate.ref, name: candidate.name, value: candidateValue(candidate, field) };
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
  /** De ONDE veio o valor recusado — `conflictTypedSource` já sabe dizer.
   *
   *  Só o comprovante muda a saída: ali o valor é destino da nota, e a resposta
   *  frequente ("é só a nota") tem de sair num toque, sem tirar nada do campo. */
  typedField?: ConflictTypedField;
}): CustomerDecision | null {
  const candidates = input.candidates || [];
  if (!candidates.length) return null;
  const field = decisionFieldFromServer(input.field);
  const fromReceipt = input.typedField === "receipt_email" || input.typedField === "invoice_tax_id";
  const current = candidates.find((row) => row.is_current) || null;
  const intruders = candidates.filter((row) => !row.is_current);
  const other = intruders[0] || null;

  // Dono DESATIVADO tem copy e saída próprias: atender não dá (não aparece na
  // busca) e unificar o Core recusa. Vale INCLUSIVE sem ninguém na comanda — a
  // venda anônima é o caso mais comum dele, e ali a recusa vinha com um lado só
  // e caía na lista, onde "Atender este" nasce desabilitado. O operador via o
  // nome de quem segura o contato e nenhum botão que resolvesse.
  if (field && other?.owner_inactive) {
    return {
      kind: "inactive_owner",
      field,
      typed: (input.typed || candidateValue(other, field) || "").trim(),
      current: current ? party(current, field) : null,
      other: party(other, field),
      candidates,
      fromReceipt,
    };
  }

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
      fromReceipt,
    };
  }

  return {
    kind: "contact_conflict",
    field,
    typed: (input.typed || candidateValue(other, field) || "").trim(),
    current: party(current, field),
    other: party(other, field),
    candidates,
    fromReceipt,
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
