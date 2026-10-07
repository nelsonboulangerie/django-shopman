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
  {
    busy: false,
    adminBaseUrl: "",
    showStatus: true,
    layout: "stack",
    decisionOnly: false,
  },
);

const emit = defineEmits<{ comment: [note: string] }>();
/** O rascunho do comentário mora na página: é ela que avisa texto não salvo. */
const comment = defineModel<string>("comment", { default: "" });

const adminUrl = computed(() =>
  adminUrlFor(props.adminBaseUrl, props.order.customer_ref),
);
const relayExpires = computed(() =>
  relayExpiresLabel(props.order.customer_relay_expires_at),
);
const showContact = computed(() =>
  hasCustomerContact(props.order, adminUrl.value),
);
const profile = computed(() => props.order.customer_profile);
const split = computed(() => props.layout === "split");
/** "Loja online · WEB-261004-V12 · aberto às 09:51 · Retirada": quem, de onde, quando. */
const metaLine = computed(() =>
  [
    props.order.channel_name || props.order.channel_ref,
    props.order.ref,
    props.order.opened_line,
    props.order.fulfillment_label,
  ].filter(Boolean),
);
const nuxtTone = (
  tone: string,
): "error" | "warning" | "success" | "info" | "neutral" =>
  tone === "danger"
    ? "error"
    : ["warning", "success", "info"].includes(tone)
      ? (tone as "warning" | "success" | "info")
      : "neutral";
const itemColumns = [
  { id: "qty", header: "Qtd." },
  { id: "item", header: "Item" },
  { id: "total", header: "Total" },
];
</script>

<template>
  <div
    :class="
      split
        ? 'flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(300px,380px)] lg:items-start lg:gap-4'
        : 'flex flex-col gap-4'
    "
    data-order-detail
    :data-order-context="order.context"
    :data-order-layout="layout"
  >
    <!-- ══ COLUNA ÚNICA (o PDV e o padrão) ═════════════════════════════════════ -->
    <template v-if="!split">
      <!-- Homologação do iFood contra o ambiente VIVO: o pedido de teste avança
           como qualquer outro, e o detalhe é onde o operador decide o que fazer
           com ele. O aviso abre a tela, acima do resumo. -->
      <NuxtAlert
        v-if="order.test_order_notice"
        color="warning"
        variant="subtle"
        icon="i-lucide-flask-conical"
        title="Pedido de teste"
        :description="order.test_order_notice"
        data-test-order-notice
      />

      <!-- resumo -->
      <NuxtCard data-order-summary>
        <div class="flex flex-col gap-3">
          <div class="flex flex-wrap items-center gap-2">
            <NuxtBadge
              v-if="showStatus"
              :color="nuxtTone(statusTone(order.status))"
              variant="subtle"
              :label="order.status_label"
              data-order-status
            />
            <span
              class="inline-flex items-center gap-1.5 text-sm text-muted-foreground"
            >
              <Icon
                :name="`lucide:${lucideIcon(order.channel_icon)}`"
                class="size-4"
              />
              {{ order.channel_name || order.channel_ref }}
            </span>
            <span
              class="ml-auto text-xl font-bold tabular-nums"
              data-order-total
              >{{ order.total_display }}</span
            >
          </div>
          <div class="grid gap-1 text-sm">
            <p class="flex items-center gap-2">
              <Icon name="lucide:user" class="size-4 text-muted-foreground" />
              {{ order.customer_name || "Sem cliente" }}
              <span
                v-if="
                  order.customer_phone &&
                  order.customer_phone !== order.customer_name
                "
                class="text-muted-foreground tabular-nums"
                data-customer-phone
              >
                · {{ order.customer_phone }}
              </span>
            </p>
            <p class="flex items-center gap-2 text-muted-foreground">
              <Icon name="lucide:package" class="size-4" />
              {{ order.fulfillment_label }}
            </p>
            <!-- Quando o combinado acontece (encomenda, ou retirada com janela). -->
            <p
              v-if="order.schedule_label"
              class="flex items-center gap-2"
              data-order-schedule
            >
              <Icon
                name="lucide:calendar-clock"
                class="size-4 text-muted-foreground"
              />
              {{ order.schedule_label }}
            </p>
            <!-- Para onde vai. Quem despacha não tinha o endereço em tela nenhuma
               do Gestor, embora o pedido sempre o carregasse. -->
            <p
              v-if="order.delivery_address"
              class="flex items-start gap-2"
              data-order-address
            >
              <Icon
                name="lucide:map-pin"
                class="mt-0.5 size-4 shrink-0 text-muted-foreground"
              />
              <span class="min-w-0">
                {{ order.delivery_address }}
                <span
                  v-if="order.delivery_instructions"
                  class="block text-muted-foreground"
                  >{{ order.delivery_instructions }}</span
                >
              </span>
            </p>
            <p class="flex items-center gap-2 text-muted-foreground">
              <Icon name="lucide:wallet" class="size-4" />
              {{ order.payment_method_label || "Pagamento não informado"
              }}<template v-if="order.payment_status_label">
                · {{ order.payment_status_label }}</template
              >
            </p>
            <slot name="summary" />
            <!-- Prova de envio do link de pagamento: "Enviando…", "Link enviado
               às 14h32" ou "falhou — reenvie". Lida da última Directive do
               aviso; sem aviso nenhum, a linha não existe. -->
            <p
              v-if="order.payment_link_notice"
              class="flex items-center gap-2 text-muted-foreground"
              data-payment-link-notice
            >
              <Icon name="lucide:send" class="size-4" />
              {{ order.payment_link_notice }}
            </p>
          </div>

          <!-- presente: destinatário é OPCIONAL na retirada (gift.py) — sem nome o
             pedido continua presente, e a instrução vira "embalar", não
             "entregar a alguém" com o nome pendurado no vazio. -->
          <NuxtAlert
            v-if="order.is_gift"
            color="info"
            variant="subtle"
            icon="i-lucide-gift"
            :title="
              order.gift_recipient_name
                ? `Presente para ${order.gift_recipient_name}`
                : 'Embalar para presente'
            "
            data-gift-block
          >
            <template #description>
              <span v-if="order.gift_recipient_phone" data-gift-phone>{{
                order.gift_recipient_phone
              }}</span>
              <template v-if="order.gift_message">
                · “{{ order.gift_message }}”</template
              >
              <NuxtBadge
                v-if="order.gift_hide_values"
                color="warning"
                variant="subtle"
                icon="i-lucide-eye-off"
                label="Não mostrar valores"
                data-gift-hide-values
              />
            </template>
          </NuxtAlert>
        </div>
        <template v-if="showContact" #footer>
          <div class="flex flex-wrap gap-2" data-customer-contact>
            <OperatorOrderContact
              :order="order"
              :admin-url="adminUrl"
              :relay-expires="relayExpires"
            />
          </div>
        </template>
      </NuxtCard>

      <!-- A barra de ações do contexto: a única parte que muda de uma tela para
           a outra. O servidor decide cada gesto; a página só liga os diálogos. -->
      <slot name="actions" />

      <!-- quem é este cliente (WP-360): só com cliente identificado. -->
      <NuxtCard v-if="profile" data-customer-profile>
        <template #header>
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="flex items-center gap-1.5 op-title">
              <Icon
                name="lucide:user-round"
                class="size-4 text-muted-foreground"
              />
              Cliente
            </h2>
            <!-- Selo só nos segmentos que mudam o atendimento. -->
            <NuxtBadge
              v-if="profile.segment_tone"
              :color="nuxtTone(profile.segment_tone)"
              variant="subtle"
              :label="profile.segment_label"
              data-customer-segment
            />
          </div>
        </template>
        <OperatorOrderProfileLines :profile="profile" />
      </NuxtCard>

      <slot name="after-profile" />

      <!-- nota fiscal -->
      <NuxtCard
        v-if="
          !decisionOnly &&
          (order.fiscal_status_label || order.fiscal_links.length)
        "
        data-order-fiscal
      >
        <div class="flex flex-wrap items-center gap-2">
          <Icon name="lucide:receipt" class="size-4 text-muted-foreground" />
          <span class="text-muted-foreground">{{
            order.fiscal_status_label || "Fiscal"
          }}</span>
          <NuxtButton
            v-for="(link, i) in order.fiscal_links"
            :key="i"
            :to="fiscalHref(link)"
            target="_blank"
            color="neutral"
            variant="link"
            icon="i-lucide-external-link"
            :label="link.label || 'Documento'"
          />
        </div>
      </NuxtCard>

      <!-- itens: os que VALEM agora, com os ajustes -->
      <NuxtCard data-order-items>
        <template #header><h2 class="op-title">Itens</h2></template>
        <NuxtTable
          :data="order.items"
          :columns="itemColumns"
          caption="Itens do pedido"
        >
          <template #qty-cell="{ row }">
            <span class="tabular-nums text-muted-foreground"
              >{{ row.original.qty }}×</span
            >
          </template>
          <template #item-cell="{ row }">{{ row.original.name }}</template>
          <template #total-cell="{ row }">
            <span class="tabular-nums">{{ row.original.total_display }}</span>
          </template>
        </NuxtTable>
      </NuxtCard>

      <!-- observação do CLIENTE (order_notes): somente leitura. -->
      <NuxtCard v-if="order.customer_note" data-customer-note>
        <template #header
          ><h2 class="op-title">Observação do cliente</h2></template
        >
        <p class="whitespace-pre-line text-sm">{{ order.customer_note }}</p>
      </NuxtCard>

      <!-- nota da cozinha: o editor entra pelo slot onde a tela a edita (Gestor);
           nas outras ela é leitura, e só existe quando há o que ler. -->
      <slot name="kitchen-note">
        <NuxtCard v-if="order.kitchen_note" data-kitchen-note>
          <template #header><h2 class="op-title">Nota da cozinha</h2></template>
          <p class="whitespace-pre-line text-sm">{{ order.kitchen_note }}</p>
          <p class="text-xs text-muted-foreground">
            Aparece no ticket da cozinha (KDS).
          </p>
        </NuxtCard>
      </slot>

      <OperatorOrderTimeline
        v-model:comment="comment"
        :order="order"
        :busy="busy"
        :read-only="decisionOnly"
        @comment="(note) => emit('comment', note)"
      />
    </template>

    <!-- ══ DUAS COLUNAS (o Gestor) ══════════════════════════════════════════════
         As colunas são `contents` abaixo de `lg`: as seções viram uma coluna só,
         ordenadas pelo `order-*` na sequência do celular. -->
    <template v-else>
      <div class="contents lg:flex lg:min-w-0 lg:flex-col lg:gap-4">
        <NuxtAlert
          v-if="order.test_order_notice"
          class="order-0 lg:order-none"
          color="warning"
          variant="subtle"
          icon="i-lucide-flask-conical"
          title="Pedido de teste"
          :description="order.test_order_notice"
          data-test-order-notice
        />

        <!-- o pedido: de onde e quando, os itens que valem e o total (v3) -->
        <NuxtCard class="order-3 lg:order-none" data-order-summary>
          <template #header>
            <p
              class="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 op-micro text-muted-foreground"
              data-order-meta
            >
              <Icon
                :name="`lucide:${lucideIcon(order.channel_icon)}`"
                class="size-4"
              />
              <template v-for="(part, i) in metaLine" :key="i"
                ><span v-if="i" aria-hidden="true">·</span
                ><span :class="part === order.ref ? 'tnum' : ''">{{
                  part
                }}</span></template
              >
            </p>
          </template>
          <NuxtTable
            :data="order.items"
            :columns="itemColumns"
            caption="Itens do pedido"
            data-order-items
          >
            <template #qty-cell="{ row }">
              <span class="font-semibold tabular-nums"
                >{{ row.original.qty }}×</span
              >
            </template>
            <template #item-cell="{ row }">
              <span class="op-body">{{ row.original.name }}</span>
            </template>
            <template #total-cell="{ row }">
              <span class="tabular-nums">{{ row.original.total_display }}</span>
            </template>
          </NuxtTable>
          <NuxtSeparator />
          <div class="flex items-baseline justify-between gap-3 py-3">
            <span class="op-label text-muted-foreground">Total</span>
            <span class="text-2xl font-bold tabular-nums" data-order-total>{{
              order.total_display
            }}</span>
          </div>
          <NuxtSeparator />
          <div class="grid gap-1 py-3 text-sm">
            <p
              v-if="order.schedule_label"
              class="flex items-center gap-2"
              data-order-schedule
            >
              <Icon
                name="lucide:calendar-clock"
                class="size-4 text-muted-foreground"
              />
              {{ order.schedule_label }}
            </p>
            <p
              v-if="order.delivery_address"
              class="flex items-start gap-2"
              data-order-address
            >
              <Icon
                name="lucide:map-pin"
                class="mt-0.5 size-4 shrink-0 text-muted-foreground"
              />
              <span class="min-w-0">
                {{ order.delivery_address }}
                <span
                  v-if="order.delivery_instructions"
                  class="block text-muted-foreground"
                  >{{ order.delivery_instructions }}</span
                >
              </span>
            </p>
            <p class="flex items-center gap-2 text-muted-foreground">
              <Icon name="lucide:wallet" class="size-4" />
              {{ order.payment_method_label || "Pagamento não informado"
              }}<template v-if="order.payment_status_label">
                · {{ order.payment_status_label }}</template
              >
            </p>
            <slot name="summary" />
            <p
              v-if="order.payment_link_notice"
              class="flex items-center gap-2 text-muted-foreground"
              data-payment-link-notice
            >
              <Icon name="lucide:send" class="size-4" />
              {{ order.payment_link_notice }}
            </p>
          </div>
          <NuxtAlert
            v-if="order.is_gift"
            color="info"
            variant="subtle"
            icon="i-lucide-gift"
            :title="
              order.gift_recipient_name
                ? `Presente para ${order.gift_recipient_name}`
                : 'Embalar para presente'
            "
            data-gift-block
          >
            <template #description>
              <span v-if="order.gift_recipient_phone" data-gift-phone>{{
                order.gift_recipient_phone
              }}</span>
              <template v-if="order.gift_message">
                · “{{ order.gift_message }}”</template
              >
              <NuxtBadge
                v-if="order.gift_hide_values"
                color="warning"
                variant="subtle"
                icon="i-lucide-eye-off"
                label="Não mostrar valores"
                data-gift-hide-values
              />
            </template>
          </NuxtAlert>
        </NuxtCard>

        <div
          v-if="$slots.actions"
          class="order-1 min-w-0 empty:hidden lg:order-none"
        >
          <slot name="actions" />
        </div>

        <NuxtCard
          v-if="order.customer_note"
          class="order-4 lg:order-none"
          data-customer-note
        >
          <template #header
            ><h2 class="op-title">Observação do cliente</h2></template
          >
          <p class="whitespace-pre-line text-sm">{{ order.customer_note }}</p>
        </NuxtCard>

        <div class="order-5 min-w-0 empty:hidden lg:order-none">
          <slot name="kitchen-note">
            <NuxtCard v-if="order.kitchen_note" data-kitchen-note>
              <template #header
                ><h2 class="op-title">Nota da cozinha</h2></template
              >
              <p class="whitespace-pre-line text-sm">
                {{ order.kitchen_note }}
              </p>
              <p class="text-xs text-muted-foreground">
                Aparece no ticket da cozinha (KDS).
              </p>
            </NuxtCard>
          </slot>
        </div>

        <div
          v-if="$slots['after-profile']"
          class="order-7 flex min-w-0 flex-col gap-4 empty:hidden lg:order-none"
        >
          <slot name="after-profile" />
        </div>

        <NuxtCard
          v-if="
            !decisionOnly &&
            (order.fiscal_status_label || order.fiscal_links.length)
          "
          class="order-8 lg:order-none"
          data-order-fiscal
        >
          <div class="flex flex-wrap items-center gap-2">
            <Icon name="lucide:receipt" class="size-4 text-muted-foreground" />
            <span class="text-muted-foreground">{{
              order.fiscal_status_label || "Fiscal"
            }}</span>
            <NuxtButton
              v-for="(link, i) in order.fiscal_links"
              :key="i"
              :to="fiscalHref(link)"
              target="_blank"
              color="neutral"
              variant="link"
              icon="i-lucide-external-link"
              :label="link.label || 'Documento'"
            />
          </div>
        </NuxtCard>
      </div>

      <div class="contents lg:flex lg:min-w-0 lg:flex-col lg:gap-4">
        <!-- Cliente: quem é, como falar e o que a casa sabe dela -->
        <NuxtCard class="order-2 lg:order-none" data-customer-card>
          <template #header>
            <div class="flex flex-wrap items-center gap-2">
              <h2 class="op-title">Cliente</h2>
              <NuxtBadge
                v-if="profile?.segment_tone"
                :color="nuxtTone(profile.segment_tone)"
                variant="subtle"
                :label="profile.segment_label"
                data-customer-segment
              />
            </div>
          </template>
          <div class="flex flex-col gap-3">
            <div class="flex items-center gap-3">
              <div class="min-w-0 flex-1">
                <p class="op-title break-words">
                  {{ order.customer_name || "Sem cliente" }}
                </p>
                <p
                  v-if="
                    order.customer_phone &&
                    order.customer_phone !== order.customer_name
                  "
                  class="tabular-nums text-muted-foreground"
                  data-customer-phone
                >
                  {{ order.customer_phone }}
                </p>
              </div>
              <div
                v-if="
                  order.customer_whatsapp_url ||
                  (order.customer_phone_uri && !order.customer_relay_phone)
                "
                class="flex shrink-0 gap-2"
                data-customer-contact
              >
                <OperatorOrderContact
                  :order="{
                    ...order,
                    customer_relay_phone: '',
                    customer_email: '',
                  }"
                  admin-url=""
                  relay-expires=""
                  compact
                />
              </div>
            </div>
            <div
              v-if="
                order.customer_relay_phone || order.customer_email || adminUrl
              "
              class="flex flex-wrap gap-2"
              data-customer-contact-more
            >
              <OperatorOrderContact
                :order="{
                  ...order,
                  customer_whatsapp_url: '',
                  customer_phone_uri: order.customer_relay_phone
                    ? order.customer_phone_uri
                    : '',
                }"
                :admin-url="adminUrl"
                :relay-expires="relayExpires"
              />
            </div>
            <div
              v-if="profile"
              class="flex flex-col gap-1"
              data-customer-profile
            >
              <OperatorOrderProfileLines :profile="profile" />
            </div>
          </div>
        </NuxtCard>

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
