<script setup lang="ts">
// O fornecedor aberto (`/base/suppliers/<ref>`), filho da tabela de Fornecedores. Na mesa
// larga divide a tela com a tabela; abaixo do `xl`, vira a página do registro.
import { recordTrailCount, recordTrailPosition } from "../../../../../operator-kit/app/presentation/recordTrail";
import { SUPPLIERS_TRAIL, baseSectionPath, supplierPath } from "~/presentation/purchaseSections";

const route = useRoute();
const { suppliers, backendReady, openSupplierEdit, openSupplierDuplicate } = usePurchaseDesk();
const supplierRef = computed(() => String(route.params.ref ?? ""));
const supplier = computed(() => suppliers.value.find((item) => item.ref === supplierRef.value) ?? null);
const { trail } = useRecordTrail(SUPPLIERS_TRAIL);
const position = computed(() => recordTrailPosition(trail.value, supplierRef.value));
const trailCount = computed(() => (position.value ? recordTrailCount(position.value) : ""));
const previousAction = computed(() => ({
  label: "Fornecedor anterior",
  shortLabel: "Anterior",
  icon: "i-lucide-chevron-left",
  to: position.value?.previous ? supplierPath(position.value.previous) : undefined,
  disabled: !position.value?.previous,
}));
const nextAction = computed(() => ({
  label: "Próximo fornecedor",
  shortLabel: "Próximo",
  icon: "i-lucide-chevron-right",
  to: position.value?.next ? supplierPath(position.value.next) : undefined,
  disabled: !position.value?.next,
}));

function close() {
  void navigateTo(baseSectionPath("suppliers"));
}
</script>

<template>
  <div class="contents">
    <!-- `contents`: a coluna é irmã da tabela no flex da rota mãe. -->
    <aside class="w-96 shrink-0 overflow-auto border-l border-default p-4 max-xl:hidden" aria-label="Fornecedor aberto" data-supplier-aside>
      <PurchaseSupplierDetail v-if="supplier" :supplier="supplier">
        <template #actions>
          <div class="flex items-center gap-1">
            <NuxtButton icon="i-lucide-pencil" color="neutral" variant="ghost" square aria-label="Editar o fornecedor" title="Editar" @click="openSupplierEdit(supplier.ref)" />
            <NuxtButton icon="i-lucide-copy" color="neutral" variant="ghost" square aria-label="Duplicar o fornecedor" title="Duplicar" @click="openSupplierDuplicate(supplier.ref)" />
            <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square aria-label="Fechar o fornecedor" @click="close()" />
          </div>
        </template>
        <template #nav>
          <OperatorRecordNav :trail="SUPPLIERS_TRAIL" :current="supplier.ref" :to="supplierPath" previous-label="Fornecedor anterior" next-label="Próximo fornecedor" />
        </template>
      </PurchaseSupplierDetail>
      <OperatorScreenState v-else-if="backendReady" state="empty" in-card icon="i-lucide-truck" :title="`O fornecedor ${supplierRef} não está na Base.`">
        <template #actions>
          <NuxtButton label="Voltar aos fornecedores" color="neutral" variant="outline" @click="close()" />
        </template>
      </OperatorScreenState>
    </aside>

    <div class="flex min-h-0 min-w-0 flex-1 flex-col xl:hidden" data-supplier-page>
      <section class="min-h-0 flex-1 overflow-auto bg-background p-4 sm:p-6">
        <div class="mx-auto flex w-full max-w-2xl flex-col gap-3">
          <NuxtButton label="Voltar aos fornecedores" icon="i-lucide-arrow-left" color="neutral" variant="ghost" class="self-start" @click="close()" />
          <NuxtCard v-if="supplier" data-supplier-sheet>
            <PurchaseSupplierDetail :supplier="supplier">
              <template #actions>
                <div class="flex items-center gap-1">
                  <NuxtButton icon="i-lucide-pencil" color="neutral" variant="ghost" square aria-label="Editar o fornecedor" title="Editar" @click="openSupplierEdit(supplier.ref)" />
                  <NuxtButton icon="i-lucide-copy" color="neutral" variant="ghost" square aria-label="Duplicar o fornecedor" title="Duplicar" @click="openSupplierDuplicate(supplier.ref)" />
                </div>
              </template>
              <template #nav>
                <div class="max-lg:hidden">
                  <OperatorRecordNav :trail="SUPPLIERS_TRAIL" :current="supplier.ref" :to="supplierPath" previous-label="Fornecedor anterior" next-label="Próximo fornecedor" />
                </div>
              </template>
            </PurchaseSupplierDetail>
          </NuxtCard>
          <OperatorScreenState v-else-if="backendReady" state="empty" in-card icon="i-lucide-truck" :title="`O fornecedor ${supplierRef} não está na Base.`">
            <template #actions>
              <NuxtButton label="Voltar aos fornecedores" color="neutral" variant="outline" @click="close()" />
            </template>
          </OperatorScreenState>
        </div>
      </section>
      <OperatorActionBar v-if="position" :action="nextAction" :secondary="previousAction" :context-label="trail?.label || 'Fornecedores'" :context-value="trailCount" label="Navegar pelos fornecedores" />
    </div>
  </div>
</template>
