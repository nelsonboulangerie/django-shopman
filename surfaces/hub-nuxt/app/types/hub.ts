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
  /** Quantas coisas a `status_attention` conta: o número no canto do ícone. Zero: nada pede alguém. */
  attention_count: number;
  /** O resto da linha de estado, calmo ("11 ativos"); vazio quando o app não tem fonte. */
  status_summary: string;
  /** O estado bom e sabido ("Caixa aberto", "Aberta"): ponto verde quando nada pede alguém. */
  status_positive: string;
}

/** A fila das filas resumida: só quantas pendências há (#2362: nenhum item viaja). */
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
