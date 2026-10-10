<script setup lang="ts">
// O fornecedor aberto (`/base/suppliers/<ref>`), filho da tabela de Fornecedores. Na mesa
// larga divide a tela com a tabela; abaixo do `xl`, abre numa folha de lado.
import { SUPPLIERS_TRAIL, baseSectionPath, supplierPath } from "~/presentation/purchaseSections";

const route = useRoute();
const screen = useScreen();
const { suppliers, backendReady } = usePurchaseDesk();
const supplierRef = computed(() => String(route.params.ref ?? ""));
const supplier = computed(() => suppliers.value.find((item) => item.ref === supplierRef.value) ?? null);

function close() {
  void navigateTo(baseSectionPath("suppliers"));
}
</script>

<template>
  <div class="contents">
    <!-- `contents`: a coluna é irmã da tabela no flex da rota mãe. -->
    <aside
      class="w-96 shrink-0 overflow-auto border-l border-default p-4 max-xl:hidden"
      aria-label="Fornecedor aberto"
      data-supplier-aside
    >
      <PurchaseSupplierDetail v-if="supplier" :supplier="supplier">
        <template #actions>
          <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square aria-label="Fechar o fornecedor" @click="close()" />
        </template>
        <template #nav>
          <OperatorRecordNav :trail="SUPPLIERS_TRAIL" :current="supplier.ref" :to="supplierPath" previous-label="Fornecedor anterior" next-label="Próximo fornecedor" />
        </template>
      </PurchaseSupplierDetail>
      <OperatorScreenState
        v-else-if="backendReady"
        state="empty"
        in-card
        icon="i-lucide-truck"
        :title="`O fornecedor ${supplierRef} não está na Base.`"
      >
        <template #actions>
          <NuxtButton label="Voltar aos fornecedores" color="neutral" variant="outline" @click="close()" />
        </template>
      </OperatorScreenState>
    </aside>

    <NuxtSlideover
      v-if="screen.ready.value && screen.belowXl.value"
      :open="Boolean(supplier)"
      side="right"
      title="Fornecedor"
      :description="supplier?.displayName"
      @update:open="(value: boolean) => { if (!value) close(); }"
    >
      <template #content>
        <div v-if="supplier" class="h-full overflow-auto p-4" data-supplier-sheet>
          <PurchaseSupplierDetail :supplier="supplier">
            <template #actions>
              <NuxtButton icon="i-lucide-x" color="neutral" variant="ghost" square aria-label="Fechar o fornecedor" @click="close()" />
            </template>
            <template #nav>
              <OperatorRecordNav :trail="SUPPLIERS_TRAIL" :current="supplier.ref" :to="supplierPath" previous-label="Fornecedor anterior" next-label="Próximo fornecedor" />
            </template>
          </PurchaseSupplierDetail>
        </div>
      </template>
    </NuxtSlideover>
  </div>
</template>
