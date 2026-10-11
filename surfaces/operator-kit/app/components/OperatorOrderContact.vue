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

</script>

<template>
  <NuxtButton
    v-if="order.customer_whatsapp_url"
    :to="order.customer_whatsapp_url"
    target="_blank"
    color="neutral"
    variant="outline"
    icon="i-lucide-message-circle"
    :label="compact ? undefined : 'WhatsApp'"
    :aria-label="compact ? 'WhatsApp do cliente' : 'WhatsApp'"
    data-contact-whatsapp
  />
  <!-- Pedido do iFood: o número NÃO é do cliente. É o 0800 da central deles + um
       código que leva até a pessoa, e o código vence. Por isso não há WhatsApp aqui,
       e o "Ligar" disca os dois de uma vez. -->
  <NuxtAlert
    v-if="order.customer_relay_phone"
    color="info"
    variant="subtle"
    icon="i-lucide-phone-call"
    title="Falar pelo iFood"
    data-contact-relay
  >
    <template #description>
      <span>Central {{ order.customer_relay_phone }}</span>
      <template v-if="order.customer_relay_code">
        · <span data-contact-relay-code>Código {{ order.customer_relay_code }}</span>
        <template v-if="relayExpires"> · {{ relayExpires }}</template>
      </template>
      <span v-else data-contact-relay-expired> · Código vencido: o iFood não repassa mais a ligação</span>
    </template>
  </NuxtAlert>
  <NuxtButton
    v-if="order.customer_phone_uri"
    :to="order.customer_phone_uri"
    color="neutral"
    variant="outline"
    icon="i-lucide-phone"
    :label="compact ? undefined : (order.customer_relay_phone ? 'Ligar pela central' : 'Ligar')"
    :aria-label="compact ? (order.customer_relay_phone ? 'Ligar pela central' : 'Ligar para o cliente') : (order.customer_relay_phone ? 'Ligar pela central' : 'Ligar')"
    data-contact-phone
  />
  <NuxtButton
    v-if="order.customer_email"
    :to="`mailto:${order.customer_email}`"
    color="neutral"
    variant="outline"
    icon="i-lucide-mail"
    :label="compact ? undefined : 'E-mail'"
    :aria-label="compact ? 'E-mail do cliente' : 'E-mail'"
    data-contact-email
  />
  <NuxtButton
    v-if="adminUrl"
    :to="adminUrl"
    target="_blank"
    color="neutral"
    variant="ghost"
    icon="i-lucide-id-card"
    label="Abrir cadastro"
    data-contact-cadastro
  />
</template>
