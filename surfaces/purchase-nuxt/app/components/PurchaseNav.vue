<script setup lang="ts">
// Navegação do Compras (V4-COMPRAS, camada visual da suíte). O rail da suíte
// (`OperatorSuiteRail`, do tablet para cima) leva as quatro seções, como na prévia
// `purchase-base3.html`: Painel, Comprar (ponto de atenção quando há reposição urgente),
// Receber (selo com as pendências da entrada aberta) e Base. No celular as mesmas seções
// vão para a barra do polegar (`OperatorSectionBar`, prévia `compras-validade4.html`).
//
// As seções deste app NÃO são rotas: são estado (`useState("purchase-view")`), porque as
// quatro vistas dividem o mesmo carregamento. Por isso as duas peças recebem a seção
// ativa (`current`) e devolvem a escolha (`select`), em vez de navegar.
import type { OperatorSection } from "../../../operator-kit/app/presentation/appBar";
import type { PurchaseView } from "~/types/purchase";

defineProps<{
  place: "rail" | "bar";
  /** Rail: URL da Central e operador ativo (o menu e o Bloquear). */
  hubUrl?: string;
  operatorName?: string;
}>();
const emit = defineEmits<{ lock: [] }>();

const isPhone = useMediaQuery("(max-width: 767.98px)");
const {
  view,
  metrics,
  receiptIsBlank,
  receiptPendingLines,
  receiptDocumentBlockers,
  receiptSupplierBlockers,
  receiptVolumesStep,
} = usePurchaseDesk();

// O mesmo número do resumo da conferência: itens travados, não avisos.
const receivePending = computed(() =>
  receiptIsBlank.value ? 0 : (
    receiptPendingLines.value.length +
    receiptDocumentBlockers.value.length +
    receiptSupplierBlockers.value.length +
    (receiptVolumesStep.value ? 1 : 0)
  ),
);

const sections = computed<OperatorSection[]>(() => [
  { key: "panel", label: "Painel", icon: "lucide:layout-dashboard" },
  {
    key: "buy",
    label: "Comprar",
    icon: "lucide:shopping-cart",
    attention: metrics.value.urgentMaterials > 0 ?
      `${metrics.value.urgentMaterials} ${metrics.value.urgentMaterials === 1 ? "reposição urgente" : "reposições urgentes"}`
    : undefined,
  },
  {
    key: "receive",
    label: "Receber",
    icon: "lucide:package-check",
    badge: receivePending.value ? String(receivePending.value) : undefined,
    badgeLabel: receivePending.value ?
      `${receivePending.value} ${receivePending.value === 1 ? "pendência" : "pendências"} na entrada aberta`
    : undefined,
  },
  { key: "base", label: "Base", icon: "lucide:database" },
]);

function select(key: string) {
  view.value = key as PurchaseView;
}
</script>

<template>
  <OperatorSuiteRail
    v-if="place === 'rail'"
    :sections="sections"
    :current="view"
    label="Seções de Compras"
    :hub-url="hubUrl"
    :operator-name="operatorName"
    @select="select"
    @lock="emit('lock')"
  >
    <template v-if="!isPhone" #foot>
      <NotificationBell placement="rail" />
    </template>
  </OperatorSuiteRail>
  <OperatorSectionBar v-else :sections="sections" :current="view" label="Seções de Compras" @select="select" />
</template>
