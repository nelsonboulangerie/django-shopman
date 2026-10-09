<script setup lang="ts">
// Comprovante dos avisos ao cliente (D3). O servidor decide o estado de cada aviso
// (`shopman/backstage/projections/notification_receipts.py`); a tela só mostra. A
// regra é dele também: "Entregue" só com comprovante do provedor; aceite sem
// identificador aparece como "Aceito pelo provedor, sem comprovante".
// O que cada estado prova (e não prova): docs/reference/comprovante-de-entrega.md.
import type { NotificationReceiptProjection } from "~/generated/ordersContract";

defineProps<{ receipts?: readonly NotificationReceiptProjection[] }>();

const toneColor = (
  tone: string,
): "success" | "warning" | "error" | "neutral" =>
  tone === "ok"
    ? "success"
    : tone === "danger"
      ? "error"
      : tone === "warning"
        ? "warning"
        : "neutral";
</script>

<template>
  <NuxtCard v-if="receipts?.length" as="section" data-notification-receipts>
    <template #header>
      <div class="flex items-center justify-between gap-3">
        <h2 class="op-title">Avisos ao cliente</h2>
        <NuxtBadge
          color="neutral"
          :label="String(receipts.length)"
        />
      </div>
    </template>
    <ol class="flex flex-col gap-3">
      <li
        v-for="(receipt, i) in receipts"
        :key="i"
        class="flex flex-col gap-1 text-sm"
        :data-receipt-state="receipt.state"
      >
        <div class="flex flex-wrap items-center gap-2">
          <span class="font-medium">{{ receipt.label }}</span>
          <NuxtBadge
            v-if="receipt.critical"
            color="error"
            label="crítico"
            data-receipt-critical
          />
          <NuxtBadge
            :color="toneColor(receipt.tone)"
            :label="receipt.state_label"
            data-receipt-label
          />
        </div>
        <p class="text-xs text-muted-foreground">
          {{ receipt.time_display
          }}<template v-if="receipt.channel_label">
            · {{ receipt.channel_label }}</template
          >
        </p>
        <p
          v-if="receipt.provider_id"
          class="break-all text-xs text-muted-foreground"
          data-receipt-provider-id
        >
          Comprovante: <span class="font-mono">{{ receipt.provider_id }}</span>
        </p>
        <p
          v-if="receipt.detail"
          class="text-xs text-muted-foreground"
          data-receipt-detail
        >
          {{ receipt.detail }}
        </p>
        <ul
          v-if="receipt.attempts.length > 1"
          class="ms-3 flex flex-col gap-0.5 border-s ps-3 text-xs text-muted-foreground"
          data-receipt-attempts
        >
          <li v-for="(attempt, j) in receipt.attempts" :key="j">
            {{ attempt.channel_label }}: {{ attempt.outcome_label
            }}<template v-if="attempt.time_display"
              >, {{ attempt.time_display }}</template
            >
          </li>
        </ul>
      </li>
    </ol>
  </NuxtCard>
</template>
