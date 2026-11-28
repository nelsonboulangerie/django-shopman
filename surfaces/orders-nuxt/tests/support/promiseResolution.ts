// A leitura do diálogo "Resolver" (WP-G08), com as quatro famílias de escolha, na forma
// que o servidor manda (`GET orders/<ref>/promise-resolution/`): `conclude` sempre com
// as cinco chaves, e a escolha fechada com o motivo e o resto vazio. A tela não
// reescreve nenhuma frase.
import type {
  PromiseResolution,
  PromiseResolutionChoice,
  PromiseResolutionConclude,
} from "../../app/presentation/promiseResolution";

export const RESOLUTION_REF = "WEB-2611-G8G-N75";
const WHATSAPP = "https://wa.me/5543999990000";
const HELLO =
  "Oi, Nelson! Aqui é da Nelson Boulangerie 💛 A Focaccia Cebola, Bacon e Tomilho do seu pedido N75 não vai ficar pronta hoje, e sinto muito por isso.";

export const SWAP_MESSAGE = `${HELLO} Posso trocar por Campagne Passas & Castanhas? Me avisa e eu ajusto por aqui ✨`;
export const RESCHEDULE_MESSAGE = `${HELLO} Posso remarcar o seu pedido para outro dia? Me diz qual fica melhor para você ✨`;
export const REMOVE_MESSAGE = `${HELLO} Posso tirar esse item do pedido e devolver R$ 44,00 pelo Pix? Me avisa e eu ajusto por aqui ✨`;
export const CANCEL_MESSAGE = `${HELLO} Se preferir, cancelo o pedido e devolvo R$ 44,00 pelo Pix. Me avisa como fica melhor ✨`;

const whatsapp = (message: string) => `${WHATSAPP}?text=${encodeURIComponent(message)}`;

export const EDIT_ITEMS = [{ line_id: "line-2", sku: "CROISSANT", qty: "2" }];
/** O que a rota de edição exige, como o servidor manda: a revisão lida e quem a tela leu. */
export const EDIT_PAYLOAD = { base_revision: "edit-rev-1", expected_actor_id: 7 };

/** `conclude` vem SEMPRE com as cinco chaves, vazias quando não se aplicam. */
export function concludeOf(over: Partial<PromiseResolutionConclude> & Pick<PromiseResolutionConclude, "kind" | "label">): PromiseResolutionConclude {
  return { href: "", items: [], payload_schema: {}, ...over };
}

/** Escolha fechada, como o servidor a manda: o motivo, e o resto vazio. */
export function closed(choice: PromiseResolutionChoice, reason: string): PromiseResolutionChoice {
  return {
    ...choice, enabled: false, reason, message: "", whatsapp_url: "",
    conclude: { ...choice.conclude, href: "", items: [] },
  };
}

export function swapChoice(over: Partial<PromiseResolutionChoice> = {}): PromiseResolutionChoice {
  return {
    key: "swap:FOCACCIA-CBT:CAMPAGNE-PC", kind: "swap", label: "Trocar por Campagne Passas & Castanhas",
    detail: "6 disponíveis hoje", enabled: true, reason: "", message: SWAP_MESSAGE,
    whatsapp_url: whatsapp(SWAP_MESSAGE),
    conclude: concludeOf({ kind: "link", label: "Trocar no PDV", href: `https://pdv.example.test/preorders/${RESOLUTION_REF}?swap=FOCACCIA-CBT` }),
    requires_manager_approval: false, ...over,
  };
}

// ⚠️ O nome fechado desta escolha no contrato termina em "fornada". A trava de
// vocabulário do kit (`operator-kit/tests/guardrails.vocabulary.test.ts`: na tela do
// operador o objeto é "lote", dono, 22/09/2026) reprova a palavra em qualquer arquivo
// dos apps de operador, este incluído. O rótulo de verdade vem do servidor e a tela não
// o escreve em lugar nenhum; o exemplo daqui usa "lote" até a coordenação decidir o nome.
export function rescheduleChoice(over: Partial<PromiseResolutionChoice> = {}): PromiseResolutionChoice {
  return {
    key: "reschedule", kind: "reschedule", label: "Remarcar para outro dia ou outro lote", detail: "", enabled: true,
    reason: "", message: RESCHEDULE_MESSAGE, whatsapp_url: whatsapp(RESCHEDULE_MESSAGE),
    conclude: concludeOf({ kind: "link", label: "Remarcar no PDV", href: `https://pdv.example.test/preorders/${RESOLUTION_REF}` }),
    requires_manager_approval: false, ...over,
  };
}

export function removeChoice(over: Partial<PromiseResolutionChoice> = {}): PromiseResolutionChoice {
  return {
    key: "remove", kind: "remove", label: "Tirar só o item que falta e devolver a diferença",
    detail: "R$ 44,00 serão estornados ao Pix do cliente.", enabled: true, reason: "", message: REMOVE_MESSAGE,
    whatsapp_url: whatsapp(REMOVE_MESSAGE),
    conclude: concludeOf({ kind: "edit", label: "Tirar o item", items: EDIT_ITEMS, payload_schema: EDIT_PAYLOAD }),
    requires_manager_approval: true, ...over,
  };
}

export function cancelChoice(over: Partial<PromiseResolutionChoice> = {}): PromiseResolutionChoice {
  return {
    key: "cancel", kind: "cancel", label: "Cancelar o pedido inteiro",
    detail: "R$ 62,00 serão estornados ao Pix do cliente.", enabled: true, reason: "", message: CANCEL_MESSAGE,
    whatsapp_url: whatsapp(CANCEL_MESSAGE),
    conclude: concludeOf({ kind: "cancel", label: "Cancelar pedido" }),
    // Pedido pago: quem pede o gerente é o diálogo de cancelar, não este.
    requires_manager_approval: true, ...over,
  };
}

export function resolution(over: Partial<PromiseResolution> = {}): PromiseResolution {
  return {
    order_ref: RESOLUTION_REF, code: "N75", customer_name: "Nelson Dias",
    facts: ["Faltam 4x Focaccia Cebola, Bacon e Tomilho. O lote de hoje foi cancelado."],
    contact: { enabled: true, reason: "" },
    notice: {
      enabled: true,
      kind: "item_missing",
      label: "Faltou um item",
      note: 'Primeiro, avise o cliente com o aviso "Faltou um item". Quando ele responder, mande a proposta da escolha.',
      reason: "",
      line_ids: ["L1"],
    },
    choices: [swapChoice(), rescheduleChoice(), removeChoice(), cancelChoice()],
    ...over,
  };
}
