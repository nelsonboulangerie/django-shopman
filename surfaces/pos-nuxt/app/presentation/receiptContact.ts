/** O documento usa o dado informado; gravar no cadastro exige escolha explícita. */

import { isValidTaxId } from "~/presentation/taxId";

export type ReceiptContactField = "email" | "tax_id";

/**
 * - `none`   — não há o que perguntar (campo vazio, incompleto, ou já igual)
 * - `save`   — o cadastro existe e o campo está VAZIO: preencher lacuna
 * - `update` — o cadastro tem OUTRO valor: atualizar é ação nomeada, desmarcada
 * - `create` — ninguém identificado: "Salvar como cliente?", desmarcada
 *
 * Dado existente exige a decisão sobre associar a venda. O documento sozinho
 * não autoriza criar, completar ou trocar o cadastro.
 */
export type ReceiptContactOfferKind = "none" | "save" | "update" | "create";

export interface ReceiptContactOffer {
  kind: ReceiptContactOfferKind;
  field: ReceiptContactField;
  /** O valor digitado, normalizado (e-mail em minúsculas, documento só dígitos). */
  typed: string;
  /** O que o cadastro tem HOJE — vazio quando não tem, ou quando não há cadastro. */
  onFile: string;
  customerName: string;
  /** O padrão da caixa quando o operador ainda não tocou nela. */
  defaultChecked: boolean;
  /** A pergunta do popover. */
  title: string;
  /** A consequência, dita ANTES de acontecer. */
  hint: string;
  /** O rótulo da ação — "Salvar" e "Atualizar" não são a mesma promessa. */
  confirmLabel: string;
  /** A linha discreta do resumo do fechamento, quando marcada. */
  summaryLine: string;
  /**
   * Marcar a caixa NÃO basta: falta a segunda palavra.
   *
   * Só o CPF divergente pede isto, e o motivo é a natureza do dado — trocar o
   * CPF do cadastro é trocar a identidade fiscal de uma pessoa, não corrigir um
   * endereço. O atrito é proporcional ao dano, e é por isso que o e-mail não o
   * carrega.
   */
  requiresConfirmation: boolean;
  /** O aviso forte, dito antes da segunda palavra. Vazio quando não há atrito. */
  warning: string;
  /** A pergunta da reconfirmação — a segunda palavra que a tela cobra. */
  confirmPrompt: string;
}

export interface ReceiptContactInput {
  field: ReceiptContactField;
  /** O que está no campo do comprovante (e-mail da nota / CPF na nota). */
  typed: string;
  /** O cadastro associado à comanda, se houver. */
  customer: { name?: string; email?: string; tax_id?: string } | null;
}

function digitsOf(value: string): string {
  return String(value || "").replace(/\D/g, "");
}

/** Normaliza como o servidor normaliza — senão "igual" e "diferente" divergem. */
export function normalizeReceiptValue(field: ReceiptContactField, value: string): string {
  return field === "email"
    ? String(value || "").trim().toLowerCase()
    : digitsOf(value);
}

/**
 * O valor está COMPLETO o bastante para perguntar?
 *
 * Perguntar no meio da digitação é o defeito que faz o operador rápido fechar
 * o popover no reflexo: "a@" ainda não é endereço, "529" ainda não é documento.
 */
export function receiptValueIsAskable(field: ReceiptContactField, value: string): boolean {
  const normalized = normalizeReceiptValue(field, value);
  if (!normalized) return false;
  if (field === "tax_id") return isValidTaxId(normalized);
  // Endereço mínimo plausível: algo@algo.algo, sem espaço.
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(normalized);
}

function firstName(name: string): string {
  return String(name || "").trim().split(/\s+/)[0] || "";
}

/** Como o campo se chama na tela, e o que ele faz na nota. `cpf` fica em
 *  português: é nome próprio. */
const FIELD_COPY: Record<ReceiptContactField, { noun: string; onInvoice: string }> = {
  email: { noun: "e-mail", onInvoice: "recebe a nota" },
  tax_id: { noun: "CPF", onInvoice: "sai na nota" },
};

/**
 * A primeira frase de TODA oferta: o que acontece com a nota não depende da
 * caixa. Sem ela o operador lia "Salvar…?" e ficava sem saber se desmarcar
 * tirava o CPF da nota — ou se marcar trocava o cliente da comanda. A pergunta
 * é só sobre o cadastro; a nota já está decidida.
 */
function invoiceInvariant(field: ReceiptContactField): string {
  const copy = FIELD_COPY[field];
  return `Este ${copy.noun} ${copy.onInvoice} de qualquer jeito.`;
}

const EMPTY: Omit<ReceiptContactOffer, "field" | "typed" | "onFile" | "customerName"> = {
  kind: "none",
  defaultChecked: false,
  title: "",
  hint: "",
  confirmLabel: "",
  summaryLine: "",
  requiresConfirmation: false,
  warning: "",
  confirmPrompt: "",
};

/** Sem atrito — o padrão de toda oferta que não troca identidade fiscal. */
const SEM_ATRITO = { requiresConfirmation: false, warning: "", confirmPrompt: "" };

/** Que pergunta (se alguma) a tela deve fazer sobre este campo do comprovante. */
export function receiptContactOffer(input: ReceiptContactInput): ReceiptContactOffer {
  const { field, customer } = input;
  const typed = normalizeReceiptValue(field, input.typed);
  const onFile = normalizeReceiptValue(
    field,
    (field === "email" ? customer?.email : customer?.tax_id) || "",
  );
  const customerName = String(customer?.name || "").trim();
  const base = { field, typed, onFile, customerName };
  const copy = FIELD_COPY[field];

  if (!receiptValueIsAskable(field, input.typed)) {
    return { ...base, ...EMPTY };
  }

  // Sem cliente identificado, cadastrar também depende de marcar a oferta.
  if (!customer) {
    return {
      ...base,
      ...SEM_ATRITO,
      kind: "create",
      defaultChecked: false,
      title: "Salvar como cliente?",
      hint: `${invoiceInvariant(field)} Marque somente se quiser cadastrar o cliente. Se o dado já pertencer a um cadastro, você poderá conferir antes de associar.`,
      confirmLabel: "Salvar como cliente",
      summaryLine: `Cadastrar cliente com este ${copy.noun}; se já existir, conferir antes de associar.`,
    };
  }

  // Já é o mesmo: silêncio é a resposta certa. Perguntar aqui seria ruído.
  if (onFile && onFile === typed) {
    return { ...base, ...EMPTY };
  }

  const ownerName = firstName(customerName) || "cliente";

  if (!onFile) {
    return {
      ...base,
      ...SEM_ATRITO,
      kind: "save",
      defaultChecked: false,
      title: `Salvar este ${copy.noun} no cadastro de ${ownerName}?`,
      // O cliente da comanda NÃO muda: a caixa só decide se o cadastro dele
      // ganha o dado. Dito por inteiro, porque a dúvida no balcão era
      // exatamente "vai trocar o cliente que eu indiquei?".
      hint: `${invoiceInvariant(field)} Marcado, fica também no cadastro de ${ownerName}, `
        + `que hoje não tem ${copy.noun}. Desmarcado, vale só nesta venda.`,
      confirmLabel: "Salvar no cadastro",
      summaryLine: `O ${copy.noun} será salvo no cadastro de ${ownerName}.`,
    };
  }

  // DIVERGE: o padrão é não tocar em nada. A nota vai para o informado e o
  // cadastro fica como está — "a pessoa pode querer enviar para outro e-mail".
  const base_update = {
    ...base,
    ...SEM_ATRITO,
    kind: "update" as const,
    defaultChecked: false,
    title: `Atualizar o ${copy.noun} do cadastro de ${ownerName}?`,
    hint: `${invoiceInvariant(field)} O cadastro de ${ownerName} tem ${onFile} e só muda `
      + "se você mandar; desmarcado, vale só nesta venda.",
    confirmLabel: "Atualizar o cadastro",
    summaryLine: `O ${copy.noun} do cadastro de ${ownerName} será atualizado para este.`,
  };

  // ⚠️ O CPF divergente é o ÚNICO ponto da matriz com atrito, e é de propósito.
  // Aqui não se está corrigindo um contato: está-se trocando o documento pelo
  // qual a Receita conhece este cadastro. A oferta fica (o dono quis o conserto
  // possível no balcão), mas ela para e pergunta de novo.
  if (field !== "tax_id") return base_update;
  return {
    ...base_update,
    requiresConfirmation: true,
    warning: `Isto troca a identidade fiscal do cadastro de ${ownerName}: `
      + `o CPF ${onFile} sai e o ${typed} entra, em todas as próximas notas. `
      + "CPF não muda — se este é de outra pessoa, não atualize o cadastro.",
    confirmPrompt: `Confirmar a troca do CPF de ${ownerName}?`,
    summaryLine: `A identidade fiscal do cadastro de ${ownerName} passará de ${onFile} para ${typed}.`,
  };
}

export interface ReceiptSaveOffersInput {
  /** Cliente vinculado continua identificado mesmo durante uma falha de lookup. */
  customerRef?: string;
  /** O e-mail do COMPROVANTE (campo da nota). */
  receiptEmail: string;
  /** O e-mail digitado no PAINEL DO CLIENTE — identidade por definição. */
  customerEmail: string;
  invoiceTaxId: string;
  wantsCpfOnInvoice: boolean;
  /** O CPF digitado no painel do cliente — identidade por definição. */
  customerTaxId: string;
  customer: ReceiptContactInput["customer"];
}

/**
 * As DUAS ofertas da venda, decididas num lugar só.
 *
 * O campo do painel do cliente (`customer_email` / `customer_tax_id`) já é
 * identidade: quando o comprovante repete o que foi digitado lá, não há o que
 * perguntar — perguntar seria oferecer o que já está acontecendo. A tela e o
 * builder do intent leem esta mesma função, senão a pergunta e o payload
 * divergem e a confirmação vira mentira.
 */
export function receiptSaveOffers(state: ReceiptSaveOffersInput): {
  email: ReceiptContactOffer;
  taxId: ReceiptContactOffer;
} {
  const lookupPending = !!state.customerRef && !state.customer;
  const email = normalizeReceiptValue("email", lookupPending ? "" : state.receiptEmail);
  const taxId = normalizeReceiptValue("tax_id", !lookupPending && state.wantsCpfOnInvoice ? state.invoiceTaxId : "");
  const emailIsIdentity = Boolean(email) && email === normalizeReceiptValue("email", state.customerEmail);
  const taxIdIsIdentity = Boolean(taxId) && taxId === normalizeReceiptValue("tax_id", state.customerTaxId);
  return {
    email: receiptContactOffer({
      field: "email",
      typed: emailIsIdentity ? "" : email,
      customer: state.customer,
    }),
    taxId: receiptContactOffer({
      field: "tax_id",
      typed: taxIdIsIdentity ? "" : taxId,
      customer: state.customer,
    }),
  };
}

/**
 * A caixa está marcada?
 *
 * `override` é o que o operador tocou; `null` significa "não tocou", e aí vale
 * o padrão da oferta. Sem esta distinção o "já marcado" da venda anônima seria
 * reimposto a cada tecla, desfazendo o desmarque do operador.
 */
export function receiptContactChecked(
  offer: ReceiptContactOffer,
  override: boolean | null,
): boolean {
  if (offer.kind === "none") return false;
  return override === null ? offer.defaultChecked : override;
}

/**
 * A ordem chegou ARMADA? — a caixa marcada MAIS a segunda palavra, quando ela
 * é exigida.
 *
 * `receiptContactChecked` responde o que o interruptor mostra; isto responde o
 * que o intent pode mandar. As duas coisas coincidem em três das quatro linhas
 * da matriz, e divergem exatamente onde o atrito existe: no CPF divergente, a
 * caixa marcada sem a reconfirmação NÃO grava nada. Sem esta separação a
 * fricção seria decorativa — o interruptor bastaria, e a segunda pergunta viraria
 * um popup que o operador aprende a fechar.
 */
export function receiptContactArmed(
  offer: ReceiptContactOffer,
  override: boolean | null,
  confirmed: boolean,
): boolean {
  if (!receiptContactChecked(offer, override)) return false;
  return offer.requiresConfirmation ? confirmed : true;
}

/**
 * As linhas do resumo do fechamento — a segunda metade da promessa.
 *
 * Perguntar junto do campo não basta: quem chega ao resumo pelo teclado nunca
 * viu o popover. A confirmação aparece de novo, discreta, dizendo o que VAI
 * acontecer e como desfazer.
 */
export function receiptSaveSummary(
  entries: Array<{ offer: ReceiptContactOffer; checked: boolean }>,
): string[] {
  return entries
    .filter((entry) => entry.checked && entry.offer.kind !== "none")
    .map((entry) => entry.offer.summaryLine);
}
