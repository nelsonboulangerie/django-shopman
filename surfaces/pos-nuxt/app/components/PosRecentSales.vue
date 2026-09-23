<script setup lang="ts">
// Últimas vendas — a casa da DANFE depois que a tela da venda passou.
//
// A emissão fiscal é assíncrona: quando a nota autoriza, o operador já está na
// próxima venda. Esta lista responde "autorizou?" e dá os três verbos que o
// balcão precisa a qualquer hora: imprimir a DANFE na bobina (via agente do
// balcão), reenviar por e-mail (o Focus entrega) e reprocessar falha. As ações
// seguem o FATO (a nota existe), nunca o toggle que o operador marcou na venda.
// E um quarto, de exceção: emitir a nota que a regra da casa não emitiu (o
// cliente voltou pedindo), sempre com a autorização de um gerente.
import type { PosFiscalState, POSPaymentDeliveryProjection, POSProjection } from "~/types/pos";
import { toast } from "vue-sonner";

import { fiscalStateLabel } from "~/presentation/saleResult";

interface RecentSale {
  order_ref: string;
  status: string;
  created_at_display: string;
  total_display: string;
  payment_label: string;
  customer_name: string;
  fiscal_status: string;
  fiscal_label: string;
  /** O estado canônico da nota (o mesmo da tela de resultado). Opcional: o
   *  backend pode chegar depois; sem ele valem `fiscal_status`/`fiscal_label`. */
  fiscal_state?: PosFiscalState;
  fiscal_links: Array<{ label: string; url: string }>;
  nfce_number: string;
  email_sent: boolean;
  receipt_email: string;
  can_print_danfe: boolean;
  can_resend_email: boolean;
  can_requeue_fiscal: boolean;
  /** A regra da casa não emitiu e a emissão avulsa pode sair (o servidor decide
   *  e impõe de novo). Opcional: backend anterior não manda. */
  can_emit_fiscal?: boolean;
  /** Ainda dentro da janela do desfazer (o servidor decide e impõe). */
  can_cancel: boolean;
  payment_delivery?: POSPaymentDeliveryProjection;
}

const props = defineProps<{
  open: boolean;
  pos: POSProjection | null;
}>();
// `cancelled` sobe para a tela de venda limpar o vestígio da mesma venda
// (tela de resultado, chip de PIX pendente) e recarregar a Projection.
const emit = defineEmits<{ "update:open": [boolean]; cancelled: [string] }>();

const apiPath = useApiPath();
const agent = useCounterAgent(computed(() => props.pos));
// A bobina só existe onde existe agente; sem ele os botões de impressão
// esconderiam uma promessa que esta lista não tem como cumprir.
const canPrintOnAgent = computed(() => agent.canPrint.value);
const djangoOrigin = computed(() => String(useRuntimeConfig().public.djangoBaseUrl || ""));

const sales = ref<RecentSale[]>([]);
const loading = ref(false);
const busyRef = ref("");
const emailPromptRef = ref("");
const emailDraft = ref("");

async function load() {
  loading.value = true;
  try {
    const response = await $fetch<{ sales: RecentSale[] }>(
      apiPath("/api/v1/backstage/pos/recent-sales/"),
      { credentials: "include" },
    );
    sales.value = response.sales || [];
  } catch {
    // A lista se repõe sozinha: enquanto o painel está aberto, um poll de 5s
    // refaz esta chamada. A saída diz isso em vez de pedir um gesto que o
    // operador não precisa dar.
    toast.error("A lista das últimas vendas não carregou. Ela tenta sozinha a cada poucos segundos; feche e reabra o painel para forçar.");
  } finally {
    loading.value = false;
  }
}

watch(() => props.open, (open) => {
  if (open) void load();
});

// A nota "pendente" vira "autorizada" segundos depois da venda; enquanto o
// painel está aberto, um poll calmo mantém a lista honesta sem F5.
let pollTimer: ReturnType<typeof setInterval> | null = null;
watch(() => props.open, (open) => {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  if (open) pollTimer = setInterval(() => void load(), 5000);
});
onBeforeUnmount(() => { if (pollTimer) clearInterval(pollTimer); });

// O carimbo "2ª via" é do servidor (`danfe_printed_at` em Order.data): esta
// tela não chuta mais por heurística de venda completa + e-mail enviado.
async function printDanfe(sale: RecentSale) {
  busyRef.value = sale.order_ref;
  try {
    const response = await $fetch<{ payload_b64: string; title: string }>(
      apiPath(`/api/v1/backstage/pos/orders/${encodeURIComponent(sale.order_ref)}/danfe-escpos/`),
      { credentials: "include" },
    );
    const outcome = await agent.print(response.payload_b64, response.title);
    if (outcome.status === "printed") toast.success(`DANFE de ${sale.order_ref} na impressora.`);
    else danfeFallbackToast(sale, outcome.detail || "impressão indisponível nesta estação");
  } catch (error) {
    danfeFallbackToast(sale, messageOf(error));
  } finally {
    busyRef.value = "";
  }
}

// Falha nunca termina em "indisponível" seco: quem tem acesso ganha a nota na
// tela como ação alternativa; quem não tem ganha o próximo passo.
function danfeFallbackToast(sale: RecentSale, reason: string) {
  if (props.pos?.danfe_screen_allowed && djangoOrigin.value) {
    toast.error(`A DANFE não saiu na bobina: ${reason}`, {
      action: {
        label: "Ver a nota na tela",
        onClick: () => window.open(
          `${djangoOrigin.value}/fiscal/danfe/${encodeURIComponent(sale.order_ref)}/`,
          "_blank",
          "noopener",
        ),
      },
    });
  } else {
    toast.error(`A DANFE não saiu na bobina: ${reason}. Confira o agente do balcão na saúde do terminal e tente de novo.`);
  }
}

// Recibo não fiscal reimpresso da bobina — o servidor compõe do que a venda
// gravou e decide sozinho o carimbo de 2ª via (`receipt_printed_at`).
async function printReceipt(sale: RecentSale) {
  busyRef.value = sale.order_ref;
  try {
    const response = await $fetch<{ payload_b64: string; title: string }>(
      apiPath(`/api/v1/backstage/pos/orders/${encodeURIComponent(sale.order_ref)}/receipt-escpos/`),
      { credentials: "include" },
    );
    const outcome = await agent.print(response.payload_b64, response.title);
    if (outcome.status === "printed") {
      toast.success(`Recibo de ${sale.order_ref} na impressora.`);
    } else {
      toast.error(`O recibo não saiu: ${outcome.detail || "impressão indisponível nesta estação"}.`, {
        action: { label: "Tentar de novo", onClick: () => void printReceipt(sale) },
      });
    }
  } catch (error) {
    toast.error(`O recibo não saiu: ${messageOf(error)}`, {
      action: { label: "Tentar de novo", onClick: () => void printReceipt(sale) },
    });
  } finally {
    busyRef.value = "";
  }
}

function openEmailPrompt(sale: RecentSale) {
  emailPromptRef.value = sale.order_ref;
  emailDraft.value = sale.receipt_email;
}

async function resendEmail(sale: RecentSale) {
  busyRef.value = sale.order_ref;
  try {
    const response = await $fetch<{ detail: string }>(
      apiPath(`/api/v1/backstage/pos/orders/${encodeURIComponent(sale.order_ref)}/resend-fiscal-email/`),
      { method: "POST", credentials: "include", body: { email: emailDraft.value.trim() } },
    );
    toast.success(response.detail || "E-mail a caminho.");
    emailPromptRef.value = "";
  } catch (error) {
    toast.error(messageOf(error));
  } finally {
    busyRef.value = "";
  }
}

async function sendPaymentNotice(sale: RecentSale) {
  const requested = sale.payment_delivery?.action;
  if (!requested) return;
  busyRef.value = sale.order_ref;
  try {
    const response = await $fetch<{ payment_delivery?: POSPaymentDeliveryProjection }>(
      apiPath(`/api/v1/backstage/pos/orders/${encodeURIComponent(sale.order_ref)}/send-payment-notice/`),
      { method: "POST", credentials: "include", body: { action: requested } },
    );
    if (response.payment_delivery) sale.payment_delivery = response.payment_delivery;
    toast.success(response.payment_delivery?.notice || "Cobrança colocada na fila de envio.");
  } catch (error) {
    const delivery = (error as { data?: { payment_delivery?: POSPaymentDeliveryProjection } } | null)?.data?.payment_delivery;
    if (delivery) sale.payment_delivery = delivery;
    toast.error(messageOf(error));
  } finally {
    busyRef.value = "";
  }
}

async function requeueFiscal(sale: RecentSale) {
  busyRef.value = sale.order_ref;
  try {
    await $fetch(
      apiPath(`/api/v1/backstage/orders/${encodeURIComponent(sale.order_ref)}/requeue-fiscal/`),
      { method: "POST", credentials: "include" },
    );
    toast.success(`Emissão de ${sale.order_ref} reenfileirada.`);
    await load();
  } catch (error) {
    toast.error(`${messageOf(error)} A emissão não foi reenfileirada. Atualize a lista e confira a situação da nota antes de repetir.`);
  } finally {
    busyRef.value = "";
  }
}

// Emissão avulsa: a venda não pediu nota, o cliente voltou pedindo. Exceção
// auditada — o MESMO diálogo de gerente das outras exceções do PDV
// (`OperatorManagerAuth`, crachá ou PIN), e quem assina fica gravado no pedido.
// O erro fica INLINE no diálogo (PIN errado se corrige ali); recusa de negócio
// (venda antiga, nota já em andamento) fecha o diálogo e vira toast.
const emitTargetRef = ref("");
const emitDialogOpen = ref(false);
const emitBusy = ref(false);
const emitError = ref("");

function openEmitFiscal(sale: RecentSale) {
  emitTargetRef.value = sale.order_ref;
  emitError.value = "";
  emitDialogOpen.value = true;
}

async function submitEmitFiscal(aprovacao: Record<string, string>) {
  const orderRef = emitTargetRef.value;
  if (!orderRef || emitBusy.value) return;
  emitBusy.value = true;
  emitError.value = "";
  try {
    const response = await $fetch<{ detail?: string }>(
      apiPath(`/api/v1/backstage/pos/orders/${encodeURIComponent(orderRef)}/emit-fiscal/`),
      { method: "POST", credentials: "include", body: { manager_approval: aprovacao } },
    );
    emitDialogOpen.value = false;
    emitTargetRef.value = "";
    toast.success(response?.detail || `NFC-e de ${orderRef} na fila.`);
    await load();
  } catch (error) {
    const failure = httpError(error);
    const data = failure.data as { detail?: string; error?: { field?: string; message?: string; recovery?: string } } | null;
    if (data?.error?.field === "manager_approval") {
      emitError.value = data.error.recovery || data.error.message || messageOf(error);
    } else {
      emitDialogOpen.value = false;
      // Nota fiscal não ganha "tente de novo": a emissão é assíncrona e a lista é
      // quem diz se ela saiu. Conferir primeiro é o gesto certo aqui.
      toast.error(`${data?.detail || messageOf(error)} A nota não foi emitida. Confira a venda na lista antes de pedir de novo.`);
    }
  } finally {
    emitBusy.value = false;
  }
}

function messageOf(error: unknown): string {
  const data = (error as { data?: { detail?: string } } | null)?.data;
  // Último recurso de CAUSA, quando o servidor não mandou `detail` e o erro não
  // é um `Error`: aqui realmente não se sabe o que houve, e inventar um motivo
  // seria pior. A saída é de quem chama — as três chamadas abaixo a trazem.
  return data?.detail || (error instanceof Error ? error.message : "Não deu para concluir a ação.");
}

// Cancelar venda DESTA lista: a correção sobrevive à saída da tela de
// resultado. O mesmo diálogo (PIN/crachá de gerente) e a mesma janela da tela
// de venda — o servidor valida a janela de novo, sempre.
const saleCorrection = computed(() => props.pos?.checkout?.capabilities?.sale_correction ?? null);
const cancelDialogOpen = ref(false);
const cancelTargetRef = ref("");
const cancelReason = ref("");
const cancelBusy = ref(false);
const cancelError = ref("");

function openCancel(sale: RecentSale) {
  cancelTargetRef.value = sale.order_ref;
  cancelReason.value = "";
  cancelError.value = "";
  cancelDialogOpen.value = true;
}

async function submitCancel(aprovacao: Record<string, string>) {
  const orderRef = cancelTargetRef.value;
  if (!orderRef || cancelBusy.value) return;
  cancelBusy.value = true;
  cancelError.value = "";
  try {
    const reason = cancelReason.value.trim();
    await $fetch(apiPath("/api/v1/backstage/pos/sale/recent/cancel/"), {
      method: "POST",
      credentials: "include",
      body: {
        order_ref: orderRef,
        manager_approval: aprovacao,
        ...(reason ? { reason } : {}),
      },
    });
    cancelDialogOpen.value = false;
    cancelTargetRef.value = "";
    cancelReason.value = "";
    toast.success("Venda cancelada", {
      description: `O pedido ${orderRef} foi cancelado dentro da janela do operador.`,
    });
    emit("cancelled", orderRef);
    await load();
  } catch (error) {
    // O erro fica INLINE no diálogo aberto: toast com o diálogo fechando leria
    // como sucesso — mesma lição do cancelamento na tela de venda.
    const failure = (httpError(error).data as { error?: { message?: string; recovery?: string } } | null)?.error;
    cancelError.value = failure?.recovery || failure?.message || messageOf(error);
  } finally {
    cancelBusy.value = false;
  }
}

// O chip fala o MESMO rótulo da tela de resultado quando o servidor manda o
// estado canônico; sem ele, o rótulo pronto do servidor.
function fiscalChipLabel(sale: RecentSale): string {
  return sale.fiscal_state ? fiscalStateLabel(sale.fiscal_state) : sale.fiscal_label;
}
function fiscalChipStatus(sale: RecentSale): string {
  if (!sale.fiscal_state) return sale.fiscal_status;
  return sale.fiscal_state === "not_expected" ? "not_requested" : sale.fiscal_state;
}
// Cor só funcional (design neutro de operador): o chip fiscal informa estado.
function fiscalChipClass(status: string): string {
  if (status === "authorized") return "bg-success/10 text-success border-success/30";
  if (status === "failed") return "bg-destructive/10 text-destructive border-destructive/30";
  if (status === "cancelled") return "bg-muted text-muted-foreground border-border";
  if (status === "not_requested") return "bg-muted text-muted-foreground border-border";
  return "bg-warning/10 text-warning-foreground border-warning/30";
}
</script>

<template>
  <UiSheet :open="open" @update:open="(v) => emit('update:open', v)">
    <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-lg" :title="undefined">
      <div class="flex items-center justify-between border-b border-border px-5 py-4">
        <div>
          <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Balcão</p>
          <h2 class="text-lg font-semibold text-foreground">Últimas vendas</h2>
        </div>
        <UiButton type="button" variant="outline" size="sm" aria-label="Atualizar as últimas vendas" :disabled="loading" @click="load">
          <Icon name="lucide:refresh-cw" class="size-4" :class="loading ? 'animate-spin' : ''" />
        </UiButton>
      </div>

      <div class="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <p v-if="!loading && !sales.length" class="py-8 text-center text-sm text-muted-foreground">
          Nenhuma venda nas últimas 24 horas.
        </p>
        <ul class="grid gap-3">
          <li v-for="sale in sales" :key="sale.order_ref" class="rounded-md border border-border p-3">
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <p class="flex items-center gap-2 text-sm font-medium text-foreground">
                  <span class="tabular-nums text-muted-foreground">{{ sale.created_at_display }}</span>
                  <span class="truncate font-mono text-xs">{{ sale.order_ref }}</span>
                </p>
                <p class="mt-0.5 text-xs text-muted-foreground">
                  R$ {{ sale.total_display }} · {{ sale.payment_label }}
                  <template v-if="sale.customer_name"> · {{ sale.customer_name }}</template>
                </p>
              </div>
              <span
                class="shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium"
                :class="fiscalChipClass(fiscalChipStatus(sale))"
                data-fiscal-chip
              >
                {{ fiscalChipLabel(sale) }}
              </span>
            </div>

            <p
              v-if="sale.payment_delivery?.notice"
              class="mt-2 flex items-start gap-1 text-xs text-muted-foreground"
              data-payment-delivery
            >
              <Icon name="lucide:message-circle-more" class="mt-0.5 size-3.5 shrink-0" />
              {{ sale.payment_delivery.notice }}
            </p>

            <div v-if="canPrintOnAgent || sale.can_print_danfe || sale.can_requeue_fiscal || sale.can_emit_fiscal || sale.can_cancel || sale.payment_delivery?.action" class="mt-2 flex flex-wrap items-center gap-2">
              <!-- Recibo não fiscal: qualquer venda reimprime, a qualquer hora.
                   Só aparece onde há agente; a bobina é o único transporte da
                   reimpressão (o diálogo do navegador só existe na venda viva). -->
              <UiButton
                v-if="canPrintOnAgent"
                type="button" variant="outline" size="xs" class="gap-1"
                :disabled="busyRef === sale.order_ref"
                @click="printReceipt(sale)"
              >
                <Icon name="lucide:printer" class="size-3.5" />
                Recibo
              </UiButton>
              <UiButton
                v-if="sale.can_print_danfe"
                type="button" variant="outline" size="xs" class="gap-1"
                :disabled="busyRef === sale.order_ref"
                @click="printDanfe(sale)"
              >
                <Icon name="lucide:receipt-text" class="size-3.5" />
                DANFE
              </UiButton>
              <UiButton
                v-if="sale.payment_delivery?.action"
                type="button" variant="outline" size="xs" class="gap-1"
                :disabled="busyRef === sale.order_ref"
                data-action="send-payment-notice"
                @click="sendPaymentNotice(sale)"
              >
                <Icon name="lucide:send" class="size-3.5" />
                {{ sale.payment_delivery.action_label }}
              </UiButton>
              <UiButton
                v-if="sale.can_resend_email"
                type="button" variant="outline" size="xs" class="gap-1"
                :disabled="busyRef === sale.order_ref"
                @click="openEmailPrompt(sale)"
              >
                <Icon name="lucide:mail" class="size-3.5" />
                <!-- ⚠️ Este botão só ABRE o campo de e-mail. Quem envia é o
                     "Enviar" que aparece ali dentro — dizia "Enviar e-mail" e
                     não enviava nada. -->
                {{ sale.email_sent ? "E-mail da nota (já enviada)" : "E-mail da nota" }}
              </UiButton>
              <UiButton
                v-if="sale.can_requeue_fiscal"
                type="button" variant="outline" size="xs"
                class="gap-1 border-destructive/40 text-destructive hover:bg-destructive/10"
                :disabled="busyRef === sale.order_ref"
                @click="requeueFiscal(sale)"
              >
                <Icon name="lucide:rotate-ccw" class="size-3.5" />
                <!-- Sem reticências: o toque reenfileira na hora, não abre nada.
                     A emissão FOI tentada e falhou (`can_requeue_fiscal` é
                     `fiscal_status == "failed"`), então "de novo" é verdade — e o
                     objeto vai no rótulo porque ao lado há outras três ações. -->
                Tentar a emissão de novo
              </UiButton>
              <!-- Emissão avulsa: a regra da casa não emitiu. Botão NEUTRO — não
                   há nada errado com a venda; o gerente é pedido no toque. -->
              <UiButton
                v-if="sale.can_emit_fiscal"
                type="button" variant="outline" size="xs" class="gap-1"
                :disabled="busyRef === sale.order_ref || emitBusy"
                data-action="emit-fiscal"
                @click="openEmitFiscal(sale)"
              >
                <Icon name="lucide:file-plus" class="size-3.5" />
                <!-- Par do chip "Emissão não estabelecida" (escolha do Pablo).
                     Reticências: o toque abre a autorização do gerente. Não é
                     "Tentar novamente" (nunca houve tentativa) nem "Solicitar
                     autorização" (a mesma tela já pede a autorização do
                     GERENTE: a palavra teria dois sentidos no mesmo toque). -->
                Estabelecer emissão…
              </UiButton>
              <!-- Desfazer dentro da janela: exceção auditada, sempre com o
                   desafio gerencial do mesmo diálogo da tela de venda. -->
              <UiButton
                v-if="sale.can_cancel"
                type="button" variant="outline" size="xs"
                class="gap-1 border-destructive/40 text-destructive hover:bg-destructive/10"
                :disabled="busyRef === sale.order_ref || cancelBusy"
                @click="openCancel(sale)"
              >
                <Icon name="lucide:undo-2" class="size-3.5" />
                Cancelar venda
              </UiButton>
            </div>

            <!-- Consulta pública da nota (Focus/SEFAZ): os links já viajavam na
                 projection; agora a tela os entrega em vez de engoli-los. -->
            <p v-if="sale.fiscal_links.length" class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span>Consulta da nota:</span>
              <a
                v-for="link in sale.fiscal_links"
                :key="link.url"
                :href="link.url"
                target="_blank" rel="noopener"
                class="underline underline-offset-2 hover:text-foreground"
              >
                {{ link.label }}
              </a>
            </p>

            <div v-if="emailPromptRef === sale.order_ref" class="mt-2 flex items-center gap-2">
              <UiInput
                v-model="emailDraft"
                type="email"
                placeholder="cliente@email.com"
                class="h-8 text-sm"
                @keydown.enter.prevent="resendEmail(sale)"
              />
              <UiButton
                type="button" size="sm"
                :disabled="!emailDraft.trim() || busyRef === sale.order_ref"
                @click="resendEmail(sale)"
              >
                Enviar
              </UiButton>
            </div>
          </li>
        </ul>
      </div>
    </UiSheetContent>
  </UiSheet>

  <!-- Confirmação destrutiva + desafio gerencial — o MESMO diálogo da tela de
       venda; a janela anunciada é a do contrato e o servidor a valida de novo. -->
  <PosCancelSaleDialog
    v-model:open="cancelDialogOpen"
    v-model:reason="cancelReason"
    :order-ref="cancelTargetRef"
    :max-age-minutes="saleCorrection?.max_age_minutes || 0"
    :busy="cancelBusy"
    :error="cancelError"
    :managers="pos?.managers"
    @confirm="(username, pin) => submitCancel({ username, pin })"
    @confirm-badge="(badge) => submitCancel({ badge })"
  />

  <!-- Emissão avulsa da NFC-e: o mesmo diálogo de gerente das outras exceções. -->
  <OperatorManagerAuth
    v-model:open="emitDialogOpen"
    action="emit_fiscal"
    :managers="pos?.managers || []"
    :busy="emitBusy"
    :error="emitError"
    @authorize="(username, pin) => submitEmitFiscal({ username, pin })"
    @authorize-badge="(badge) => submitEmitFiscal({ badge })"
  />
</template>
