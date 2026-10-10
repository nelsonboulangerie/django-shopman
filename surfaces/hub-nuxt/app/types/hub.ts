// Contrato da Central — espelha `OperatorHubProjection` do Django
// (shopman/backstage/projections/hub.py). Os tiles já vêm FILTRADOS por permissão:
// se está na lista, o operador pode abrir.

export interface HubTileProjection {
  ref: string;
  label: string;
  description: string;
  /** Nome Lucide do ícone forte da superfície (DS §6), sem o prefixo `lucide:`. */
  icon: string;
  url: string;
  /** "launch" = superfície de operador (mesma aba); "external" = fora da zona, nova aba (ex.: loja do cliente). */
  kind: "launch" | "external";
  /** A parte da linha de estado que pede alguém ("1 para aceitar"); vazia quando nada pede. */
  status_attention: string;
  /** O resto da linha de estado, calmo ("11 ativos"); vazio quando o app não tem fonte. */
  status_summary: string;
  /** O estado bom e sabido ("Caixa aberto", "Aberta"): ponto verde quando nada pede alguém. */
  status_positive: string;
  /**
   * A pendência mais urgente deste app para este operador, com o link que leva ao item, ou
   * `null`. É a ação direta da linha do app; os apps com pendência vêm primeiro.
   */
  next_item: HubQueueItemProjection | null;
}

/**
 * Uma pendência (`projections/hub_queue.py`): o item exato de uma fila, com o gesto que abre
 * o lugar exato no app certo. Já vem filtrado por permissão; é a mais urgente do app.
 */
export interface HubQueueItemProjection {
  key: string;
  /** Ref do tile de destino (gestor, kds, pos, production, marketing). */
  app: string;
  app_label: string;
  kind: "order_to_accept" | "ticket_late" | "preorder_pickup" | "work_order_late" | "announcement_review" | "alert";
  title: string;
  detail: string;
  /** Começo da espera (ISO), ou vazio. */
  waiting_since: string;
  /** O prazo que importa (ISO), ou vazio. */
  due_at: string;
  /** Como o prazo entra na frase: "aceita sozinho em", "retira às", "decide até". */
  due_label: string;
  due_style: "countdown" | "clock" | "";
  /** O prazo na hora da loja ("10:15"), para `due_style === "clock"`. */
  due_clock: string;
  /** "since": há quanto espera; "until": quanto falta para o prazo. */
  time_mode: "since" | "until";
  /** Passou da meta, ou o prazo está perto: o tempo vai em âmbar. */
  attention: boolean;
  action_label: string;
  url: string;
  slack_seconds: number;
}

/** A fila das filas resumida: os itens vão na linha de cada app (`next_item`). */
export interface HubQueueProjection {
  /** Quantas pendências o operador tem, somando todos os apps. */
  total_count: number;
  /** A hora do servidor quando a fila foi montada (ISO), para contar o tempo sem depender do relógio do dispositivo. */
  server_now: string;
}

export interface OperatorHubProjection {
  operator_name: string;
  tiles: HubTileProjection[];
  queue: HubQueueProjection;
  /** O nome inteiro da casa (`Shop.name`), para "Shopman · Nelson Boulangerie". */
  shop_name: string;
}

export interface HubResponse {
  hub: OperatorHubProjection;
}
