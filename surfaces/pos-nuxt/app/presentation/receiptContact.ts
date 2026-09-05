/**
 * O contato do comprovante vira cadastro quando PERGUNTAM — e só então.
 *
 * O crime nunca foi gravar. O crime era gravar CALADO: o e-mail digitado para
 * receber a nota virava identidade do cliente sem que ninguém dissesse nada, e
 * o CPF pedido na nota entrava no cadastro pela mesma porta muda. A metade
 * defensiva cortou o vazamento; esta é a metade generosa — a tela pergunta, e a
 * resposta viaja como ordem explícita (`save_receipt_contact` /
 * `save_receipt_tax_id`).
 *
 * A matriz, IGUAL para e-mail e para CPF:
 *
 *   cliente sem o contato no cadastro   → "Salvar este e-mail no cadastro?"
 *   cliente com o MESMO contato         → nada a perguntar (silêncio é a resposta)
 *   cliente com contato DIFERENTE       → cadastro INTACTO; atualizar é ação à parte
 *   sem cliente identificado            → "Salvar como cliente?", JÁ MARCADO
 *
 * ⚠️ O "já marcado" da última linha é decisão do dono, tomada contra a
 * recomendação de nascer desmarcado ("no aperto do balcão ninguém desmarca").
 * Ele leu o trade-off e escolheu marcado. Não "corrigir" para desmarcado — o
 * que segura a promessa de transparência aqui é a VISIBILIDADE: a oferta fica à
 * vista, com a consequência escrita, e desmarcar é um toque.
 *
 * Puro de propósito: sem DOM, sem rede, sem Vue. Quem monta o popover e a linha
 * do resumo é a tela; quem decide o que perguntar é isto.
 */

import { isValidTaxId } from "~/presentation/taxId";

export type ReceiptContactField = "email" | "tax_id";

/**
 * - `none`   — não há o que perguntar (campo vazio, incompleto, ou já igual)
 * - `save`   — o cadastro existe e o campo está VAZIO: preencher lacuna
 * - `update` — o cadastro tem OUTRO valor: atualizar é ação nomeada, desmarcada
 * - `create` — ninguém identificado: "Salvar como cliente?", marcada
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

/** Como o campo se chama na tela. `cpf` fica em português: é nome próprio. */
const FIELD_COPY: Record<ReceiptContactField, { noun: string }> = {
  email: { noun: "e-mail" },
  tax_id: { noun: "CPF" },
};

const EMPTY: Omit<ReceiptContactOffer, "field" | "typed" | "onFile" | "customerName"> = {
  kind: "none",
  defaultChecked: false,
  title: "",
  hint: "",
  confirmLabel: "",
  summaryLine: "",
};

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

  // Sem cliente identificado: a única identidade que existe é a que o
  // comprovante carrega. JÁ MARCADO — decisão do dono.
  if (!customer) {
    return {
      ...base,
      kind: "create",
      defaultChecked: true,
      title: "Salvar como cliente?",
      hint: `Nasce um cadastro novo com este ${copy.noun}. Desmarque para vender sem cadastrar.`,
      confirmLabel: "Salvar como cliente",
      summaryLine: `Um cadastro novo será criado com este ${copy.noun}.`,
    };
  }

  // Já é o mesmo: silêncio é a resposta certa. Perguntar aqui seria ruído.
  if (onFile && onFile === typed) {
    return { ...base, ...EMPTY };
  }

  const quem = firstName(customerName) || "cliente";

  if (!onFile) {
    return {
      ...base,
      kind: "save",
      defaultChecked: false,
      title: `Salvar este ${copy.noun} no cadastro de ${quem}?`,
      hint: `Hoje o cadastro não tem ${copy.noun}.`,
      confirmLabel: "Salvar no cadastro",
      summaryLine: `O ${copy.noun} será salvo no cadastro de ${quem}.`,
    };
  }

  // DIVERGE: o padrão é não tocar em nada. A nota vai para o informado e o
  // cadastro fica como está — "a pessoa pode querer enviar para outro e-mail".
  return {
    ...base,
    kind: "update",
    defaultChecked: false,
    title: `Atualizar o ${copy.noun} do cadastro de ${quem}?`,
    hint: `Hoje: ${onFile}. A nota vai para o informado de qualquer jeito; o cadastro só muda se você mandar.`,
    confirmLabel: "Atualizar o cadastro",
    summaryLine: `O ${copy.noun} do cadastro de ${quem} será atualizado para este.`,
  };
}

export interface ReceiptSaveOffersInput {
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
  const email = normalizeReceiptValue("email", state.receiptEmail);
  const taxId = normalizeReceiptValue("tax_id", state.wantsCpfOnInvoice ? state.invoiceTaxId : "");
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
