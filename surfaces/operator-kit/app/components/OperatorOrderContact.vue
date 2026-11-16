<script setup lang="ts">
// Falar com o cliente do pedido (peça do `OperatorOrderDetail`). Um pedido é um
// combinado com uma pessoa, e quem abre o detalhe abre justamente quando algo precisa
// ser dito: o item acabou, o endereço não fecha, a entrega vai atrasar. Cada botão só
// existe quando tem para onde levar. `compact` (o cartão "Cliente" do detalhe em duas
// colunas e do celular, prévia v3 `depois-gestor-celular` (c)): WhatsApp e Ligar viram
// botões redondos de ícone, com o nome acessível por extenso.
import type { OperatorOrderDetail } from "../types/orderDetail";

withDefaults(defineProps<{
  order: OperatorOrderDetail;
  adminUrl: string;
  compact?: boolean;
  external?: boolean;
}>(), { compact: false, external: true });

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
  <!-- Pedido do iFood: o número NÃO é do cliente, é o 0800 da central deles com um
       código que vence. Ele não entra aqui: fica no rodapé do detalhe, sem destaque
       (dono, 12/11/2026: "pró-forma"). -->
  <NuxtButton
    v-if="order.customer_phone_uri && !order.customer_relay_phone"
    :to="order.customer_phone_uri"
    color="neutral"
    variant="outline"
    icon="i-lucide-phone"
    :label="compact ? undefined : 'Ligar'"
    :aria-label="compact ? 'Ligar para o cliente' : 'Ligar'"
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
    :target="external ? '_blank' : undefined"
    color="neutral"
    variant="ghost"
    icon="i-lucide-id-card"
    label="Abrir cadastro"
    data-contact-cadastro
  />
</template>
