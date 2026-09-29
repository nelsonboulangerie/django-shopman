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
// O servidor decide o que cada contexto pode (`build_operator_order(context=…)`):
// o comentário no histórico só aparece quando a ação `comment` vem habilitada.
// Os diálogos de cada gesto continuam na página de cada app.
import { computed } from "vue";

import {
  canComment as canCommentOn,
  customerAdminUrl as adminUrlFor,
  fiscalHref,
  hasCustomerContact,
  lucideIcon,
  profileHabits,
  profileHistory,
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
  }>(),
  { busy: false, adminBaseUrl: "" },
);

const emit = defineEmits<{ comment: [note: string] }>();
/** O rascunho do comentário mora na página: é ela que avisa texto não salvo. */
const comment = defineModel<string>("comment", { default: "" });

const adminUrl = computed(() => adminUrlFor(props.adminBaseUrl, props.order.customer_ref));
const relayExpires = computed(() => relayExpiresLabel(props.order.customer_relay_expires_at));
const showContact = computed(() => hasCustomerContact(props.order, adminUrl.value));
const profile = computed(() => props.order.customer_profile);
const history = computed(() => profileHistory(profile.value));
const habits = computed(() => profileHabits(profile.value));
const commentAllowed = computed(() => canCommentOn(props.order));

function submitComment() {
  const note = comment.value.trim();
  if (!note || props.busy) return;
  emit("comment", note);
}
</script>

<template>
  <div class="flex flex-col gap-4" data-order-detail :data-order-context="order.context">
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
        <span class="inline-flex items-center rounded-md border px-2 py-0.5 text-sm font-medium" :class="toneBadge(statusTone(order.status))" data-order-status>
          {{ order.status_label }}
        </span>
        <span class="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
          <Icon :name="`lucide:${lucideIcon(order.channel_icon)}`" class="size-4" /> {{ order.channel_ref }}
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

      <!-- Falar com o cliente. Um pedido é um combinado com uma pessoa, e
           quem abre o detalhe abre justamente quando algo precisa ser dito:
           o item acabou, o endereço não fecha, a entrega vai atrasar. Cada
           botão só existe quando tem para onde levar. -->
      <div v-if="showContact" class="flex flex-wrap gap-2 border-t pt-3" data-customer-contact>
        <a
          v-if="order.customer_whatsapp_url"
          :href="order.customer_whatsapp_url"
          target="_blank"
          rel="noopener"
          class="inline-flex min-h-control min-w-control items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition-colors hover:bg-accent"
          data-contact-whatsapp
        >
          <Icon name="lucide:message-circle" class="size-4" /> WhatsApp
        </a>
        <!-- Pedido do iFood: o número NÃO é do cliente. É o 0800 da central
             deles + um código que leva até a pessoa, e o código vence. Por
             isso não há WhatsApp aqui, e o "Ligar" disca os dois de uma vez. -->
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
          class="inline-flex min-h-control min-w-control items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition-colors hover:bg-accent"
          data-contact-phone
        >
          <Icon name="lucide:phone" class="size-4" /> {{ order.customer_relay_phone ? "Ligar pela central" : "Ligar" }}
        </a>
        <a
          v-if="order.customer_email"
          :href="`mailto:${order.customer_email}`"
          class="inline-flex min-h-control min-w-control items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-sm font-medium transition-colors hover:bg-accent"
          data-contact-email
        >
          <Icon name="lucide:mail" class="size-4" /> E-mail
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
        <!-- instrução operacional: nada de valores junto do presente (sem
             cupom/valor na sacola). -->
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

    <!-- quem é este cliente (WP-360) — o operador abria o detalhe sem saber se
         quem está do outro lado é da casa ou comprou pela primeira vez. O
         bloco só existe com cliente identificado, e cada linha só aparece com
         o dado que o servidor de fato tem. -->
    <section v-if="profile" class="flex flex-col gap-1.5 rounded-lg border bg-card p-4 text-sm" data-customer-profile>
      <div class="flex flex-wrap items-center gap-2">
        <h2 class="flex items-center gap-1.5 text-sm font-bold uppercase tracking-wide">
          <Icon name="lucide:user-round" class="size-4 text-muted-foreground" /> Cliente
        </h2>
        <!-- Selo só nos segmentos que mudam o atendimento (fiel/campeão, em
             risco/perdido). Badge que aparece sempre deixa de ser lido. -->
        <span
          v-if="profile.segment_tone"
          class="inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium"
          :class="toneBadge(profile.segment_tone)"
          data-customer-segment
        >
          {{ profile.segment_label }}
        </span>
      </div>
      <p v-if="history" data-customer-history>{{ history }}</p>
      <p v-if="habits" class="text-muted-foreground" data-customer-habits>{{ habits }}</p>
      <!-- Aniversário: no dia, é gesto de casa; fora dele, é só cadastro. -->
      <p v-if="profile.birthday_display" class="flex items-center gap-1.5" :class="profile.is_birthday_today ? 'font-medium' : 'text-muted-foreground'" data-customer-birthday>
        <Icon name="lucide:cake" class="size-3.5 shrink-0" />
        {{ profile.is_birthday_today ? "Faz aniversário hoje" : `Aniversário em ${profile.birthday_display}` }}
      </p>
      <!-- Restrição alimentar é a única linha deste bloco que pode virar
           incidente se passar batido — por isso tom de atenção, não cinza. -->
      <p v-if="profile.dietary_restrictions" class="flex items-start gap-1.5 font-medium text-amber-700 dark:text-amber-400" data-customer-restrictions>
        <Icon name="lucide:triangle-alert" class="mt-0.5 size-3.5 shrink-0" />
        <span>{{ profile.dietary_restrictions }}</span>
      </p>
      <p v-if="profile.notes" class="flex items-start gap-1.5 text-muted-foreground" data-customer-notes>
        <Icon name="lucide:sticky-note" class="mt-0.5 size-3.5 shrink-0" />
        <span>{{ profile.notes }}</span>
      </p>
    </section>

    <slot name="after-profile" />

    <!-- nota fiscal -->
    <section v-if="order.fiscal_status_label || order.fiscal_links.length" class="flex flex-wrap items-center gap-2 rounded-lg border bg-card p-3 text-sm" data-order-fiscal>
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

    <!-- observação do CLIENTE (order_notes, escrita no checkout): somente
         leitura, dona diferente da nota da cozinha logo abaixo — o operador
         edita a dele, nunca a do cliente. -->
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

    <!-- histórico -->
    <section class="flex flex-col gap-2 rounded-lg border bg-card p-4" data-order-timeline>
      <h2 class="text-sm font-bold uppercase tracking-wide">Histórico</h2>
      <ol v-if="order.timeline.length" class="flex flex-col gap-2.5">
        <li v-for="(ev, i) in order.timeline" :key="i" class="flex gap-3 text-sm">
          <span class="mt-1 size-2 shrink-0 rounded-full" :class="ev.event_type === 'operator_comment' ? 'bg-primary' : 'bg-muted-foreground/40'" />
          <div class="min-w-0">
            <p class="font-medium">{{ ev.label }}</p>
            <p class="text-xs text-muted-foreground">{{ ev.timestamp_display }}<template v-if="ev.actor"> · {{ ev.actor }}</template><template v-if="ev.detail"> · {{ ev.detail }}</template></p>
          </div>
        </li>
      </ol>
      <p v-else class="text-sm text-muted-foreground" data-order-timeline-empty>Ainda não há nada no histórico deste pedido.</p>

      <!-- comentar: só quando o servidor oferece a ação neste contexto -->
      <div v-if="commentAllowed" class="flex items-start gap-2 border-t pt-3" data-order-comment>
        <textarea
          v-model="comment"
          rows="1"
          placeholder="Comentar no histórico…"
          class="min-h-control flex-1 resize-y rounded-md border bg-background p-2 text-sm outline-none focus:ring-1 focus:ring-ring"
          aria-label="Comentar no histórico"
          @keydown.enter.meta.prevent="submitComment"
        />
        <button
          type="button"
          :disabled="!comment.trim() || busy"
          class="inline-flex min-h-action shrink-0 items-center gap-1.5 rounded-md border border-transparent bg-primary px-3 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:opacity-50"
          data-order-comment-submit
          @click="submitComment"
        >
          <Icon name="lucide:message-square-plus" class="size-4" /> Comentar
        </button>
      </div>
    </section>
  </div>
</template>
