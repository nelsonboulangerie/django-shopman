<script setup lang="ts">
// Falar com o cliente do pedido (peça do `OperatorOrderDetail`). Um pedido é um
// combinado com uma pessoa, e quem abre o detalhe abre justamente quando algo precisa
// ser dito: o item acabou, o endereço não fecha, a entrega vai atrasar. Cada botão só
// existe quando tem para onde levar. `compact` (o cartão "Cliente" do detalhe em duas
// colunas e do celular, prévia v3 `depois-gestor-celular` (c)): WhatsApp e Ligar viram
// botões redondos de ícone, com o nome acessível por extenso.
import type { OperatorOrderDetail } from "../types/orderDetail";

defineProps<{
  order: OperatorOrderDetail;
  adminUrl: string;
  relayExpires: string;
  compact?: boolean;
}>();

const ROUND = "inline-grid size-11 place-items-center rounded-full border transition-colors hover:bg-accent";
const PILL = "inline-flex min-h-control min-w-control items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition-colors hover:bg-accent";
</script>

<template>
  <a
    v-if="order.customer_whatsapp_url"
    :href="order.customer_whatsapp_url"
    target="_blank"
    rel="noopener"
    :class="compact ? ROUND : PILL"
    :aria-label="compact ? 'WhatsApp do cliente' : undefined"
    data-contact-whatsapp
  >
    <Icon name="lucide:message-circle" class="size-4" /><template v-if="!compact"> WhatsApp</template>
  </a>
  <!-- Pedido do iFood: o número NÃO é do cliente. É o 0800 da central deles + um
       código que leva até a pessoa, e o código vence. Por isso não há WhatsApp aqui,
       e o "Ligar" disca os dois de uma vez. -->
  <div
    v-if="order.customer_relay_phone"
    class="flex w-full flex-wrap items-center gap-2 rounded-md bg-muted px-2.5 py-2 text-sm"
    data-contact-relay
  >
    <span class="text-muted-foreground">Falar pelo iFood:</span>
    <span class="tabular-nums">Central {{ order.customer_relay_phone }}</span>
    <template v-if="order.customer_relay_code">
      <span class="text-muted-foreground">·</span>
      <span class="font-semibold tabular-nums" data-contact-relay-code>Código {{ order.customer_relay_code }}</span>
      <span v-if="relayExpires" class="text-xs text-muted-foreground">{{ relayExpires }}</span>
    </template>
    <span v-else class="text-xs text-muted-foreground" data-contact-relay-expired>
      Código vencido: o iFood não repassa mais a ligação
    </span>
  </div>
  <a
    v-if="order.customer_phone_uri"
    :href="order.customer_phone_uri"
    :class="compact ? ROUND : PILL"
    :aria-label="compact ? (order.customer_relay_phone ? 'Ligar pela central' : 'Ligar para o cliente') : undefined"
    data-contact-phone
  >
    <Icon name="lucide:phone" class="size-4" /><template v-if="!compact"> {{ order.customer_relay_phone ? "Ligar pela central" : "Ligar" }}</template>
  </a>
  <a
    v-if="order.customer_email"
    :href="`mailto:${order.customer_email}`"
    :class="compact ? ROUND : PILL"
    :aria-label="compact ? 'E-mail do cliente' : undefined"
    data-contact-email
  >
    <Icon name="lucide:mail" class="size-4" /><template v-if="!compact"> E-mail</template>
  </a>
  <a
    v-if="adminUrl"
    :href="adminUrl"
    target="_blank"
    rel="noopener"
    class="inline-flex min-h-control min-w-control items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
    data-contact-cadastro
  >
    <Icon name="lucide:id-card" class="size-4" /> Abrir cadastro
  </a>
</template>
