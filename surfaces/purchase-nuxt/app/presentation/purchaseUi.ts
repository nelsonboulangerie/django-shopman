// O estado do insumo e do pedido de compra em selo (`NuxtBadge`, sem `variant`: o tema
// dá `soft`). Uma cor e uma palavra por estado, em toda tela do Compras.
import type { MaterialTone, PurchaseRequestStatus, Supplier } from "~/types/purchase";
import type { ActiveFilters, FilterDimension } from "../../../operator-kit/app/types/filters";

type BadgeColor = "neutral" | "primary" | "info" | "success" | "warning" | "error";

export const TONE_BADGE: Record<MaterialTone, BadgeColor> = {
  ok: "success",
  watch: "warning",
  urgent: "error",
};

export const TONE_LABEL: Record<MaterialTone, string> = {
  ok: "Em ordem",
  watch: "Revisar",
  urgent: "Comprar",
};

/** A ordem de "Situação" ao ordenar: o que pede compra primeiro. */
export const TONE_RANK: Record<MaterialTone, number> = { urgent: 0, watch: 1, ok: 2 };

export const REQUEST_BADGE: Record<PurchaseRequestStatus, BadgeColor> = {
  review: "warning",
  sent: "info",
};

export const REQUEST_LABEL: Record<PurchaseRequestStatus, string> = {
  review: "Revisar",
  sent: "Aguardando entrega",
};

/** "1 insumo", "3 insumos". */
export function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

// ── Os recortes de Base · Insumos (o painel de filtros da suíte) ────────────
// Situação (o selo da linha) e Categoria, com a contagem de cada opção. "Pedem
// atenção" (o filtro rápido) é a Situação em Comprar ou Revisar.

const TONE_ORDER: readonly MaterialTone[] = ["urgent", "watch", "ok"];

/** As dimensões do painel, com quantos insumos casam cada opção. */
export function materialDimensions(
  materials: readonly { tone: MaterialTone; category: string }[],
): FilterDimension[] {
  const toneCount = (tone: MaterialTone) => materials.filter((material) => material.tone === tone).length;
  const categories = [...new Set(materials.map((material) => material.category).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, "pt-BR"),
  );
  return [
    {
      id: "archive",
      label: "Cadastro",
      type: "single-select",
      options: [{ value: "archived", label: "Arquivados" }],
    },
    {
      id: "tone",
      label: "Situação",
      type: "multi-select",
      options: TONE_ORDER.map((tone) => ({ value: tone, label: TONE_LABEL[tone], count: toneCount(tone) })),
    },
    {
      id: "category",
      label: "Categoria",
      type: "multi-select",
      options: categories.map((category) => ({
        value: category,
        label: category,
        count: materials.filter((material) => material.category === category).length,
      })),
    },
  ];
}

/** O que pede atenção: o filtro rápido "Pedem atenção" liga estas duas situações. */
export const MATERIAL_ATTENTION_TONES: readonly MaterialTone[] = ["urgent", "watch"];

/** O recorte é exatamente "Pedem atenção"? (as duas situações, e só elas) */
export function isAttentionRecorte(filters: ActiveFilters): boolean {
  const tones = filters.tone ?? [];
  return tones.length === MATERIAL_ATTENTION_TONES.length && MATERIAL_ATTENTION_TONES.every((tone) => tones.includes(tone));
}

/** O insumo casa o recorte? Dentro de uma dimensão, OU; entre dimensões, E. */
export function matchesMaterialFilters(
  material: { tone: MaterialTone; category: string; isActive?: boolean },
  filters: ActiveFilters,
): boolean {
  const archive = filters.archive ?? [];
  const tones = filters.tone ?? [];
  const categories = filters.category ?? [];
  return (
    (!archive.length ? material.isActive !== false : archive.includes("archived") && material.isActive === false) &&
    (!tones.length || tones.includes(material.tone)) &&
    (!categories.length || categories.includes(material.category))
  );
}

// ── Os recortes de Base · Fornecedores ──────────────────────────────────────
// Arquivados e a pergunta que o comprador faz antes de apertar enviar: este
// fornecedor tem para quem mandar o pedido?

/** As dimensões do painel, com quantos fornecedores casam cada opção. */
export function supplierDimensions(suppliers: readonly Supplier[]): FilterDimension[] {
  const withContact = suppliers.filter((supplier) => Boolean(supplier.orderContactName)).length;
  return [
    {
      id: "archive",
      label: "Cadastro",
      type: "single-select",
      options: [{ value: "archived", label: "Arquivados" }],
    },
    {
      id: "contact",
      label: "Contato comercial",
      type: "multi-select",
      options: [
        { value: "with", label: "Com contato comercial", count: withContact },
        { value: "without", label: "Sem contato comercial", count: suppliers.length - withContact },
      ],
    },
  ];
}

/** O fornecedor casa o recorte? Dentro de uma dimensão, OU; entre dimensões, E. */
export function matchesSupplierFilters(
  supplier: Pick<Supplier, "isActive" | "orderContactName">,
  filters: ActiveFilters,
): boolean {
  const archive = filters.archive ?? [];
  const contact = filters.contact ?? [];
  const contactValue = supplier.orderContactName ? "with" : "without";
  return (
    (!archive.length ? supplier.isActive : archive.includes("archived") && !supplier.isActive) &&
    (!contact.length || contact.includes(contactValue))
  );
}

