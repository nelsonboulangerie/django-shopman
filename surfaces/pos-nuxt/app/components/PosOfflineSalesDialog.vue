<script setup lang="ts">
// As vendas feitas SEM CONEXÃO, guardadas neste dispositivo (WP-PDV-SEM-CONEXAO).
//
// Abre pelo aviso do cabeçalho. Diz o que funciona sem conexão, lista cada venda
// guardada com o que ela espera, e dá a saída de cada recusa do servidor ali
// mesmo: "Tentar de novo" (o motivo foi resolvido fora, ex.: o caixa abriu) e,
// quando o total mudou, "Enviar com R$ X" (a diferença aparece no fechamento).
import { clockLabel, type OfflineSale } from "~/presentation/offlineSales";
import { formatBRL } from "~/utils/posIntent";

const props = defineProps<{
  open: boolean;
  online: boolean;
  sales: OfflineSale[];
  sending: boolean;
  /** `false`: sem IndexedDB, a fila vive só nesta aba. */
  durable: boolean;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  sendNow: [];
  retry: [string];
  sendWithServerTotal: [string];
}>();

const WORKS = [
  { icon: "lucide:circle-check", tone: "text-success", title: "Vender em comanda livre ou na já aberta aqui", note: "em dinheiro e na maquininha com chip e 4G próprios" },
  { icon: "lucide:circle-check", tone: "text-success", title: "Gaveta do Balcão e recibo", note: "a gaveta abre pelo agente; o recibo sai pela impressão do navegador" },
  { icon: "lucide:circle-x", tone: "text-destructive", title: "Pix, link de pagamento, entrega e encomenda", note: "esperam a conexão" },
  { icon: "lucide:circle-x", tone: "text-destructive", title: "Comanda em uso, envio à cozinha e desconto", note: "esperam a conexão; avise a cozinha de voz" },
  { icon: "lucide:triangle-alert", tone: "text-warning", title: "Nota fiscal", note: "sai quando a venda for enviada" },
] as const;

const pendingCount = computed(() => props.sales.filter((sale) => sale.status === "pending").length);
</script>

<template>
  <NuxtModal
    :open="open"
    title="Vendas sem conexão"
    :description="online ? 'As vendas guardadas são enviadas sozinhas.' : 'Sem conexão. O balcão continua vendendo neste dispositivo.'"
    :ui="{ content: 'sm:max-w-lg' }"
    data-pos-offline-sales
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <template #body>
      <div class="grid gap-4">
        <ul v-if="!online" class="grid gap-2" data-pos-offline-works>
          <li v-for="item in WORKS" :key="item.title" class="flex items-start gap-2">
            <Icon :name="item.icon" class="mt-0.5 size-4 shrink-0" :class="item.tone" aria-hidden="true" />
            <span class="min-w-0">
              <span class="block op-label">{{ item.title }}</span>
              <span class="block op-micro text-muted-foreground">{{ item.note }}</span>
            </span>
          </li>
        </ul>

        <p v-if="!durable" class="op-label text-destructive" role="alert">
          Este navegador não guarda as vendas no dispositivo: fechar esta aba perde as que estão na lista.
        </p>

        <p v-if="!sales.length" class="op-label text-muted-foreground" data-pos-offline-empty>
          Nenhuma venda esperando envio.
        </p>
        <ul v-else class="grid gap-2" data-pos-offline-list>
          <li
            v-for="sale in sales"
            :key="sale.id"
            class="grid gap-2 rounded-md border p-3"
            :class="sale.status === 'conflict' ? 'border-destructive/40 bg-destructive/5' : 'border-border'"
            :data-pos-offline-sale="sale.status"
          >
            <div class="flex items-baseline justify-between gap-3">
              <span class="op-label font-semibold">{{ clockLabel(sale.capturedAt) }} · {{ sale.paymentLabel }}</span>
              <span class="op-label font-semibold tnum">{{ formatBRL(sale.totalQ) }}</span>
            </div>
            <p v-if="sale.status === 'pending'" class="op-micro text-muted-foreground">
              {{ sale.itemCount === 1 ? "1 item" : `${sale.itemCount} itens` }} · espera envio
            </p>
            <template v-else>
              <p class="op-micro text-destructive">{{ sale.lastError?.message || "Esta venda não entrou." }}</p>
              <div class="flex flex-wrap gap-2">
                <NuxtButton
                  v-if="typeof sale.lastError?.newTotalQ === 'number'"
                  color="primary"
                  size="md"
                  :label="`Enviar com ${formatBRL(sale.lastError.newTotalQ)}`"
                  :disabled="!online || sending"
                  @click="emit('sendWithServerTotal', sale.id)"
                />
                <NuxtButton
                  color="neutral"
                  variant="outline"
                  size="md"
                  label="Tentar de novo"
                  :disabled="!online || sending"
                  @click="emit('retry', sale.id)"
                />
              </div>
            </template>
          </li>
        </ul>
      </div>
    </template>
    <template #footer>
      <div class="flex w-full flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <NuxtButton color="neutral" variant="outline" label="Fechar" @click="emit('update:open', false)" />
        <NuxtButton
          v-if="pendingCount"
          color="primary"
          :label="sending ? 'Enviando…' : 'Enviar agora'"
          :loading="sending"
          :disabled="!online || sending"
          @click="emit('sendNow')"
        />
      </div>
    </template>
  </NuxtModal>
</template>
