/** O post do Google Meu Negócio, como o operador escolhe e como o Google mostra.
 *
 *  ⚠️ O rótulo é o que o GOOGLE mostra em pt-BR no botão do post — nunca o nome da
 *  API. O identificador (`call_to_action`) é do contrato com o servidor
 *  (`shopman/shop/services/marketing_google_post.py`), que confere cada escolha de
 *  novo antes de aprovar e antes de publicar.
 *
 *  ⚠️ Padrão é "Nenhum", e link nunca vira botão sozinho. Até 25/09/2026 todo post com
 *  link saía com "Pedir on-line", rótulo que mente quando o link não é de compra.
 *  Decisão do dono: post institucional leva "Ligar agora" ou nenhum. "Como chegar" não
 *  existe entre os botões do Google (o perfil já tem "Rotas"). */

export type GoogleCallToAction =
  | "none"
  | "book"
  | "order"
  | "shop"
  | "learn_more"
  | "sign_up"
  | "call";

export type GooglePostType = "standard" | "event" | "offer";

export type GoogleBusinessOptions = {
  publication_format: GooglePostType;
  call_to_action: GoogleCallToAction;
  event_title: string;
  event_start: string;
  event_end: string;
  offer_terms: string;
};

export const GOOGLE_CALL_TO_ACTIONS: readonly {
  value: GoogleCallToAction;
  label: string;
  hint: string;
}[] = [
  { value: "none", label: "Nenhum", hint: "Só o texto e a foto." },
  {
    value: "call",
    label: "Ligar agora",
    hint: "Liga para o telefone do perfil. Não precisa de link.",
  },
  {
    value: "learn_more",
    label: "Saiba mais",
    hint: "Leva ao link do anúncio.",
  },
  {
    value: "order",
    label: "Pedir on-line",
    hint: "Só com link de produto ou de oferta da loja.",
  },
  {
    value: "shop",
    label: "Comprar",
    hint: "Só com link de produto ou de oferta da loja.",
  },
  { value: "book", label: "Reservar", hint: "Leva ao link do anúncio." },
  {
    value: "sign_up",
    label: "Inscrever-se",
    hint: "Leva ao link do anúncio.",
  },
];

export const GOOGLE_POST_TYPES: readonly {
  value: GooglePostType;
  label: string;
  hint: string;
}[] = [
  {
    value: "standard",
    label: "Atualização",
    hint: "Novidade da casa: texto, foto e, se quiser, um botão.",
  },
  {
    value: "event",
    label: "Evento",
    hint: "Com título, início e fim. Some do perfil quando o evento termina.",
  },
  {
    value: "offer",
    label: "Oferta",
    hint: "Nasce da promoção da campanha: título e validade vêm dela. O Google mostra o botão “Ver oferta”.",
  },
];

const CALL_TO_ACTION_REFS = new Set(
  GOOGLE_CALL_TO_ACTIONS.map((item) => item.value),
);
const POST_TYPE_REFS = new Set(GOOGLE_POST_TYPES.map((item) => item.value));

export function googleCallToActionLabel(value: unknown): string {
  const ref = String(value || "none");
  if (ref === "none") return "";
  return GOOGLE_CALL_TO_ACTIONS.find((item) => item.value === ref)?.label || "";
}

export function googlePostTypeLabel(value: unknown): string {
  return (
    GOOGLE_POST_TYPES.find((item) => item.value === String(value || ""))
      ?.label || "Atualização"
  );
}

/** Botão que leva a um link; "Ligar agora" usa o telefone do perfil. */
export function googleCallToActionNeedsLink(value: GoogleCallToAction): boolean {
  return value !== "none" && value !== "call";
}

/** As opções guardadas no anúncio/modelo, completas e sem valor inventado. */
export function googleBusinessOptions(
  variant: Record<string, unknown> | undefined,
): GoogleBusinessOptions {
  const raw = variant || {};
  const format = String(raw.publication_format || "standard");
  const action = String(raw.call_to_action || "none");
  return {
    publication_format: (POST_TYPE_REFS.has(format as GooglePostType)
      ? format
      : "standard") as GooglePostType,
    call_to_action: (CALL_TO_ACTION_REFS.has(action as GoogleCallToAction)
      ? action
      : "none") as GoogleCallToAction,
    event_title: String(raw.event_title || ""),
    event_start: String(raw.event_start || ""),
    event_end: String(raw.event_end || ""),
    offer_terms: String(raw.offer_terms || ""),
  };
}

/** O que viaja na aprovação: só o que o tipo escolhido usa. Campo de outro tipo
 *  seria recusado pelo servidor ("uma opção que esta plataforma não consegue
 *  aplicar"), então nem sai daqui. */
export function googleBusinessEdits(
  options: GoogleBusinessOptions,
): Record<string, string> {
  const edits: Record<string, string> = {
    publication_format: options.publication_format,
  };
  if (options.publication_format !== "offer") {
    edits.call_to_action = options.call_to_action;
  }
  if (options.publication_format === "event") {
    edits.event_title = options.event_title.trim();
    edits.event_start = options.event_start;
    edits.event_end = options.event_end;
  }
  if (options.publication_format === "offer" && options.offer_terms.trim()) {
    edits.offer_terms = options.offer_terms.trim();
  }
  return edits;
}

/** A variante do Google para a prévia: as opções da revisão sobre as do modelo. */
export function withGoogleBusinessEdits(
  platformContent: Record<string, Record<string, unknown>> | undefined,
  options: GoogleBusinessOptions,
): Record<string, Record<string, unknown>> {
  const merged = { ...(platformContent || {}) };
  const base = { ...(merged.google_business || {}) };
  for (const key of [
    "publication_format",
    "call_to_action",
    "event_title",
    "event_start",
    "event_end",
    "offer_terms",
  ]) {
    Reflect.deleteProperty(base, key);
  }
  const edits = googleBusinessEdits(options);
  for (const [key, value] of Object.entries(edits)) {
    if (value) base[key] = value;
  }
  merged.google_business = base;
  return merged;
}

/** "sáb., 27/09, 08:00 – 12:00" — o período como o operador confere. */
export function googlePeriodLabel(start: unknown, end: unknown): string {
  const first = parseLocal(start);
  const last = parseLocal(end);
  if (!first || !last) return "";
  const day = new Intl.DateTimeFormat("pt-BR", {
    weekday: "short",
    day: "2-digit",
    month: "2-digit",
  });
  const hour = new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const sameDay = first.toDateString() === last.toDateString();
  return sameDay
    ? `${day.format(first)}, ${hour.format(first)} – ${hour.format(last)}`
    : `${day.format(first)}, ${hour.format(first)} – ${day.format(last)}, ${hour.format(last)}`;
}

/** Hora LOCAL da loja, sem fuso ("2026-09-27T08:00"): é o que o Google recebe. */
function parseLocal(value: unknown): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(
    String(value || ""),
  );
  if (!match) return null;
  const [, y, mo, d, h, mi] = match.map(Number) as number[];
  return new Date(y!, mo! - 1, d!, h!, mi!);
}
