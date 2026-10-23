<script setup lang="ts">
// O insumo aberto (`/base/materials/<sku>`), filho da tabela de Insumos. Na mesa larga
// divide a tela com a tabela (nada fica coberto); abaixo do `xl`, vira a página do
// registro. A navegação anda dentro da lista que a pessoa via.
import { recordTrailCount, recordTrailPosition } from "../../../../../operator-kit/app/presentation/recordTrail";
import { MATERIALS_TRAIL, baseSectionPath, materialPath } from "~/presentation/purchaseSections";

const route = useRoute();
const { enrichedMaterials, backendReady, openMaterialEdit, openMaterialDuplicate } = usePurchaseDesk();
const sku = computed(() => String(route.params.sku ?? ""));
const material = computed(() => enrichedMaterials.value.find((item) => item.sku === sku.value) ?? null);
const { trail } = useRecordTrail(MATERIALS_TRAIL);
const position = computed(() => recordTrailPosition(trail.value, sku.value));
const trailCount = computed(() => (position.value ? recordTrailCount(position.value) : ""));
const previousAction = computed(() => ({
  label: "Insumo anterior",
  shortLabel: "Anterior",
  icon: "i-lucide-chevron-left",
  to: position.value?.previous ? materialPath(position.value.previous) : undefined,
  disabled: !position.value?.previous,
}));
const nextAction = computed(() => ({
  label: "Próximo insumo",
  shortLabel: "Próximo",
  icon: "i-lucide-chevron-right",
  to: position.value?.next ? materialPath(position.value.next) : undefined,
  disabled: !position.value?.next,
}));

function close() {
  void navigateTo(baseSectionPath("materials"));
}
</script>

<template>
  <div class="contents">
    <!-- `contents`: a coluna é irmã da tabela no flex da rota mãe. -->
    <!-- Na mesa larga: a coluna ao lado da tabela. -->
    <aside class="w-96 shrink-0 overflow-auto border-l border-default p-4 max-xl:hidden" aria-label="Insumo aberto" data-material-aside>
      <PurchaseMaterialDetail v-if="material" :material="material">
        <template #actions>
          <div class="flex items-center gap-1">
            <NuxtButton icon="i-lucide-pencil" color="neutral" variant="ghost" square aria-label="Editar o insumo" title="Editar" @click="openMaterialEdit(material.sku)" />
            <NuxtButton icon="i-lucide-copy" color="neutral" variant="ghost" square aria-label="Duplicar o insumo" title="Duplicar" @click="openMaterialDuplicate(material.sku)" />
            <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square aria-label="Fechar o insumo" @click="close()" />
          </div>
        </template>
        <template #nav>
          <OperatorRecordNav :trail="MATERIALS_TRAIL" :current="material.sku" :to="materialPath" previous-label="Insumo anterior" next-label="Próximo insumo" />
        </template>
      </PurchaseMaterialDetail>
      <OperatorScreenState v-else-if="backendReady" state="empty" in-card icon="i-lucide-package-x" :title="`O insumo ${sku} não está na Base.`">
        <template #actions>
          <NuxtButton label="Voltar aos insumos" color="neutral" variant="outline" @click="close()" />
        </template>
      </OperatorScreenState>
    </aside>

    <!-- No celular e no tablet, o registro é a página: não uma gaveta cobrindo a lista.
       A rota continua sendo a mesma e a mesa larga preserva o painel lado a lado. -->
  <div class="flex min-h-0 min-w-0 flex-1 flex-col xl:hidden" data-material-page>
      <section class="min-h-0 flex-1 overflow-auto bg-background p-4 sm:p-6">
        <div class="mx-auto flex w-full max-w-2xl flex-col gap-3">
          <NuxtButton label="Voltar aos insumos" icon="i-lucide-arrow-left" color="neutral" variant="ghost" class="self-start" @click="close()" />
          <NuxtCard v-if="material" data-material-sheet>
            <PurchaseMaterialDetail :material="material">
              <template #actions>
                <div class="flex items-center gap-1">
                  <NuxtButton icon="i-lucide-pencil" color="neutral" variant="ghost" square aria-label="Editar o insumo" title="Editar" @click="openMaterialEdit(material.sku)" />
                  <NuxtButton icon="i-lucide-copy" color="neutral" variant="ghost" square aria-label="Duplicar o insumo" title="Duplicar" @click="openMaterialDuplicate(material.sku)" />
                </div>
              </template>
              <template #nav>
                <div class="max-lg:hidden">
                  <OperatorRecordNav :trail="MATERIALS_TRAIL" :current="material.sku" :to="materialPath" previous-label="Insumo anterior" next-label="Próximo insumo" />
                </div>
              </template>
            </PurchaseMaterialDetail>
          </NuxtCard>
          <OperatorScreenState v-else-if="backendReady" state="empty" in-card icon="i-lucide-package-x" :title="`O insumo ${sku} não está na Base.`">
            <template #actions>
              <NuxtButton label="Voltar aos insumos" color="neutral" variant="outline" @click="close()" />
            </template>
          </OperatorScreenState>
        </div>
      </section>
      <OperatorActionBar v-if="position" :action="nextAction" :secondary="previousAction" :context-label="trail?.label || 'Insumos'" :context-value="trailCount" label="Navegar pelos insumos" />
    </div>
  </div>
</template>
