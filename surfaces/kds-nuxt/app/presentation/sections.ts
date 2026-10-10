// As seções da Cozinha na barra lateral e na barra inferior (prévia v4,
// `cozinha-estacao4.html` e `cozinha-celular4.html`).
//
// Conceito (dono, 09/10/2026): cada item da operação é uma ESTAÇÃO DA CASA, pelo nome
// que ela tem no cadastro (Cafés, Lanches, Encomendas…), e leva à bancada dela
// (`/<ref>`). Estação é um posto de preparo específico: não existe estação chamada
// "Preparo", e por isso não há item genérico "Preparo". A Saída é o atalho para a
// coluna Saída do Gestor (SUITE-UX §15: a Cozinha não tem tela de Saída). Abaixo, na
// barra lateral, o Painel de retirada; no pé, Ajustes (densidade e som da estação).
//
// A lista vem do servidor (o índice das estações), nunca fixa no código.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

/** Quantas seções a barra inferior mostra antes do "Mais" (regra da suíte: 3 a 5 vagas
 *  ao todo; aqui 4 seções + "Mais"). O "Mais" existe sempre (Ajustes nunca cabe nas
 *  quatro): abre a gaveta, com o resto e o menu do operador (Bloquear, trocar). */
export const KDS_BAR_SECTIONS = 4;

export interface KdsStationNav {
  ref: string;
  name: string;
  /** `prep` ou `picking` (a de Saída não entra aqui: é o item Saída). */
  type: string;
  /** Pedidos ativos nela. Zero não é selo. */
  count: number;
}

export interface KdsSectionsInput {
  /** As estações da casa, na ordem do cadastro. */
  stations: readonly KdsStationNav[];
  /**
   * A estação que vai à frente na barra inferior: a aberta agora ou, fora do quadro, a
   * deste dispositivo. A barra lateral não reordena (as teclas Alt 1…9 seguem o cadastro).
   */
  priorityRef: string;
  /** A coluna Saída do Gestor; vazio sem a URL do Gestor. */
  exitUrl: string;
  /** Pedidos prontos para sair (a estação de Saída do cadastro). */
  exitCount: number;
  /** A barra inferior não leva o Painel de retirada (é tela de TV, não de bolso). */
  place: "rail" | "bar";
}

/** A chave da seção de uma estação. É o que o item atual compara. */
export function stationSectionKey(ref: string): string {
  return `station:${ref}`;
}

function stationIcon(type: string): string {
  return type === "picking" ? "lucide:layers" : "lucide:flame";
}

function stationSection(station: KdsStationNav): OperatorSection {
  return {
    key: stationSectionKey(station.ref),
    label: station.name || station.ref,
    icon: stationIcon(station.type),
    to: `/${station.ref}`,
    badge: station.count > 0 ? String(station.count) : undefined,
  };
}

export function kdsSections(input: KdsSectionsInput): OperatorSection[] {
  const exit: OperatorSection | null = input.exitUrl
    ? {
        key: "exit",
        label: "Saída",
        icon: "lucide:package-check",
        to: input.exitUrl,
        badge: input.exitCount > 0 ? String(input.exitCount) : undefined,
      }
    : null;
  const settings: OperatorSection = { key: "settings", label: "Ajustes", icon: "lucide:settings-2", foot: true };

  if (input.place === "rail") {
    return [
      ...input.stations.map(stationSection),
      ...(exit ? [exit] : []),
      { key: "pickup", label: "Painel de retirada", icon: "lucide:monitor", to: "/pickup" },
      settings,
    ];
  }

  // Barra inferior: a estação aberta (ou a deste dispositivo) primeiro, as outras na
  // ordem do cadastro, e a Saída sempre à vista. O que não cabe vai para o "Mais".
  const priority = input.stations.find((station) => station.ref === input.priorityRef);
  const ordered = priority ? [priority, ...input.stations.filter((station) => station !== priority)] : [...input.stations];
  const stationSlots = Math.max(1, KDS_BAR_SECTIONS - (exit ? 1 : 0));
  return [
    ...ordered.slice(0, stationSlots).map(stationSection),
    ...(exit ? [exit] : []),
    ...ordered.slice(stationSlots).map(stationSection),
    settings,
  ];
}

/**
 * As seções que o shell da suíte (`OperatorSuiteShell`) recebe: UMA lista, com as duas
 * ordens dentro. A barra lateral (e a gaveta) lê as de `where: "rail"` na ordem do
 * cadastro; a barra inferior lê as de `where: "bar"`, com a estação aberta à frente e as
 * quatro primeiras declaradas `quick`. Ajustes mora no pé e, na barra inferior, só cabe
 * no "Mais". As chaves se repetem de propósito: a seção é a mesma nas duas barras, e o
 * item atual (`current`) acende nas duas.
 */
export function kdsShellSections(input: Omit<KdsSectionsInput, "place">): OperatorSection[] {
  const rail = kdsSections({ ...input, place: "rail" }).filter((section) => !section.foot);
  const bar = kdsSections({ ...input, place: "bar" });
  const settings = bar.find((section) => section.foot);
  return [
    ...rail.map((section) => ({ ...section, where: "rail" as const })),
    ...bar
      .filter((section) => !section.foot)
      .map((section, index) => ({
        ...section,
        where: "bar" as const,
        quick: index < KDS_BAR_SECTIONS || undefined,
      })),
    ...(settings ? [settings] : []),
  ];
}
