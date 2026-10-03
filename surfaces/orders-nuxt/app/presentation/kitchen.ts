// Presentation — a Cozinha no cartão do Gestor (SUITE-UX §15: uma Saída só, no Gestor).
//
// A Saída da Cozinha mostrava, por pedido, em que pé cada estação estava, dava o
// "Pronto" da estação sem tela e devolvia à cozinha um ticket concluído. Isso mora
// agora no cartão do Gestor: o progresso por estação ("Falta Cafés") no Preparo, o
// "Pronto de Lanches" para a estação que só recebe papel, e o "Voltar para Lanches"
// no menu do pedido pronto. Puro: quem decide o que pode é o servidor
// (`KitchenProgressProjection`); aqui se monta só o que a tela diz.
import type { KitchenProgressProjection, KitchenStationProjection } from "~/generated/ordersContract";

export type KitchenChipTone = "done" | "working" | "waiting" | "alert";

export interface KitchenChipView {
  ref: string;
  /** O nome da estação ("Lanches"). */
  station: string;
  /** O que está acontecendo nela: "pronto", "em preparo", "impresso às 10:42"… */
  detail: string;
  tone: KitchenChipTone;
  icon: string;
  /** Mostra o "Pronto de <estação>" (estação sem tela com ticket aberto). */
  canMarkReady: boolean;
  /** Itens retirados depois do disparo, por extenso ("1 item cancelado"). */
  cancelledNote: string;
}

/** O que o chip da estação diz, e com que peso (a mesma régua da Saída da Cozinha).
 *
 *  - pronto: verde e um ✓;
 *  - estação sem tela com papel que não saiu: vermelho, porque ninguém na bancada
 *    sabe do pedido e alguém precisa ir até lá;
 *  - estação sem tela, papel na bancada: o horário do papel;
 *  - estação de tela: o estado, neutro. */
export function kitchenChipView(station: KitchenStationProjection): KitchenChipView {
  const cancelledNote = station.cancelled_items
    ? `${station.cancelled_items} ${station.cancelled_items === 1 ? "item cancelado" : "itens cancelados"}`
    : "";
  const base = { ref: station.station_ref, station: station.station_name, cancelledNote };
  if (station.state === "done") {
    return { ...base, detail: "pronto", tone: "done", icon: "lucide:check", canMarkReady: false };
  }
  if (station.prints && station.paper_failed) {
    return {
      ...base,
      detail: `${station.paper_label}: avise a estação`,
      tone: "alert",
      icon: "lucide:printer",
      canMarkReady: station.can_mark_ready,
    };
  }
  if (station.prints) {
    return {
      ...base,
      detail: station.paper_label || station.state_label,
      tone: "waiting",
      icon: "lucide:printer",
      canMarkReady: station.can_mark_ready,
    };
  }
  return {
    ...base,
    detail: station.state_label,
    tone: station.state === "in_progress" ? "working" : "waiting",
    icon: station.state === "in_progress" ? "lucide:flame" : "lucide:clock",
    canMarkReady: false,
  };
}

/** Classes do chip por tom: verde só no pronto, vermelho só no papel perdido. */
export function kitchenChipTone(tone: KitchenChipTone): string {
  if (tone === "done") return "border-success/40 bg-success/10 text-success";
  if (tone === "alert") return "border-destructive/50 bg-destructive/10 text-destructive dark:text-red-300";
  if (tone === "working") return "border-foreground/20 bg-foreground/5 text-foreground";
  return "border-border bg-card text-muted-foreground";
}

/** Os chips que o cartão mostra. Pedido pronto (todas as estações prontas) não
 *  repete "pronto" em cada uma: a coluna já diz, e o gesto que sobra (voltar à
 *  cozinha) mora no menu do pedido. */
export function kitchenChips(kitchen: KitchenProgressProjection | null | undefined): KitchenChipView[] {
  if (!kitchen || !kitchen.missing_label) return [];
  return kitchen.stations.map(kitchenChipView);
}

export interface KitchenRecallOption {
  ticketPk: number;
  stationRef: string;
  /** "Voltar para Lanches" */
  label: string;
}

/** O menu do pedido: devolver à cozinha o ticket de uma estação já pronta. */
export function kitchenRecallOptions(kitchen: KitchenProgressProjection | null | undefined): KitchenRecallOption[] {
  if (!kitchen) return [];
  return kitchen.stations
    .filter((station) => station.recall_ticket_pk != null)
    .map((station) => ({
      ticketPk: station.recall_ticket_pk as number,
      stationRef: station.station_ref,
      label: `Voltar para ${station.station_name}`,
    }));
}

/** O "Pronto" da estação sem tela neste pedido (o mesmo endpoint da Saída da Cozinha). */
export function stationReadyPath(orderPk: number, stationRef: string): string {
  return `/api/v1/backstage/kds/expedition/${orderPk}/printed-stations/${encodeURIComponent(stationRef)}/done/`;
}

/** Devolver o ticket à cozinha (o mesmo recall da estação). */
export function stationRecallPath(ticketPk: number): string {
  return `/api/v1/backstage/kds/tickets/${ticketPk}/recall/`;
}
