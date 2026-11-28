<script setup lang="ts">
// O pedido à Produção (WP-F13, P1-04): no topo do Planejamento, a encomenda da data
// que o plano não cobre, pela régua das reservas (`promised`, WP-F08). Sem lote:
// "Encomendado sem lote: Croissant 12" com "Planejar 12"; acima do plano:
// "Encomendado acima do plano: Croissant 3" com "Planejar mais 3". Quando o produto já
// tem linha no dia com sugestão que conta as encomendas, a faixa não oferece número seu:
// diz o fato ("Croissant Manteiga: 12 encomendadas, já contadas na sugestão de 196") e
// leva até a linha (decisão da coordenação, 28/11). Planejar cobre a
// encomenda e a faixa some. A Produção só planeja (D-042, item 2): não há recusar
// aqui, e quem fala com o cliente é o Gestor ("Promessa em risco").
// A conta mora em `presentation/production.ts` (`unbackedOrders`); o envio, na grade.
import {
  promisedWhen,
  rowPromisedOrders,
  type UnbackedOrder,
} from "~/presentation/production";

const props = defineProps<{
  items: UnbackedOrder[];
  today: string;
  canPlan: boolean;
  busySku: string | null;
}>();

const emit = defineEmits<{
  plan: [item: UnbackedOrder];
  orders: [item: UnbackedOrder];
  /** O produto já tem linha com número próprio: a faixa leva até ela. */
  line: [item: UnbackedOrder];
}>();

/** Quem encomendou e quando: "Clara · amanhã 9h", "Marina e Bruno · amanhã, das 8h30 às 11h". */
function whoAndWhen(item: UnbackedOrder): string {
  // Quem encomendou duas vezes aparece uma vez ("Ana", nunca "Ana e Ana").
  const names = [
    ...new Set(
      rowPromisedOrders(item.row).map(
        (order) => order.customer_first_name || order.ref,
      ),
    ),
  ];
  const who =
    names.length <= 2
      ? names.join(" e ")
      : `${names.slice(0, 2).join(", ")} e mais ${names.length - 2}`;
  const when = item.row.promised ? promisedWhen(item.row.promised, props.today) : "";
  return [who, when].filter(Boolean).join(" · ");
}
</script>

<template>
  <section
    v-if="items.length"
    class="overflow-hidden rounded-lg border border-warning/40 bg-warning/5"
    aria-label="Encomendas que o plano não cobre"
    data-plan-promised-band
  >
    <div
      v-for="item in items"
      :key="item.row.output_sku"
      class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-warning/25 px-4 py-3 last:border-b-0 lg:min-h-16"
      data-plan-promised-item
      :data-sku="item.row.output_sku"
      :data-kind="item.kind"
    >
      <span
        class="grid size-9 shrink-0 place-items-center rounded-full border border-warning/40 bg-card"
        aria-hidden="true"
      >
        <Icon name="lucide:shopping-bag" class="size-4 text-warning" />
      </span>
      <div class="min-w-0 flex-1 basis-56">
        <p class="op-body" data-plan-promised-text>
          <b class="font-semibold">{{ item.headline }}:</b>
          {{ item.subject }}
        </p>
        <p class="op-micro text-muted-foreground" data-plan-promised-who>
          {{ whoAndWhen(item) }}
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <NuxtButton
          color="neutral"
          variant="outline"
          icon="i-lucide-list"
          label="Ver encomendas"
          data-plan-promised-orders
          @click="emit('orders', item)"
        />
        <NuxtButton
          v-if="item.coveredBy"
          color="primary"
          variant="outline"
          icon="i-lucide-arrow-down-to-line"
          :label="item.actionLabel"
          data-plan-promised-line
          @click="emit('line', item)"
        />
        <NuxtButton
          v-else-if="canPlan"
          color="primary"
          variant="solid"
          icon="i-lucide-calendar-plus"
          :label="busySku === item.row.output_sku ? 'Planejando…' : item.actionLabel"
          :aria-busy="busySku === item.row.output_sku"
          :disabled="busySku !== null"
          data-plan-promised-plan
          @click="emit('plan', item)"
        />
      </div>
    </div>
  </section>
</template>
