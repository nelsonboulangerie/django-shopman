<script setup lang="ts">
// Últimas vendas — a casa da DANFE depois que a tela da venda passou.
//
// A emissão fiscal é assíncrona: quando a nota autoriza, o operador já está na
// próxima venda. Esta lista responde "autorizou?" e dá os três verbos que o
// balcão precisa a qualquer hora: imprimir a DANFE na bobina (via agente do
// balcão), reenviar por e-mail (o Focus entrega) e reprocessar falha. As ações
// seguem o FATO (a nota existe), nunca o toggle que o operador marcou na venda.
import type { POSProjection } from "~/types/pos";
import { toast } from "vue-sonner";

interface RecentSale {
  order_ref: string;
  status: string;
  created_at_display: string;
  total_display: string;
  payment_label: string;
  customer_name: string;
  fiscal_status: string;
  fiscal_label: string;
  fiscal_links: Array<{ label: string; url: string }>;
  nfce_number: string;
  email_sent: boolean;
  receipt_email: string;
  can_print_danfe: boolean;
  can_resend_email: boolean;
  can_requeue_fiscal: boolean;
}

const props = defineProps<{
  open: boolean;
  pos: POSProjection | null;
}>();
const emit = defineEmits<{ "update:open": [boolean] }>();

const apiPath = usePosApiPath();
const agent = useCounterAgent(computed(() => props.pos));
// A bobina só existe onde existe agente; sem ele os botões de impressão
// esconderiam uma promessa que esta lista não tem como cumprir.
const canPrintOnAgent = computed(() => agent.canKick.value);
const djangoOrigin = computed(() => String(useRuntimeConfig().public.djangoPublicBaseUrl || ""));

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
    toast.error("Falha ao carregar as últimas vendas.");
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

// Falha nunca termina em "indisponível" seco: quem tem acesso ganha a prévia
// web como ação alternativa; quem não tem ganha o próximo passo.
function danfeFallbackToast(sale: RecentSale, reason: string) {
  if (props.pos?.danfe_preview_allowed && djangoOrigin.value) {
    toast.error(`A DANFE não saiu na bobina: ${reason}`, {
      action: {
        label: "Abrir prévia web",
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
    toast.error(messageOf(error));
  } finally {
    busyRef.value = "";
  }
}

function messageOf(error: unknown): string {
  const data = (error as { data?: { detail?: string } } | null)?.data;
  return data?.detail || (error instanceof Error ? error.message : "Falha na ação.");
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
        <UiButton type="button" variant="outline" size="sm" :disabled="loading" @click="load">
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
                :class="fiscalChipClass(sale.fiscal_status)"
              >
                {{ sale.fiscal_label }}
              </span>
            </div>

            <div v-if="canPrintOnAgent || sale.can_print_danfe || sale.can_requeue_fiscal" class="mt-2 flex flex-wrap items-center gap-2">
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
                v-if="sale.can_resend_email"
                type="button" variant="outline" size="xs" class="gap-1"
                :disabled="busyRef === sale.order_ref"
                @click="openEmailPrompt(sale)"
              >
                <Icon name="lucide:mail" class="size-3.5" />
                {{ sale.email_sent ? "Reenviar e-mail" : "Enviar e-mail" }}
              </UiButton>
              <UiButton
                v-if="sale.can_requeue_fiscal"
                type="button" variant="outline" size="xs"
                class="gap-1 border-destructive/40 text-destructive hover:bg-destructive/10"
                :disabled="busyRef === sale.order_ref"
                @click="requeueFiscal(sale)"
              >
                <Icon name="lucide:rotate-ccw" class="size-3.5" />
                Reprocessar nota
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
</template>
