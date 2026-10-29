<script setup lang="ts">
// Onde está a maquininha: o botão do cabeçalho do Gestor diz quantas estão na
// rua e abre a lista (qual, com qual pedido, desde quando) com o "Voltou" de
// cada uma. Some quando todas estão na loja. A lista é `equipment_out` da fila,
// a mesma custódia do card; o "Voltou" é o mesmo gesto do card.
import type { EquipmentOutProjection } from "~/generated/ordersContract";
import { equipmentOutLabel, equipmentOutLine } from "~/presentation/board";

const props = defineProps<{
  items: EquipmentOutProjection[];
  isBusy: (ref: string) => boolean;
}>();

const emit = defineEmits<{ back: [orderRef: string] }>();

const backAction = (item: EquipmentOutProjection) =>
  item.actions.find((action) => action.ref === "equipment-back");
</script>

<template>
  <NuxtPopover v-if="props.items.length" :content="{ align: 'end' }">
    <NuxtButton
      icon="i-lucide-smartphone-nfc"
      :label="equipmentOutLabel(props.items.length)"
      color="neutral"
      variant="outline"
      data-equipment-out-menu
    />
    <template #content>
      <div class="w-80 p-2" data-equipment-out-list>
        <template v-for="(item, index) in props.items" :key="item.ref">
          <div class="flex items-center gap-2 px-2 py-2">
            <Icon
              name="lucide:smartphone-nfc"
              class="size-4 shrink-0 text-muted-foreground"
            />
            <span class="min-w-0 flex-1">
              <span class="block truncate op-body font-medium">{{
                item.label
              }}</span>
              <span class="block truncate op-micro text-muted-foreground">{{
                equipmentOutLine(item)
              }}</span>
            </span>
            <NuxtButton
              v-if="backAction(item)"
              label="Voltou"
              color="neutral"
              variant="outline"
              :disabled="
                !backAction(item)?.enabled || props.isBusy(item.order_ref)
              "
              :title="backAction(item)?.reason || undefined"
              data-equipment-out-back
              @click="emit('back', item.order_ref)"
            />
          </div>
          <NuxtSeparator v-if="index < props.items.length - 1" />
        </template>
      </div>
    </template>
  </NuxtPopover>
</template>
