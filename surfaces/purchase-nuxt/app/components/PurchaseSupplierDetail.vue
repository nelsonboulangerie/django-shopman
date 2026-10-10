<script setup lang="ts">
// O fornecedor aberto na Base: prazo, entrega, pagamento, para quem vai o pedido de
// compra e a carteira (os custos dele por insumo).
import type { Material, Supplier, SupplierMaterialCost } from "~/types/purchase";
import { costPerBaseUnitQ, formatMoney, formatShortDate, isApproximateCost, purchaseUnitLabel } from "~/presentation/purchase";
import { materialPath } from "~/presentation/purchaseSections";

const props = defineProps<{ supplier: Supplier }>();
const { costs, materials, conversions } = usePurchaseDesk();

// Pessoa de contato é cadastro: se edita no Admin. O aviso leva direto ao fornecedor lá.
const adminBase = String(useRuntimeConfig().public.djangoBaseUrl || "").replace(/\/$/, "");
const adminUrl = computed(() => `${adminBase}/admin/buyman/supplier/?q=${encodeURIComponent(props.supplier.ref)}`);

// Contato inativo continua no cadastro (histórico), mas não na tela de quem vai ligar hoje.
const activeContacts = computed(() => props.supplier.contacts.filter((person) => person.isActive));

type PortfolioRow = { cost: SupplierMaterialCost; material: Material; unitLabel: string; baseCostQ: number; approximate: boolean };
const portfolio = computed(() =>
  costs.value
    .filter((cost) => cost.supplierRef === props.supplier.ref)
    .map((cost) => {
      const material = materials.value.find((item) => item.sku === cost.materialSku);
      if (!material) return null;
      return {
        cost,
        material,
        unitLabel: purchaseUnitLabel(cost, material, conversions.value),
        baseCostQ: costPerBaseUnitQ(cost, conversions.value),
        approximate: isApproximateCost(cost, conversions.value),
      };
    })
    .filter((row): row is PortfolioRow => Boolean(row)),
);
</script>

<template>
  <div class="space-y-4" data-supplier-panel>
    <div>
      <div class="flex items-start justify-between gap-2">
        <div class="min-w-0">
          <p class="text-xs text-muted">Fornecedor</p>
          <h2 class="text-base font-semibold">{{ supplier.displayName }}</h2>
          <!-- A razão social só aparece quando difere do nome do dia a dia. -->
          <p v-if="supplier.tradeName && supplier.name !== supplier.displayName" class="text-xs text-muted">{{ supplier.name }}</p>
          <p v-if="supplier.document" class="text-xs text-muted tabular-nums">{{ supplier.document }}</p>
        </div>
        <slot name="actions" />
      </div>
      <slot name="nav" />
    </div>

    <dl class="grid grid-cols-2 gap-3">
      <div><dt class="text-xs text-muted">Prazo de entrega</dt><dd class="text-sm font-semibold">{{ supplier.leadTimeDays }} {{ supplier.leadTimeDays === 1 ? "dia" : "dias" }}</dd></div>
      <div><dt class="text-xs text-muted">Entregas no prazo</dt><dd class="text-sm font-semibold tabular-nums">{{ supplier.reliabilityPercent }}%</dd></div>
      <div><dt class="text-xs text-muted">Última entrega</dt><dd class="text-sm font-semibold tabular-nums">{{ formatShortDate(supplier.lastDeliveryAt) }}</dd></div>
      <div><dt class="text-xs text-muted">Pagamento</dt><dd class="text-sm font-semibold">{{ supplier.paymentTerm || "a combinar" }}</dd></div>
    </dl>

    <section class="border-t border-default pt-4">
      <h3 class="text-sm font-semibold">Contatos</h3>
      <!-- A pergunta antes de apertar "enviar" é "vai para quem?". Responder depois do
           envio não serve. -->
      <NuxtAlert
        v-if="!supplier.orderContactName"
        class="mt-2"
        variant="subtle"
        color="warning"
        :title="supplier.contact ? `Sem contato comercial: o pedido de compra vai para a central (${supplier.contact}).` : 'Sem contato e sem central: o pedido de compra não tem para onde ir.'"
        description="Contatos se cadastram no Admin."
        :actions="alertActions('warning', [{ label: 'Cadastrar contato no Admin', to: adminUrl, target: '_blank' }])"
      />
      <p v-else class="mt-1 text-xs text-muted">
        O pedido de compra vai para <span class="font-semibold text-default">{{ supplier.orderContactName }}</span>. Contatos se cadastram no Admin.
      </p>
      <ul v-if="activeContacts.length" class="mt-2 space-y-2">
        <li v-for="person in activeContacts" :key="person.id">
          <NuxtCard variant="soft">
            <div class="flex items-start justify-between gap-2">
              <p class="text-sm font-semibold">{{ person.name }}</p>
              <NuxtBadge color="neutral" :label="person.isPrimary ? `${person.roleLabel} · principal` : person.roleLabel" class="shrink-0" />
            </div>
            <p v-if="person.email" class="text-xs text-muted">{{ person.email }}</p>
            <p v-if="person.phone" class="text-xs text-muted tabular-nums">{{ person.phone }}</p>
            <p v-if="person.notes" class="mt-1 text-xs text-muted">{{ person.notes }}</p>
          </NuxtCard>
        </li>
      </ul>
    </section>

    <section class="border-t border-default pt-4">
      <h3 class="text-sm font-semibold">Carteira <span class="font-normal text-muted tabular-nums">{{ portfolio.length }}</span></h3>
      <ul v-if="portfolio.length" class="mt-2 divide-y divide-default">
        <li v-for="row in portfolio" :key="row.cost.id">
          <NuxtLink :to="materialPath(row.material.sku)" class="flex items-start justify-between gap-2 py-2 hover:text-highlighted">
            <span class="min-w-0">
              <span class="block text-sm font-semibold">{{ row.material.name }}</span>
              <span class="block text-xs text-muted tabular-nums">{{ formatMoney(row.cost.costQ) }} / {{ row.unitLabel }}</span>
            </span>
            <span class="shrink-0 text-sm font-semibold tabular-nums">
              <span v-if="row.approximate">≈ </span>{{ formatMoney(row.baseCostQ) }} / {{ row.material.unit }}
            </span>
          </NuxtLink>
        </li>
      </ul>
      <p v-else class="mt-1 text-xs text-muted">Nenhum custo lançado para este fornecedor.</p>
    </section>
  </div>
</template>
