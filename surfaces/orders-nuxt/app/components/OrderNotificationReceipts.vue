<script setup lang="ts">
// Comprovante dos avisos ao cliente (D3). O servidor decide o estado de cada aviso
// (`shopman/backstage/projections/notification_receipts.py`); a tela só mostra. A
// regra é dele também: "Entregue" só com comprovante do provedor; aceite sem
// identificador aparece como "Aceito pelo provedor, sem comprovante".
// O que cada estado prova (e não prova): docs/reference/comprovante-de-entrega.md.
import type { NotificationReceiptProjection } from "~/generated/ordersContract";

defineProps<{ receipts?: readonly NotificationReceiptProjection[] }>();

const toneClass: Record<string, string> = {
  ok: "border-success/40 bg-success/10 text-foreground",
  warning: "border-warning/40 bg-warning/10 text-foreground",
  danger: "border-destructive/40 bg-destructive/10 text-destructive dark:text-orange-300",
  muted: "border-border bg-muted text-muted-foreground",
};
</script>

<template>
  <section v-if="receipts?.length" class="flex flex-col gap-2 rounded-lg border bg-card p-4" data-notification-receipts>
    <h2 class="text-sm font-bold uppercase tracking-wide">Avisos ao cliente</h2>
    <ol class="flex flex-col gap-3">
      <li v-for="(receipt, i) in receipts" :key="i" class="flex flex-col gap-1 text-sm" :data-receipt-state="receipt.state">
        <div class="flex flex-wrap items-center gap-2">
          <span class="font-medium">{{ receipt.label }}</span>
          <span v-if="receipt.critical" class="text-xs text-muted-foreground" data-receipt-critical>crítico</span>
          <span class="rounded-full border px-2 py-0.5 text-xs font-medium" :class="toneClass[receipt.tone] || toneClass.muted" data-receipt-label>
            {{ receipt.state_label }}
          </span>
        </div>
        <p class="text-xs text-muted-foreground">
          {{ receipt.time_display }}<template v-if="receipt.channel_label"> · {{ receipt.channel_label }}</template>
        </p>
        <p v-if="receipt.provider_id" class="break-all text-xs text-muted-foreground" data-receipt-provider-id>
          Comprovante: <span class="font-mono">{{ receipt.provider_id }}</span>
        </p>
        <p v-if="receipt.detail" class="text-xs text-muted-foreground" data-receipt-detail>{{ receipt.detail }}</p>
        <ul v-if="receipt.attempts.length > 1" class="ml-3 flex flex-col gap-0.5 border-l pl-3 text-xs text-muted-foreground" data-receipt-attempts>
          <li v-for="(attempt, j) in receipt.attempts" :key="j">
            {{ attempt.channel_label }}: {{ attempt.outcome_label }}<template v-if="attempt.time_display">, {{ attempt.time_display }}</template>
          </li>
        </ul>
      </li>
    </ol>
  </section>
</template>
