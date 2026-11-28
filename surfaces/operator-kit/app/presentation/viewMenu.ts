// "Exibir" no estreito (dono, 07/11/2026): no celular, os controles que mudam COMO a
// lista aparece (Grade ou Lista, densidade, ocultar o que não serve agora) viram UM
// botão com menu. Não são gestos primários do balcão, e roubavam a linha da busca e a
// dos filtros. É o mesmo gesto do "Exibir" das tabelas (`OperatorTableView`): um botão
// só, ícone do estado atual, o menu com cada opção marcada.
//
// Puro: a peça (`OperatorViewMenu`) só desenha o que sai daqui.

/** Uma opção de uma escolha (Grade, Lista; Compacta, Padrão, Ampla). */
export interface OperatorViewOption {
  value: string;
  label: string;
  /** Ícone `lucide:*` (o mesmo do segmentado da mesa). */
  icon: string;
}

/** Uma escolha entre opções que se excluem (a vista, a densidade). */
export interface OperatorViewChoice {
  kind: "choice";
  key: string;
  /** Título da seção no menu ("Vista", "Densidade"). */
  label: string;
  value: string;
  options: OperatorViewOption[];
  select: (value: string) => void;
}

/** Uma preferência que liga e desliga (ocultar indisponíveis). */
export interface OperatorViewToggle {
  kind: "toggle";
  key: string;
  /** O nome do gesto no menu ("Ocultar indisponíveis"). */
  label: string;
  /** O estado ligado, dito no nome do botão ("indisponíveis ocultos"). */
  onLabel: string;
  checked: boolean;
  /** Complemento do item quando ligado (por exemplo, "3 ocultos"). */
  detail?: string;
  icon: string;
  toggle: (checked: boolean) => void;
}

export type OperatorViewGroup = OperatorViewChoice | OperatorViewToggle;

export interface OperatorViewMenuItem {
  type?: "label" | "checkbox";
  label: string;
  icon?: string;
  checked?: boolean;
  onUpdateChecked?: (checked: boolean) => void;
  onSelect?: (event: Event) => void;
}

// O menu fica aberto depois da escolha: quem ajusta a vista vê o efeito e pode
// ajustar a próxima sem reabrir (o mesmo do "Exibir" das tabelas).
const keepOpen = (event: Event) => event.preventDefault();

function iconName(icon: string): string {
  return icon.startsWith("lucide:") ? `i-lucide-${icon.slice("lucide:".length)}` : icon;
}

function selected(choice: OperatorViewChoice): OperatorViewOption | undefined {
  return choice.options.find((option) => option.value === choice.value);
}

/** As seções do menu: cada escolha com o título e as opções; as preferências juntas no fim. */
export function viewMenuItems(groups: OperatorViewGroup[]): OperatorViewMenuItem[][] {
  const sections: OperatorViewMenuItem[][] = [];
  for (const group of groups) {
    if (group.kind !== "choice") continue;
    sections.push([
      { type: "label", label: group.label },
      ...group.options.map((option) => ({
        type: "checkbox" as const,
        label: option.label,
        icon: iconName(option.icon),
        checked: option.value === group.value,
        // Desmarcar a opção marcada não desfaz a escolha: uma vista sempre vale.
        onUpdateChecked: () => group.select(option.value),
        onSelect: keepOpen,
      })),
    ]);
  }
  const toggles = groups.filter((group): group is OperatorViewToggle => group.kind === "toggle");
  if (toggles.length) {
    sections.push(
      toggles.map((toggle) => ({
        type: "checkbox" as const,
        label: toggle.checked && toggle.detail ? `${toggle.label} (${toggle.detail})` : toggle.label,
        icon: iconName(toggle.icon),
        checked: toggle.checked,
        onUpdateChecked: (checked: boolean) => toggle.toggle(checked),
        onSelect: keepOpen,
      })),
    );
  }
  return sections;
}

/** O ícone do botão: o estado da primeira escolha (a vista), que é o que mais se vê. */
export function viewMenuIcon(groups: OperatorViewGroup[]): string {
  const first = groups.find((group): group is OperatorViewChoice => group.kind === "choice");
  const option = first ? selected(first) : undefined;
  return iconName(option?.icon ?? "lucide:sliders-horizontal");
}

/** Alguma preferência ligada? O botão fica marcado (`soft`), como o "Exibir" com coluna oculta. */
export function viewMenuHasToggleOn(groups: OperatorViewGroup[]): boolean {
  return groups.some((group) => group.kind === "toggle" && group.checked);
}

/** O nome do botão diz o estado inteiro: "Exibir: Grade, Padrão, indisponíveis ocultos". */
export function viewMenuLabel(groups: OperatorViewGroup[]): string {
  const parts: string[] = [];
  for (const group of groups) {
    if (group.kind === "choice") {
      const option = selected(group);
      if (option) parts.push(option.label);
    } else if (group.checked) {
      parts.push(group.detail ? `${group.onLabel} (${group.detail})` : group.onLabel);
    }
  }
  return parts.length ? `Exibir: ${parts.join(", ")}` : "Exibir";
}
