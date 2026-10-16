// As seções do Compras no shell da suíte (WP-FASE2-UX-OPERADOR, onda do Compras).
//
// Cada seção é uma rota: Painel (`/`), Comprar (`/buy`), Receber (`/receive`) e Base
// (`/base/<cadastro>`). As quatro vão para a barra inferior do celular (`quick`), sem
// "Mais": o ☰ abre a gaveta com o menu completo. A Base tem quatro sub-seções com rota
// própria (Insumos, Fornecedores, Custos, Contagem), escolhidas na toolbar da tela.
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

export const PURCHASE_BASE_SECTIONS: ReadonlyArray<{ key: PurchaseBaseView; label: string; icon: string; to: string }> = [
  { key: "materials", label: "Insumos", icon: "i-lucide-package-search", to: "/base/materials" },
  { key: "suppliers", label: "Fornecedores", icon: "i-lucide-truck", to: "/base/suppliers" },
  { key: "costs", label: "Custos", icon: "i-lucide-calculator", to: "/base/costs" },
  { key: "count", label: "Contagem", icon: "i-lucide-clipboard-check", to: "/base/count" },
];

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

export function purchaseSections({ urgentMaterials, receivePending }: PurchaseSectionsInput): OperatorSection[] {
  return [
    { key: "panel", label: "Painel", icon: "lucide:layout-dashboard", to: "/", quick: true },
    {
      key: "buy",
      label: "Comprar",
      icon: "lucide:shopping-cart",
      to: "/buy",
      quick: true,
      attention: urgentMaterials > 0 ? urgentLabel(urgentMaterials) : undefined,
    },
    {
      key: "receive",
      label: "Receber",
      icon: "lucide:package-check",
      to: "/receive",
      quick: true,
      badge: receivePending > 0 ? String(receivePending) : undefined,
    },
    { key: "base", label: "Base", icon: "lucide:database", to: "/base/materials", match: ["/base"], quick: true },
  ];
}
