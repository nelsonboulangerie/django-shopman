<script setup lang="ts">
// O insumo aberto (`/base/materials/<sku>`), filho da tabela de Insumos. Na mesa larga
// divide a tela com a tabela (nada fica coberto); abaixo do `xl`, abre numa folha de
// lado. "‹ 3 de 18 ›" (`OperatorRecordNav`) anda dentro da lista que a pessoa via.
import { MATERIALS_TRAIL, baseSectionPath, materialPath } from "~/presentation/purchaseSections";

const route = useRoute();
const screen = useScreen();
const { enrichedMaterials, backendReady } = usePurchaseDesk();
const sku = computed(() => String(route.params.sku ?? ""));
const material = computed(() => enrichedMaterials.value.find((item) => item.sku === sku.value) ?? null);

function close() {
  void navigateTo(baseSectionPath("materials"));
}
</script>

<template>
  <div class="contents">
  <!-- `contents`: a coluna é irmã da tabela no flex da rota mãe. -->
  <!-- Na mesa larga: a coluna ao lado da tabela. -->
  <aside
    class="w-96 shrink-0 overflow-auto border-l border-default p-4 max-xl:hidden"
    aria-label="Insumo aberto"
    data-material-aside
  >
    <PurchaseMaterialDetail v-if="material" :material="material">
      <template #actions>
        <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square aria-label="Fechar o insumo" @click="close()" />
      </template>
      <template #nav>
        <OperatorRecordNav :trail="MATERIALS_TRAIL" :current="material.sku" :to="materialPath" previous-label="Insumo anterior" next-label="Próximo insumo" />
      </template>
    </PurchaseMaterialDetail>
    <OperatorScreenState
      v-else-if="backendReady"
      state="empty"
      in-card
      icon="i-lucide-package-x"
      :title="`O insumo ${sku} não está na Base.`"
    >
      <template #actions>
        <NuxtButton label="Voltar aos insumos" color="neutral" variant="outline" @click="close()" />
      </template>
    </OperatorScreenState>
  </aside>

  <!-- Abaixo do `xl`: a mesma ficha numa folha de lado. Só depois de montar (a régua
       responde "mesa" até lá); na mesa larga ela nunca abre. -->
  <NuxtSlideover
    v-if="screen.ready.value && screen.belowXl.value"
    :open="Boolean(material)"
    side="right"
    title="Insumo"
    :description="material?.name"
    @update:open="(value: boolean) => { if (!value) close(); }"
  >
    <template #content>
      <div v-if="material" class="h-full overflow-auto p-4" data-material-sheet>
        <PurchaseMaterialDetail :material="material">
          <template #actions>
            <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square aria-label="Fechar o insumo" @click="close()" />
          </template>
          <template #nav>
            <OperatorRecordNav :trail="MATERIALS_TRAIL" :current="material.sku" :to="materialPath" previous-label="Insumo anterior" next-label="Próximo insumo" />
          </template>
        </PurchaseMaterialDetail>
      </div>
    </template>
  </NuxtSlideover>
  </div>
</template>
