// As seções da Cozinha no rail da suíte e na barra do polegar (prévia v4,
// `cozinha-estacao4.html` e `cozinha-celular4.html`). Em cima, a operação: Estações,
// Preparo (a estação deste dispositivo), Saída (a coluna Saída do Gestor, SUITE-UX §15:
// a Cozinha não tem tela de Saída, o item é um atalho para lá) e o Painel de retirada.
// No pé, Ajustes (densidade da grade e a data de consulta).
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";

export interface KdsSectionsInput {
  /** A estação deste dispositivo (a aberta agora ou a última aberta). */
  stationRef: string;
  /** Pedidos ativos nela. Zero não é selo. */
  prepCount: number;
  /** A coluna Saída do Gestor; vazio sem a URL do Gestor. */
  exitUrl: string;
  /** Pedidos prontos para sair (a estação de Saída do cadastro). */
  exitCount: number;
  /** A barra do polegar não leva o Painel de retirada (é tela de TV, não de bolso)
   *  e começa pelo Preparo, como na prévia do celular. */
  place: "rail" | "bar";
}

export function kdsSections(input: KdsSectionsInput): OperatorSection[] {
  const sections: OperatorSection[] = [];
  if (input.place === "bar" && input.stationRef) sections.push(prepSection(input));
  sections.push({ key: "stations", label: "Estações", icon: "lucide:layout-grid", to: "/" });
  if (input.place === "rail" && input.stationRef) sections.push(prepSection(input));
  if (input.exitUrl) {
    sections.push({
      key: "exit",
      label: "Saída",
      icon: "lucide:package-check",
      to: input.exitUrl,
      badge: input.exitCount > 0 ? String(input.exitCount) : undefined,
      badgeLabel:
        input.exitCount > 0
          ? plural(input.exitCount, "pedido pronto para sair", "pedidos prontos para sair")
          : undefined,
    });
  }
  if (input.place === "rail") {
    sections.push({ key: "pickup", label: "Painel de retirada", icon: "lucide:monitor", to: "/pickup" });
  }
  sections.push({ key: "settings", label: "Ajustes", icon: "lucide:settings-2", foot: true });
  return sections;
}

function prepSection(input: KdsSectionsInput): OperatorSection {
  return {
    key: "prep",
    label: "Preparo",
    icon: "lucide:flame",
    to: `/${input.stationRef}`,
    badge: input.prepCount > 0 ? String(input.prepCount) : undefined,
    badgeLabel:
      input.prepCount > 0 ? plural(input.prepCount, "pedido nesta estação", "pedidos nesta estação") : undefined,
  };
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}
