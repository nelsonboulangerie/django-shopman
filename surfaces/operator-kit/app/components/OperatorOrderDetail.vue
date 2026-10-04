<script setup lang="ts">
// O DETALHE DE UM PEDIDO — a mesma tela no Gestor e no PDV.
//
// Decisão do dono (28/09/2026): o detalhe do pedido do Gestor e o da encomenda no
// PDV são telas IRMÃS. A estrutura e o conteúdo são estes, nesta ordem — resumo,
// cliente, nota fiscal, itens, observação do cliente, nota da cozinha, histórico
// —, e o que muda de uma tela para a outra entra pelos slots:
//
//   #summary        linhas a mais no resumo (iFood no Gestor; saldo no PDV)
//   #actions        a barra de ações do contexto (a régua é do servidor)
//   #after-profile  blocos do contexto depois do cliente (entregador no Gestor)
//   #kitchen-note   o editor da nota da cozinha, onde a tela a edita; sem ele a
//                   nota aparece só para ler
//
// `layout` (G14 da auditoria v4, prévia v3 `depois-gestor-detalhe`): "stack" é a coluna
// única de sempre (o PDV); "split" é o detalhe do Gestor em duas colunas — itens, total
// e notas à esquerda; Cliente e Linha do tempo à direita — com o mesmo conteúdo. Abaixo
// de `lg` as duas colunas viram uma, na ordem do celular (prévia v3
// `depois-gestor-celular` (c)): resumo, cliente, itens, notas, linha do tempo. O layout é
// do componente, não do contexto: o PDV não passa nada e continua igual.
//
// O servidor decide o que cada contexto pode (`build_operator_order(context=…)`):
// o comentário no histórico só aparece quando a ação `comment` vem habilitada.
// Os diálogos de cada gesto continuam na página de cada app.
import { computed } from "vue";

import OperatorOrderContact from "./OperatorOrderContact.vue";
import OperatorOrderProfileLines from "./OperatorOrderProfileLines.vue";
import OperatorOrderTimeline from "./OperatorOrderTimeline.vue";
import {
  customerAdminUrl as adminUrlFor,
  fiscalHref,
  hasCustomerContact,
  lucideIcon,
  relayExpiresLabel,
  statusTone,
  toneBadge,
} from "../presentation/orderDetail";
import type { OperatorOrderDetail } from "../types/orderDetail";

const props = withDefaults(
  defineProps<{
    order: OperatorOrderDetail;
    busy?: boolean;
    /** Endereço do Admin (o cadastro do cliente ainda mora lá). Vazio: sem o link. */
    adminBaseUrl?: string;
    /** A etiqueta de status do pedido no resumo. Padrão: aparece (o Gestor).
     *  A tela que já diz a situação com a etiqueta dela desliga esta, para não
     *  mostrar duas etiquetas de estado com vocabulários diferentes (o PDV,
     *  com a situação do balcão; P5 do dono, 02/10). */
    showStatus?: boolean;
    /** "stack": coluna única (padrão, o PDV). "split": duas colunas (o Gestor). */
    layout?: "stack" | "split";
    /** Só o que pede decisão (quem está fora da loja, G18): sem fiscal nem comentar. */
    decisionOnly?: boolean;
  }>(),
  { busy: false, adminBaseUrl: "", showStatus: true, layout: "stack", decisionOnly: false },
);

const emit = defineEmits<{ comment: [note: string] }>();
/** O rascunho do comentário mora na página: é ela que avisa texto não salvo. */
const comment = defineModel<string>("comment", { default: "" });

const adminUrl = computed(() => adminUrlFor(props.adminBaseUrl, props.order.customer_ref));
const relayExpires = computed(() => relayExpiresLabel(props.order.customer_relay_expires_at));
const showContact = computed(() => hasCustomerContact(props.order, adminUrl.value));
const profile = computed(() => props.order.customer_profile);
const split = computed(() => props.layout === "split");
/** "Loja online · WEB-261004-V12 · aberto às 09:51 · Retirada": quem, de onde, quando. */
const metaLine = computed(() =>
  [props.order.channel_name || props.order.channel_ref, props.order.ref, props.order.opened_line, props.order.fulfillment_label].filter(Boolean),
);
</script>

<template>
  <div
    :class="split ? 'flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(300px,380px)] lg:items-start lg:gap-4' : 'flex flex-col gap-4'"
    data-order-detail
    :data-order-context="order.context"
    :data-order-layout="layout"
  >
    <!-- ══ COLUNA ÚNICA (o PDV e o padrão) ═════════════════════════════════════ -->
    <template v-if="!split">
      <!-- Homologação do iFood contra o ambiente VIVO: o pedido de teste avança
           como qualquer outro, e o detalhe é onde o operador decide o que fazer
           com ele. O aviso abre a tela, acima do resumo. -->
      <p
        v-if="order.test_order_notice"
        class="flex items-start gap-2 rounded-lg border border-warning/50 bg-warning/15 p-3 text-sm font-medium"
        role="status"
        data-test-order-notice
      >
        <Icon name="lucide:flask-conical" class="mt-0.5 size-4 shrink-0" />
        <span>{{ order.test_order_notice }}</span>
      </p>

      <!-- resumo -->
      <section class="flex flex-col gap-3 rounded-lg border bg-card p-4" data-order-summary>
        <div class="flex flex-wrap items-center gap-2">
          <span v-if="showStatus" class="inline-flex items-center rounded-md border px-2 py-0.5 text-sm font-medium" :class="toneBadge(statusTone(order.status))" data-order-status>
            {{ order.status_label }}
          </span>
          <span class="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
            <Icon :name="`lucide:${lucideIcon(order.channel_icon)}`" class="size-4" /> {{ order.channel_name || order.channel_ref }}
          </span>
          <span class="ml-auto text-xl font-bold tabular-nums" data-order-total>{{ order.total_display }}</span>
        </div>
        <div class="grid gap-1 text-sm">
          <p class="flex items-center gap-2">
            <Icon name="lucide:user" class="size-4 text-muted-foreground" /> {{ order.customer_name || "Sem cliente" }}
            <span v-if="order.customer_phone && order.customer_phone !== order.customer_name" class="text-muted-foreground tabular-nums" data-customer-phone>
              · {{ order.customer_phone }}
            </span>
          </p>
          <p class="flex items-center gap-2 text-muted-foreground"><Icon name="lucide:package" class="size-4" /> {{ order.fulfillment_label }}</p>
          <!-- Quando o combinado acontece (encomenda, ou retirada com janela). -->
          <p v-if="order.schedule_label" class="flex items-center gap-2" data-order-schedule>
            <Icon name="lucide:calendar-clock" class="size-4 text-muted-foreground" /> {{ order.schedule_label }}
          </p>
          <!-- Para onde vai. Quem despacha não tinha o endereço em tela nenhuma
               do Gestor, embora o pedido sempre o carregasse. -->
          <p v-if="order.delivery_address" class="flex items-start gap-2" data-order-address>
            <Icon name="lucide:map-pin" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
            <span class="min-w-0">
              {{ order.delivery_address }}
              <span v-if="order.delivery_instructions" class="block text-muted-foreground">{{ order.delivery_instructions }}</span>
            </span>
          </p>
          <p class="flex items-center gap-2 text-muted-foreground"><Icon name="lucide:wallet" class="size-4" /> {{ order.payment_method_label || "Pagamento não informado" }}<template v-if="order.payment_status_label"> · {{ order.payment_status_label }}</template></p>
          <slot name="summary" />
          <!-- Prova de envio do link de pagamento: "Enviando…", "Link enviado
               às 14h32" ou "falhou — reenvie". Lida da última Directive do
               aviso; sem aviso nenhum, a linha não existe. -->
          <p v-if="order.payment_link_notice" class="flex items-center gap-2 text-muted-foreground" data-payment-link-notice>
            <Icon name="lucide:send" class="size-4" /> {{ order.payment_link_notice }}
          </p>
        </div>

        <!-- Falar com o cliente: cada botão só existe quando tem para onde levar. -->
        <div v-if="showContact" class="flex flex-wrap gap-2 border-t pt-3" data-customer-contact>
          <OperatorOrderContact :order="order" :admin-url="adminUrl" :relay-expires="relayExpires" />
        </div>

        <!-- presente: destinatário é OPCIONAL na retirada (gift.py) — sem nome o
             pedido continua presente, e a instrução vira "embalar", não
             "entregar a alguém" com o nome pendurado no vazio. -->
        <div v-if="order.is_gift" class="rounded-md bg-muted/60 p-2.5 text-sm" data-gift-block>
          <p class="flex items-center gap-1.5 font-medium">
            <Icon name="lucide:gift" class="size-4" />
            {{ order.gift_recipient_name ? `Presente para ${order.gift_recipient_name}` : "Embalar para presente" }}
          </p>
          <p v-if="order.gift_recipient_phone" class="mt-1 flex items-center gap-1.5 text-muted-foreground" data-gift-phone>
            <Icon name="lucide:phone" class="size-3.5" /> {{ order.gift_recipient_phone }}
          </p>
          <p v-if="order.gift_message" class="mt-1 text-muted-foreground">“{{ order.gift_message }}”</p>
          <!-- instrução operacional: nada de valores junto do presente. -->
          <p
            v-if="order.gift_hide_values"
            class="mt-1.5 inline-flex items-center gap-1 rounded-md border border-warning/50 px-1.5 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400"
            data-gift-hide-values
          >
            <Icon name="lucide:eye-off" class="size-3" /> Não mostrar valores
          </p>
        </div>
      </section>

      <!-- A barra de ações do contexto: a única parte que muda de uma tela para
           a outra. O servidor decide cada gesto; a página só liga os diálogos. -->
      <slot name="actions" />

      <!-- quem é este cliente (WP-360): só com cliente identificado. -->
      <section v-if="profile" class="flex flex-col gap-1.5 rounded-lg border bg-card p-4 text-sm" data-customer-profile>
        <div class="flex flex-wrap items-center gap-2">
          <h2 class="flex items-center gap-1.5 text-sm font-bold uppercase tracking-wide">
            <Icon name="lucide:user-round" class="size-4 text-muted-foreground" /> Cliente
          </h2>
          <!-- Selo só nos segmentos que mudam o atendimento. -->
          <span
            v-if="profile.segment_tone"
            class="inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium"
            :class="toneBadge(profile.segment_tone)"
            data-customer-segment
          >
            {{ profile.segment_label }}
          </span>
        </div>
        <OperatorOrderProfileLines :profile="profile" />
      </section>

      <slot name="after-profile" />

      <!-- nota fiscal -->
      <section v-if="!decisionOnly && (order.fiscal_status_label || order.fiscal_links.length)" class="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3 text-sm" data-order-fiscal>
        <Icon name="lucide:receipt" class="size-4 text-muted-foreground" />
        <span class="text-muted-foreground">{{ order.fiscal_status_label || "Fiscal" }}</span>
        <a v-for="(link, i) in order.fiscal_links" :key="i" :href="fiscalHref(link)" target="_blank" rel="noopener" class="font-medium text-primary underline-offset-2 hover:underline">
          {{ link.label || "Documento" }}
        </a>
      </section>

      <!-- itens: os que VALEM agora, com os ajustes -->
      <section class="overflow-hidden rounded-lg border bg-card" data-order-items>
        <h2 class="border-b px-4 py-2.5 text-sm font-bold uppercase tracking-wide">Itens</h2>
        <table class="w-full text-sm">
          <tbody>
            <tr v-for="(item, i) in order.items" :key="i" class="border-b last:border-0">
              <td class="px-4 py-2.5 tabular-nums text-muted-foreground">{{ item.qty }}×</td>
              <td class="px-1 py-2.5">{{ item.name }}</td>
              <td class="px-4 py-2.5 text-right tabular-nums">{{ item.total_display }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <!-- observação do CLIENTE (order_notes): somente leitura. -->
      <section v-if="order.customer_note" class="flex flex-col gap-1.5 rounded-lg border bg-card p-4" data-customer-note>
        <h2 class="flex items-center gap-1.5 text-sm font-bold uppercase tracking-wide">
          <Icon name="lucide:message-square" class="size-4 text-muted-foreground" /> Observação do cliente
        </h2>
        <p class="whitespace-pre-line text-sm">{{ order.customer_note }}</p>
      </section>

      <!-- nota da cozinha: o editor entra pelo slot onde a tela a edita (Gestor);
           nas outras ela é leitura, e só existe quando há o que ler. -->
      <slot name="kitchen-note">
        <section v-if="order.kitchen_note" class="flex flex-col gap-1.5 rounded-lg border bg-card p-4" data-kitchen-note>
          <h2 class="text-sm font-bold uppercase tracking-wide">Nota da cozinha</h2>
          <p class="whitespace-pre-line text-sm">{{ order.kitchen_note }}</p>
          <p class="text-xs text-muted-foreground">Aparece no ticket da cozinha (KDS).</p>
        </section>
      </slot>

      <OperatorOrderTimeline v-model:comment="comment" :order="order" :busy="busy" :read-only="decisionOnly" @comment="(note) => emit('comment', note)" />
    </template>

    <!-- ══ DUAS COLUNAS (o Gestor) ══════════════════════════════════════════════
         As colunas são `contents` abaixo de `lg`: as seções viram uma coluna só,
         ordenadas pelo `order-*` na sequência do celular. -->
    <template v-else>
      <div class="contents lg:flex lg:min-w-0 lg:flex-col lg:gap-4">
        <p
          v-if="order.test_order_notice"
          class="order-0 flex items-start gap-2 rounded-lg border border-warning/50 bg-warning/15 p-3 text-sm font-medium lg:order-none"
          role="status"
          data-test-order-notice
        >
          <Icon name="lucide:flask-conical" class="mt-0.5 size-4 shrink-0" />
          <span>{{ order.test_order_notice }}</span>
        </p>

        <!-- o pedido: de onde e quando, os itens que valem e o total (v3) -->
        <section class="order-3 overflow-hidden rounded-lg border bg-card lg:order-none" data-order-summary>
          <p class="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 border-b px-4 py-2.5 op-micro text-muted-foreground" data-order-meta>
            <Icon :name="`lucide:${lucideIcon(order.channel_icon)}`" class="size-4" />
            <template v-for="(part, i) in metaLine" :key="i"><span v-if="i" aria-hidden="true">·</span><span :class="part === order.ref ? 'tnum' : ''">{{ part }}</span></template>
          </p>
          <table class="w-full text-sm" data-order-items>
            <tbody>
              <tr v-for="(item, i) in order.items" :key="i" class="border-b">
                <td class="w-12 py-3 pl-4 font-semibold tabular-nums">{{ item.qty }}×</td>
                <td class="px-1 py-3 op-body">{{ item.name }}</td>
                <td class="py-3 pr-4 text-right tabular-nums">{{ item.total_display }}</td>
              </tr>
            </tbody>
          </table>
          <div class="flex items-baseline justify-between gap-3 px-4 py-3">
            <span class="op-label text-muted-foreground">Total</span>
            <span class="text-2xl font-bold tabular-nums" data-order-total>{{ order.total_display }}</span>
          </div>
          <div class="grid gap-1 border-t px-4 py-3 text-sm">
            <p v-if="order.schedule_label" class="flex items-center gap-2" data-order-schedule>
              <Icon name="lucide:calendar-clock" class="size-4 text-muted-foreground" /> {{ order.schedule_label }}
            </p>
            <p v-if="order.delivery_address" class="flex items-start gap-2" data-order-address>
              <Icon name="lucide:map-pin" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <span class="min-w-0">
                {{ order.delivery_address }}
                <span v-if="order.delivery_instructions" class="block text-muted-foreground">{{ order.delivery_instructions }}</span>
              </span>
            </p>
            <p class="flex items-center gap-2 text-muted-foreground"><Icon name="lucide:wallet" class="size-4" /> {{ order.payment_method_label || "Pagamento não informado" }}<template v-if="order.payment_status_label"> · {{ order.payment_status_label }}</template></p>
            <slot name="summary" />
            <p v-if="order.payment_link_notice" class="flex items-center gap-2 text-muted-foreground" data-payment-link-notice>
              <Icon name="lucide:send" class="size-4" /> {{ order.payment_link_notice }}
            </p>
          </div>
          <div v-if="order.is_gift" class="mx-4 mb-3 rounded-md bg-muted/60 p-2.5 text-sm" data-gift-block>
            <p class="flex items-center gap-1.5 font-medium">
              <Icon name="lucide:gift" class="size-4" />
              {{ order.gift_recipient_name ? `Presente para ${order.gift_recipient_name}` : "Embalar para presente" }}
            </p>
            <p v-if="order.gift_recipient_phone" class="mt-1 flex items-center gap-1.5 text-muted-foreground" data-gift-phone>
              <Icon name="lucide:phone" class="size-3.5" /> {{ order.gift_recipient_phone }}
            </p>
            <p v-if="order.gift_message" class="mt-1 text-muted-foreground">“{{ order.gift_message }}”</p>
            <p v-if="order.gift_hide_values" class="mt-1.5 inline-flex items-center gap-1 rounded-md border border-warning/50 px-1.5 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400" data-gift-hide-values>
              <Icon name="lucide:eye-off" class="size-3" /> Não mostrar valores
            </p>
          </div>
        </section>

        <div v-if="$slots.actions" class="order-1 min-w-0 empty:hidden lg:order-none">
          <slot name="actions" />
        </div>

        <section v-if="order.customer_note" class="order-4 flex flex-col gap-1.5 rounded-lg border bg-card p-4 lg:order-none" data-customer-note>
          <h2 class="flex items-center gap-1.5 text-sm font-bold uppercase tracking-wide">
            <Icon name="lucide:message-square" class="size-4 text-muted-foreground" /> Observação do cliente
          </h2>
          <p class="whitespace-pre-line text-sm">{{ order.customer_note }}</p>
        </section>

        <div class="order-5 min-w-0 empty:hidden lg:order-none">
          <slot name="kitchen-note">
            <section v-if="order.kitchen_note" class="flex flex-col gap-1.5 rounded-lg border bg-card p-4" data-kitchen-note>
              <h2 class="text-sm font-bold uppercase tracking-wide">Nota da cozinha</h2>
              <p class="whitespace-pre-line text-sm">{{ order.kitchen_note }}</p>
              <p class="text-xs text-muted-foreground">Aparece no ticket da cozinha (KDS).</p>
            </section>
          </slot>
        </div>

        <div v-if="$slots['after-profile']" class="order-7 flex min-w-0 flex-col gap-4 empty:hidden lg:order-none">
          <slot name="after-profile" />
        </div>

        <section v-if="!decisionOnly && (order.fiscal_status_label || order.fiscal_links.length)" class="order-8 flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3 text-sm lg:order-none" data-order-fiscal>
          <Icon name="lucide:receipt" class="size-4 text-muted-foreground" />
          <span class="text-muted-foreground">{{ order.fiscal_status_label || "Fiscal" }}</span>
          <a v-for="(link, i) in order.fiscal_links" :key="i" :href="fiscalHref(link)" target="_blank" rel="noopener" class="font-medium text-primary underline-offset-2 hover:underline">
            {{ link.label || "Documento" }}
          </a>
        </section>
      </div>

      <div class="contents lg:flex lg:min-w-0 lg:flex-col lg:gap-4">
        <!-- Cliente: quem é, como falar e o que a casa sabe dela -->
        <section class="order-2 flex flex-col gap-2 rounded-lg border bg-card p-4 text-sm lg:order-none" data-customer-card>
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="op-eyebrow">Cliente</h2>
            <span
              v-if="profile?.segment_tone"
              class="inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium"
              :class="toneBadge(profile.segment_tone)"
              data-customer-segment
            >{{ profile.segment_label }}</span>
          </div>
          <div class="flex items-center gap-3">
            <div class="min-w-0 flex-1">
              <p class="op-title break-words">{{ order.customer_name || "Sem cliente" }}</p>
              <p v-if="order.customer_phone && order.customer_phone !== order.customer_name" class="tabular-nums text-muted-foreground" data-customer-phone>{{ order.customer_phone }}</p>
            </div>
            <div v-if="order.customer_whatsapp_url || (order.customer_phone_uri && !order.customer_relay_phone)" class="flex shrink-0 gap-2" data-customer-contact>
              <OperatorOrderContact :order="{ ...order, customer_relay_phone: '', customer_email: '' }" admin-url="" relay-expires="" compact />
            </div>
          </div>
          <div v-if="order.customer_relay_phone || order.customer_email || adminUrl" class="flex flex-wrap gap-2" data-customer-contact-more>
            <OperatorOrderContact :order="{ ...order, customer_whatsapp_url: '', customer_phone_uri: order.customer_relay_phone ? order.customer_phone_uri : '' }" :admin-url="adminUrl" :relay-expires="relayExpires" />
          </div>
          <div v-if="profile" class="flex flex-col gap-1" data-customer-profile>
            <OperatorOrderProfileLines :profile="profile" />
          </div>
        </section>

        <OperatorOrderTimeline
          v-model:comment="comment"
          class="order-6 lg:order-none"
          :order="order"
          :busy="busy"
          :read-only="decisionOnly"
          title="Linha do tempo"
          @comment="(note) => emit('comment', note)"
        />
      </div>
    </template>
  </div>
</template>
