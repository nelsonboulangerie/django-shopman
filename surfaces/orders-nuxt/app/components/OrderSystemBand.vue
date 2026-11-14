<script setup lang="ts">
// "O sistema fez", em faixa (D, dono 13/11/2026, prévia `gestor-d`): o que o sistema
// mudou sozinho e ainda dá para desfazer, logo abaixo do cabeçalho. Uma linha por
// pedido, só enquanto a janela do Desfazer está aberta; fechada, some. A faixa é a do
// kit (`OperatorBand`: descolada e invertida, variante 3 do dono). A lista inteira
// do que o sistema fez continua na Fila.
import type { SystemActionProjection } from "~/types/orders";
import { splitRef } from "~/presentation/board";

defineProps<{
  lines: SystemActionProjection[];
  busy: (ref: string) => boolean;
  serverNow?: string;
}>();
const emit = defineEmits<{ undo: [ref: string] }>();
</script>

<template>
  <div class="flex flex-col gap-2" data-system-band>
    <OperatorBand
      v-for="line in lines"
      :key="`${line.order_ref}-${line.at_iso}`"
      icon="i-lucide-sparkles"
      :title="`${splitRef(line.order_ref).code} ficou ${line.verb.toLowerCase()} sozinho · ${line.reason}`"
      :data-system-band-line="line.order_ref"
    >
      <template #actions>
        <OperatorTimedButton
          :until="line.undo_until_iso"
          :since="line.at_iso"
          :server-now="serverNow"
          label="Desfazer"
          color="neutral"
          variant="outline"
          icon="i-lucide-undo-2"
          :disabled="busy(line.order_ref)"
          data-system-band-undo
          @click="emit('undo', line.order_ref)"
        />
      </template>
    </OperatorBand>
  </div>
</template>
