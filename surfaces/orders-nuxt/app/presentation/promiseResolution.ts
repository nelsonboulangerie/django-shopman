// Presentation — o diálogo "Resolver" da promessa em risco (WP-G08). Puro.
//
// Quem decide o que dá para fazer com o pedido sem lastro é o servidor
// (`GET orders/<ref>/promise-resolution/`): o fato, cada escolha com o detalhe, a guarda
// e o motivo dela, a mensagem ao cliente já escrita e o que conclui. Aqui só se traduz
// a leitura em desenho: as linhas do rádio, o botão que conclui e as frases de tela.
// Nenhuma régua de estoque, de dinheiro ou de permissão mora neste arquivo, e nenhuma
// frase do servidor é reescrita.
//
// Os tipos abaixo copiam a forma do contrato (`OrderPromiseResolutionProjection`)
// enquanto `~/generated/ordersContract` não os traz: quando o contrato gerado os
// tiver, eles saem daqui e passam a vir de lá.

/** Uma linha da lista final que a edição do pedido recebe (`POST orders/<ref>/edit/`). */
export interface PromiseResolutionEditItem {
  line_id: string;
  sku: string;
  qty: string;
}

/**
 * O que conclui a escolha. As cinco chaves vêm SEMPRE, vazias quando não se aplicam:
 * - `link` (trocar, remarcar): `href` é o pedido no PDV, onde o gesto mora;
 * - `edit` (tirar o item): `items` é a lista final pronta para a edição do pedido que já
 *   existe, e `payload_schema` traz o que a gravação exige (`base_revision`, a revisão
 *   que o servidor leu, e `expected_actor_id`, quem a tela leu);
 * - `cancel`: o diálogo de cancelar que já existe, com o motivo e o dinheiro.
 */
export interface PromiseResolutionConclude {
  kind: "link" | "edit" | "cancel";
  label: string;
  href: string;
  items: PromiseResolutionEditItem[];
  payload_schema: Record<string, unknown>;
}

export type PromiseResolutionKind = "swap" | "reschedule" | "remove" | "cancel";

/** Uma escolha do "O que fazer". */
export interface PromiseResolutionChoice {
  /** "swap:<sku em falta>:<sku oferecido>", "reschedule", "remove" ou "cancel". */
  key: string;
  kind: PromiseResolutionKind;
  label: string;
  /** O que há ao lado do nome: o livre da troca, a frase do dinheiro. */
  detail: string;
  enabled: boolean;
  /** Por que não pode, quando `enabled` é falso. */
  reason: string;
  /** A mensagem ao cliente desta escolha, pronta para conferir; vazia na escolha travada. */
  message: string;
  /** O `wa.me` do cliente com a mensagem; vazio quando o pedido não tem WhatsApp. */
  whatsapp_url: string;
  conclude: PromiseResolutionConclude;
  requires_manager_approval: boolean;
}

/** A resposta de `GET /api/v1/backstage/orders/<ref>/promise-resolution/`. */
export interface PromiseResolution {
  order_ref: string;
  code: string;
  customer_name: string;
  /** As frases do aviso, uma por item em falta. */
  facts: string[];
  contact: { enabled: boolean; reason: string };
  /** O interino declarado: por que copiar e chamar, e não enviar. */
  interim_note: string;
  choices: PromiseResolutionChoice[];
}

/** O que a leitura do diálogo é agora. `gone`: o pedido não está mais em risco (409). */
export type PromiseResolutionRead = "idle" | "loading" | "ready" | "error" | "gone";

export const WHAT_TO_DO_LABEL = "O que fazer";
export const COPY_MESSAGE_LABEL = "Copiar mensagem";
export const CALL_ON_WHATSAPP_LABEL = "Chamar no WhatsApp";
export const MESSAGE_COPIED = "Mensagem copiada.";
/** O rótulo do botão que conclui enquanto ninguém escolheu. */
export const PICK_FIRST_LABEL = "Escolha o que fazer";
/**
 * "Cancelar o pedido inteiro" a partir do painel: o pedido abre com `#cancel` e sobe o
 * diálogo de cancelar que já existe, com o motivo por escolher e o dinheiro escrito.
 */
export const CANCEL_HASH = "#cancel";
/** O que a tela diz quando o 409 chega sem frase. */
export const NOT_AT_RISK = "Este pedido não tem mais promessa em risco.";
/** Sem área de transferência (navegador antigo, permissão negada): o texto continua na tela. */
export const COPY_FAILED = "Não deu para copiar. Selecione a mensagem e copie à mão.";
/** O gerente assina depois do botão: dito antes, ao lado dele. */
export const MANAGER_NEXT_STEP = "Um gerente autoriza no próximo passo.";

/** O título do diálogo: o mesmo nome do aviso de página ("Promessa em risco no pedido W33"). */
export function resolutionTitle(code: string): string {
  return code ? `Promessa em risco no pedido ${code}` : "Promessa em risco";
}

/** De quem é a mensagem que se confere: o nome do cliente, como o pedido o traz. */
export function messageHeading(customerName: string): string {
  const name = customerName.trim();
  return name ? `Mensagem para ${name}` : "Mensagem para o cliente";
}

export interface ResolutionChoiceItem {
  value: string;
  label: string;
  /** O detalhe da escolha; na travada, o motivo, escrito (nunca só em `title`). */
  description?: string;
  disabled: boolean;
  "data-resolve-choice": string;
  "data-resolve-choice-kind": string;
}

/** As linhas do rádio, na ordem do servidor: trocas, remarcar, tirar, cancelar. */
export function choiceItems(
  choices: readonly PromiseResolutionChoice[],
): ResolutionChoiceItem[] {
  return choices.map((choice) => ({
    value: choice.key,
    label: choice.label,
    description:
      (choice.enabled ? choice.detail : choice.reason || choice.detail) || undefined,
    disabled: !choice.enabled,
    "data-resolve-choice": choice.key,
    "data-resolve-choice-kind": choice.kind,
  }));
}

/** A escolha marcada. Escolha travada nunca conta como marcada. */
export function pickedChoice(
  resolution: PromiseResolution | null,
  key: string,
): PromiseResolutionChoice | null {
  if (!key) return null;
  return (
    resolution?.choices.find((choice) => choice.key === key && choice.enabled) ?? null
  );
}

export interface ConcludeButton {
  label: string;
  /** Cancelar é sempre vermelho, como no menu do pedido. */
  color: "primary" | "error";
  icon: string;
  disabled: boolean;
  /** Trocar e remarcar: o destino no PDV. Vazio no que grava e no que abre outro diálogo. */
  href: string;
}

const CONCLUDE_ICONS: Record<PromiseResolutionConclude["kind"], string> = {
  link: "i-lucide-external-link",
  edit: "i-lucide-check",
  cancel: "i-lucide-ban",
};

/**
 * O botão que conclui, com o nome do que a escolha faz. Sem escolha marcada ele fica
 * travado e diz o que falta: quem decide é a pessoa, e nada vem marcado sozinho.
 */
export function concludeButton(
  choice: PromiseResolutionChoice | null,
  busy: boolean,
): ConcludeButton {
  if (!choice)
    return {
      label: PICK_FIRST_LABEL,
      color: "primary",
      icon: "i-lucide-list-checks",
      disabled: true,
      href: "",
    };
  const { conclude } = choice;
  return {
    label: conclude.label,
    color: conclude.kind === "cancel" ? "error" : "primary",
    icon: CONCLUDE_ICONS[conclude.kind],
    disabled: busy || (conclude.kind === "link" && !conclude.href),
    href: conclude.kind === "link" ? conclude.href : "",
  };
}

/**
 * A escolha grava com a assinatura de um gerente? Só a edição grava daqui: o cancelar
 * de pedido pago também vem marcado, mas quem pede o gerente é o diálogo de cancelar.
 */
export function needsManager(choice: PromiseResolutionChoice | null): boolean {
  return Boolean(
    choice && choice.conclude.kind === "edit" && choice.requires_manager_approval,
  );
}

/**
 * O que a tela diz depois de tirar o que faltava: o que foi feito e, com as palavras
 * do servidor, para onde vai o dinheiro (`detail` da escolha).
 */
export function removedSentence(choice: PromiseResolutionChoice): string {
  return ["O que faltava saiu do pedido.", choice.detail.trim()]
    .filter(Boolean)
    .join(" ");
}
