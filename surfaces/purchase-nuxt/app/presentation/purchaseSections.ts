// As seções do Compras no shell da suíte (WP-FASE2-UX-OPERADOR, onda do Compras).
//
// Cada seção é uma rota: Painel (`/`), Comprar (`/buy`), Receber (`/receive`), Base
// (`/base/<cadastro>`) e Contar estoque (`/count`). A ordem é a da barra lateral e das
// teclas: Alt+1 a Alt+4 seguem as de antes, e Contar estoque entra no fim, Alt+5, para
// nenhuma tecla trocar de lugar (dono, 03/11/2026: memória muscular).
//
// O modelo de navegação (dono, 31/10/2026) dá a cada seção a forma da tela, que nunca
// vira palavra na tela:
//   · chão (de pé, no estoque ou na porta, com o celular): Painel, Comprar, Receber e
//     Contar estoque. São elas a barra de baixo do celular (`quick`). A contagem deixou
//     de ser tarefa escondida no ⋯ da Base: é seção (modelo de 31/10, "Contagem → chão");
//   · escritório (no computador): a Base, com os cadastros (Insumos, Fornecedores) e o
//     lançamento de custos.
// A Base tem sub-seções com rota própria, escolhidas na toolbar da tela.
//
// Puro: o número de reposições urgentes e o de pendências da entrada chegam prontos.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";
import type { PurchaseBaseView } from "~/types/purchase";

export interface PurchaseSectionsInput {
  /** Insumos que pedem reposição urgente (o ponto em Comprar). */
  urgentMaterials: number;
  /** Itens travados da entrada aberta (o número em Receber). */
  receivePending: number;
}

export const PURCHASE_BASE_SECTIONS: ReadonlyArray<{
  key: PurchaseBaseView;
  label: string;
  icon: string;
  to: string;
  /** Só objetos estáveis entram na troca de cadastro. Tarefas têm entrada própria. */
  record?: boolean;
}> = [
  {
    key: "materials",
    label: "Insumos",
    icon: "i-lucide-package-search",
    to: "/base/materials",
    record: true,
  },
  {
    key: "suppliers",
    label: "Fornecedores",
    icon: "i-lucide-truck",
    to: "/base/suppliers",
    record: true,
  },
  {
    key: "costs",
    label: "Lançar custos",
    icon: "i-lucide-calculator",
    to: "/base/costs",
  },
];

/** O endereço da contagem de estoque, seção própria desde o modelo de navegação. */
export const COUNT_PATH = "/count";

/** As duas coleções irmãs da Base. Custos é tarefa, não aba. */
export const PURCHASE_BASE_RECORD_SECTIONS = PURCHASE_BASE_SECTIONS.filter((section) => section.record);

/** O endereço de uma sub-seção da Base. */
export function baseSectionPath(key: PurchaseBaseView): string {
  return PURCHASE_BASE_SECTIONS.find((section) => section.key === key)?.to ?? "/base/materials";
}

/** A sub-seção da Base de uma rota (`/base/suppliers/MOINHO` → `suppliers`). */
export function baseSectionOf(path: string): PurchaseBaseView | null {
  const match = /^\/base\/([a-z]+)/.exec(path);
  const key = match?.[1];
  return PURCHASE_BASE_SECTIONS.some((section) => section.key === key) ? (key as PurchaseBaseView) : null;
}

/** A trilha da tabela de Insumos (`useRecordTrail`): o "‹ 3 de 18 ›" do insumo aberto. */
export const MATERIALS_TRAIL = "purchase-materials";
/** A trilha da tabela de Fornecedores. */
export const SUPPLIERS_TRAIL = "purchase-suppliers";
/** A trilha dos itens da entrada em conferência (o item aberto no Receber). */
export const RECEIPT_LINES_TRAIL = "purchase-receipt-lines";

export function materialPath(sku: string): string {
  return `/base/materials/${encodeURIComponent(sku)}`;
}

export function supplierPath(ref: string): string {
  return `/base/suppliers/${encodeURIComponent(ref)}`;
}

/** "1 reposição urgente", "3 reposições urgentes". */
export function urgentLabel(count: number): string {
  return `${count} ${count === 1 ? "reposição urgente" : "reposições urgentes"}`;
}

/** As seções do chão: as da barra de baixo do celular. */
export const PURCHASE_FLOOR_SECTIONS: readonly string[] = ["panel", "buy", "receive", "count"];

export function purchaseSections({ urgentMaterials, receivePending }: PurchaseSectionsInput): OperatorSection[] {
  const sections: OperatorSection[] = [
    {
      key: "panel",
      label: "Painel",
      icon: "lucide:layout-dashboard",
      to: "/",
    },
    {
      key: "buy",
      label: "Comprar",
      icon: "lucide:shopping-cart",
      to: "/buy",
      attention: urgentMaterials > 0 ? urgentLabel(urgentMaterials) : undefined,
    },
    {
      key: "receive",
      label: "Receber",
      icon: "lucide:package-check",
      to: "/receive",
      badge: receivePending > 0 ? String(receivePending) : undefined,
    },
    {
      key: "base",
      label: "Base",
      icon: "lucide:database",
      to: "/base/materials",
      match: ["/base"],
    },
    {
      key: "count",
      label: "Contar estoque",
      // Na barra de baixo, 1/4 de um celular de 320px: o nome curto. O acessível é o cheio.
      shortLabel: "Contar",
      icon: "lucide:clipboard-check",
      to: COUNT_PATH,
    },
  ];
  return sections.map((section, index) => ({
    ...section,
    shortcut: `Alt+${index + 1}`,
    ...(PURCHASE_FLOOR_SECTIONS.includes(section.key)
      ? { form: "floor" as const, quick: true }
      : { form: "office" as const }),
  }));
}
