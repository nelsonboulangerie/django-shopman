<script setup lang="ts">
// Cabeçalho de seção do Compras. As seções deste app NÃO são rotas: são estado
// (`useState("purchase-view")`), porque as três vistas compartilham o mesmo carregamento
// de dados. Por isso a barra recebe a seção ativa e devolve a escolha, em vez de navegar.
//
// O desenho vem do `OperatorAppBar` do kit. As abas daqui estavam em `h-8` — metade do
// alvo de toque da casa (`--spacing-control`, 44px) — e o `chipClass(active)` local era
// cópia byte a byte do que estava no B.I.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";
import type { PurchaseView } from "~/types/purchase";

defineProps<{
  view: PurchaseView;
  metrics: {
    urgentMaterials: number;
    missingPreferred: number;
    approximatePreferred: number;
  };
}>();

const emit = defineEmits<{ "update:view": [value: PurchaseView] }>();

const sections: OperatorSection[] = [
  { key: "panel", label: "Painel", icon: "lucide:layout-dashboard" },
  { key: "buy", label: "Comprar", icon: "lucide:shopping-cart" },
  { key: "receive", label: "Receber", icon: "lucide:package-check" },
  { key: "base", label: "Base", icon: "lucide:database" },
];
</script>

<template>
  <OperatorAppBar
    :sections="sections"
    :current="view"
    label="Seções de Compras"
    @select="key => emit('update:view', key as PurchaseView)"
  >
    <template #end>
      <div class="hidden items-center gap-2 xl:flex">
        <span class="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-xs font-medium text-foreground">
          <Icon name="lucide:triangle-alert" class="size-3.5 text-warning" />
          {{ metrics.urgentMaterials }} reposições
        </span>
        <span class="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-xs font-medium text-foreground">
          <Icon name="lucide:badge-alert" class="size-3.5 text-info" />
          {{ metrics.missingPreferred }} sem preferencial
        </span>
        <span class="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-background px-2.5 text-xs font-medium text-foreground">
          <Icon name="lucide:equal-approximately" class="size-3.5 text-muted-foreground" />
          {{ metrics.approximatePreferred }} estimados
        </span>
      </div>
    </template>
  </OperatorAppBar>
</template>
