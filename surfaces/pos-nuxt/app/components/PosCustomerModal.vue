<script setup lang="ts">
import { toast } from "vue-sonner";
// Customer picker (spec — Odoo "Choose Customer" clone, redesign 2026-06-10).
// One SHARED modal for both the comanda header and the payment screen, replacing
// the two divergent inline dialogs. Picker-first (not form-first), full-screen
// overlay like Odoo:
//   1. associated customer (if any) pinned at top, highlighted, with "Remover
//      cliente" (= Odoo's UNSELECT — the disassociate affordance we were missing);
//   2. a prominent search → rich results list (shared PosCustomerSearch);
//   3. a create/edit form below.
// The payment context also passes showFiscal to surface the fiscal/comprovante
// block (it rides with the customer because the receipt needs the e-mail).
// Renders intent; the shell owns clearCustomer / resolveCustomer / search.
import type {
  POSCheckoutOptionProjection,
  POSCustomerLookupProjection,
  POSCustomerSearchResult,
} from "~/types/pos";
import { cpfTail } from "~/presentation/customerSearch";
import type { CustomerDecision } from "~/presentation/customerDecision";
import { customerDecisionCopy } from "~/presentation/customerDecision";

const props = withDefaults(defineProps<{
  open: boolean;
  customerName: string;
  customerPhone: string;
  customerTaxId: string;
  customerEmail: string;
  customerLookup: POSCustomerLookupProjection | null;
  searchResults: POSCustomerSearchResult[];
  searchBusy: boolean;
  lookupBusy: boolean;
  /** O cliente associado foi CRIADO AGORA (resolve just-in-time): a confirmação
   *  visual distingue "cadastro novo" de "cadastro encontrado". */
  resolvedNew?: boolean;
  /** A ESCOLHA QUE É DO OPERADOR, não do sistema: o WhatsApp digitado já é de
   *  outro cadastro, ou o contato do cliente associado vai mudar. Enquanto ela
   *  existe, o modal fica aberto e "Concluir" espera a resposta. */
  customerDecision?: CustomerDecision | null;
  /** Payment context: also show the fiscal/comprovante block. */
  showFiscal?: boolean;
  receiptChannels?: string[];
  receiptChannelOptions?: POSCheckoutOptionProjection[];
  receiptEmail?: string;
}>(), {
  customerDecision: null,
  resolvedNew: false,
  showFiscal: false,
  receiptChannels: () => [],
  receiptChannelOptions: () => [],
  receiptEmail: "",
});

const emit = defineEmits<{
  "update:open": [boolean];
  "update:customerName": [string];
  "update:customerPhone": [string];
  "update:customerTaxId": [string];
  "update:customerEmail": [string];
  "update:receiptChannels": [string[]];
  "update:receiptEmail": [string];
  search: [string];
  selectResult: [POSCustomerSearchResult];
  clear: [];
  resolveCustomer: [];
  /** O operador assumiu a mudança (trocar de cliente / trocar o contato). */
  decisionConfirm: [];
  /** O operador ficou com o que estava — o valor digitado é descartado. */
  decisionCancel: [];
  applyCustomerFavorite: [];
  repeatCustomerLastOrder: [];
}>();

// ── Preferências persistentes do cliente (painel do balcão) ──────────────────
// Draft local sincronizado do lookup; salvar é POST parcial no perfil. Os
// toggles salvam no clique; textos salvam no blur (menos requests, zero botão).
const apiPathProfile = usePosApiPath();
const profileSaving = ref(false);
const profileDraft = reactive({
  cpf_na_nota: false,
  email_receipt: false,
  dietary_restrictions: "",
  notes: "",
});
watch(() => props.customerLookup, (lookup) => {
  profileDraft.cpf_na_nota = !!lookup?.fiscal_prefs?.cpf_na_nota;
  profileDraft.email_receipt = !!lookup?.fiscal_prefs?.email_receipt;
  profileDraft.dietary_restrictions = lookup?.dietary_restrictions || "";
  profileDraft.notes = lookup?.notes || "";
}, { immediate: true });

async function saveProfile(body: Record<string, unknown>) {
  const customerRef = props.customerLookup?.ref;
  if (!customerRef) return;
  profileSaving.value = true;
  try {
    await $fetch(apiPathProfile(`/api/v1/backstage/pos/customer/${encodeURIComponent(customerRef)}/profile/`), {
      method: "POST", credentials: "include", body,
    });
  } catch {
    toast.error("Falha ao salvar a preferência do cliente.");
  } finally {
    profileSaving.value = false;
  }
}

function toggleProfilePref(key: "cpf_na_nota" | "email_receipt") {
  profileDraft[key] = !profileDraft[key];
  void saveProfile({ fiscal_prefs: { [key]: profileDraft[key] } });
}

function saveProfileText() {
  void saveProfile({
    dietary_restrictions: profileDraft.dietary_restrictions,
    notes: profileDraft.notes,
  });
}

function toggleReceiptChannel(ref: string) {
  const next = props.receiptChannels.includes(ref)
    ? props.receiptChannels.filter((c) => c !== ref)
    : [...props.receiptChannels, ref];
  emit("update:receiptChannels", next);
}

// A customer is associated when there's a loaded lookup or a name in context.
const hasCustomer = computed(() => Boolean(props.customerName.trim() || props.customerLookup));
const memory = computed(() => props.customerLookup?.memory || null);
const identityChips = computed(() =>
  [props.customerPhone, props.customerTaxId, props.customerEmail].map((v) => v.trim()).filter(Boolean),
);

// Reset the shared search field whenever the modal reopens fresh.
watch(() => props.open, (open) => { if (!open) emit("search", ""); });

// A RECUSA TRAZ A TELA DE VOLTA. O "Concluir" fecha o modal e só depois a
// resposta do servidor chega: sem isto, a recusa nasceria atrás de uma tela
// fechada e o operador veria a venda seguir com o cliente errado.
const decisionCopy = computed(() =>
  props.customerDecision ? customerDecisionCopy(props.customerDecision) : null,
);
watch(() => props.customerDecision, (decision) => {
  if (decision && !props.open) emit("update:open", true);
});

function onSelect(result: POSCustomerSearchResult) {
  emit("selectResult", result);
}
function onConclude() {
  // Uma pergunta aberta na tela não se responde fechando a tela.
  if (props.customerDecision) return;
  emit("resolveCustomer");
  emit("update:open", false);
}

// ── Atos NOMEADOS vindos do PosCustomerSearch ───────────────────────────────
// CPF válido sem resultado: o documento entra no campo fiscal e o resolve roda
// JÁ (get-or-create idempotente) — o cliente novo aparece fixado no topo.
async function onResolveCpf(cpf: string) {
  emit("update:customerTaxId", cpf);
  await nextTick(); // o v-model sobe dois níveis; o resolve lê o cart já atualizado
  emit("resolveCustomer");
}
// Telefone sem resultado: transfere para o campo do cadastro novo.
function onTransfer(payload: { field: "phone"; value: string }) {
  emit("update:customerPhone", payload.value);
}
// CADASTRAR SÓ COM O NOME — o ato que antes acontecia por inércia de dois
// Enters e agora tem botão, rótulo e ressalva. Um toque, como era; a diferença
// é que o operador leu o que ia acontecer.
async function onCreateNameOnly(name: string) {
  emit("update:customerName", name);
  await nextTick(); // o v-model sobe dois níveis; o resolve lê o cart atualizado
  emit("resolveCustomer");
}

// Foco garantido na BUSCA ao abrir: sem isto o foco inicial do diálogo caía no
// primeiro focável — "Remover cliente", o pior lugar para um Enter distraído.
const searchRef = ref<{ focus: () => void; reset: () => void } | null>(null);
function onOpenAutoFocus(event: Event) {
  event.preventDefault();
  void nextTick(() => searchRef.value?.focus());
}

// Confirmação visual do cadastro criado agora: "Cliente novo · CPF ···789-00".
const newCustomerNote = computed(() => {
  if (!props.resolvedNew) return "";
  const tail = cpfTail(props.customerTaxId);
  return tail ? `Cliente novo · CPF ${tail}` : "Cliente novo";
});
</script>

<template>
  <UiDialog :open="open" @update:open="$emit('update:open', Boolean($event))">
    <!-- MESMA CAIXA dos irmãos (Recebimento, Desconto): `max-h-[85vh]
         overflow-y-auto sm:max-w-lg`, cabeçalho padrão, altura pelo conteúdo.
         Era um painel fixo de 90vh × 60rem — sempre com a altura inteira da tela
         mesmo com três campos dentro, e um conteúdo de 42rem centrado num painel
         de 60rem, gerando faixas vazias dos dois lados. Três perguntas feitas na
         mesma sequência do balcão não podem chegar em três formatos diferentes:
         o operador reaprende a tela a cada uma. -->
    <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-lg" @open-auto-focus="onOpenAutoFocus">
      <UiDialogHeader>
        <UiDialogTitle>Cliente</UiDialogTitle>
        <UiDialogDescription>
          Busque por nome, telefone, CPF ou e-mail — selecione um cadastro ou crie um novo.
        </UiDialogDescription>
      </UiDialogHeader>

      <div>
        <div class="grid gap-5">
          <!-- 1 · associated customer (Odoo's pinned-and-highlighted) + Remover -->
          <div v-if="hasCustomer" class="grid gap-3 rounded-md border border-primary bg-primary/5 p-4">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="flex items-center gap-1.5 text-base font-semibold">
                  <Icon name="lucide:user-check" class="size-4 shrink-0 text-primary" />
                  <span class="truncate">{{ customerName || customerLookup?.name || "Cliente" }}</span>
                  <span
                    v-if="newCustomerNote"
                    class="inline-flex shrink-0 items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
                    role="status"
                  >
                    <Icon name="lucide:sparkles" class="size-3" />
                    {{ newCustomerNote }}
                  </span>
                </p>
                <p v-if="identityChips.length" class="mt-0.5 truncate text-sm tabular-nums text-muted-foreground">
                  {{ identityChips.join(" · ") }}
                </p>
              </div>
              <UiButton type="button" variant="outline" size="sm" class="shrink-0 text-destructive" @click="$emit('clear')">
                <Icon name="lucide:user-x" class="size-4" />
                Remover cliente
              </UiButton>
            </div>
            <!-- Guestman memory (warmer than Odoo's raw "All Orders"): favourite +
                 last order, one tap to apply. -->
            <div v-if="memory && (memory.favorite_item?.sku || memory.last_order_items?.length || memory.total_orders)" class="flex flex-wrap items-center gap-2">
              <span v-if="memory.total_orders" class="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                {{ memory.total_orders }} {{ memory.total_orders === 1 ? "pedido" : "pedidos" }}
              </span>
              <UiButton v-if="memory.favorite_item?.sku" type="button" variant="outline" size="xs" @click="$emit('applyCustomerFavorite')">
                <Icon name="lucide:heart" class="size-3.5" /> Favorito
              </UiButton>
              <UiButton v-if="memory.last_order_items?.length" type="button" variant="outline" size="xs" @click="$emit('repeatCustomerLastOrder')">
                <Icon name="lucide:rotate-ccw" class="size-3.5" /> Último pedido
              </UiButton>
            </div>

            <!-- Alertas do balcão: só existem quando há dado (a tela não cresce à toa).
                 Restrição alimentar é SEGURANÇA — sempre visível, cor funcional. -->
            <div v-if="customerLookup?.dietary_restrictions || customerLookup?.is_birthday_today || customerLookup?.is_birthday_month" class="flex flex-wrap items-center gap-2">
              <span v-if="customerLookup?.dietary_restrictions" class="inline-flex items-center gap-1 rounded-full border border-warning/50 bg-warning/10 px-2 py-0.5 text-xs font-medium text-amber-700 dark:text-amber-400">
                <Icon name="lucide:triangle-alert" class="size-3.5" /> {{ customerLookup.dietary_restrictions }}
              </span>
              <span v-if="customerLookup?.is_birthday_today" class="inline-flex items-center gap-1 rounded-full border border-primary/50 bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
                🎂 Aniversário HOJE{{ customerLookup?.birthday_promo_label ? ` · ${customerLookup.birthday_promo_label}` : "" }}
              </span>
              <span v-else-if="customerLookup?.is_birthday_month" class="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                🎂 Aniversariante do mês ({{ customerLookup?.birthday_display }})
              </span>
            </div>

            <!-- Preferências PERSISTENTES do cliente: liga E desliga aqui —
                 "hoje não" é desmarcar na venda; "nunca mais" é desligar AQUI. -->
            <div v-if="customerLookup?.ref" class="grid gap-2 border-t border-primary/20 pt-3">
              <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Preferências do cliente</p>
              <div class="grid grid-cols-2 gap-2">
                <UiButton
                  type="button" variant="outline" size="sm"
                  class="justify-between text-xs"
                  :class="profileDraft.cpf_na_nota ? 'border-primary bg-primary/5' : ''"
                  :disabled="profileSaving"
                  @click="toggleProfilePref('cpf_na_nota')"
                >
                  CPF na nota por padrão
                  <Icon :name="profileDraft.cpf_na_nota ? 'lucide:check' : 'lucide:minus'" class="size-3.5" />
                </UiButton>
                <UiButton
                  type="button" variant="outline" size="sm"
                  class="justify-between text-xs"
                  :class="profileDraft.email_receipt ? 'border-primary bg-primary/5' : ''"
                  :disabled="profileSaving"
                  @click="toggleProfilePref('email_receipt')"
                >
                  Nota por e-mail por padrão
                  <Icon :name="profileDraft.email_receipt ? 'lucide:check' : 'lucide:minus'" class="size-3.5" />
                </UiButton>
              </div>
              <label class="grid gap-1 text-sm">
                <span class="text-xs font-medium text-muted-foreground">Restrições alimentares</span>
                <UiInput v-model="profileDraft.dietary_restrictions" placeholder="Ex: alérgico a nozes" @blur="saveProfileText" />
              </label>
              <label class="grid gap-1 text-sm">
                <span class="text-xs font-medium text-muted-foreground">Observações do balcão</span>
                <UiTextarea v-model="profileDraft.notes" :rows="2" placeholder="Ex: prefere pão bem assado; busca às 17h" @blur="saveProfileText" />
              </label>
            </div>
          </div>

          <!-- 1.5 · A PERGUNTA — e ela vem antes do resto porque é o que trava
               a venda. Duas situações, uma forma: o sistema NÃO decide sozinho.

               · o WhatsApp digitado já é de outro cadastro (trocar de cliente é
                 legítimo, mas pela porta da frente — nunca como efeito colateral
                 de digitar num formulário de edição);
               · o contato do cliente associado vai mudar (o telefone errado
                 finalmente tem conserto no balcão, com os dois valores ditos
                 antes de acontecer).

               Âmbar porque é ATENÇÃO, não destruição — a paleta do operador é
               neutra e cor aqui só existe por função. -->
          <div
            v-if="customerDecision && decisionCopy"
            class="grid gap-3 rounded-md border border-warning/60 bg-warning/10 p-4"
            role="alertdialog"
            aria-live="assertive"
          >
            <p class="flex items-center gap-2 text-sm font-semibold text-amber-700 dark:text-amber-400">
              <Icon name="lucide:triangle-alert" class="size-4 shrink-0" />
              {{ decisionCopy.title }}
            </p>
            <p class="text-sm">{{ decisionCopy.body }}</p>
            <div class="grid gap-2 sm:grid-cols-2">
              <UiButton type="button" class="h-11 justify-center gap-2" @click="$emit('decisionConfirm')">
                <Icon :name="decisionCopy.confirmIcon" class="size-4 shrink-0" />
                <span class="min-w-0 truncate">{{ decisionCopy.confirmLabel }}</span>
              </UiButton>
              <UiButton type="button" variant="outline" class="h-11 justify-center gap-2" @click="$emit('decisionCancel')">
                <Icon :name="decisionCopy.cancelIcon" class="size-4 shrink-0" />
                <span class="min-w-0 truncate">{{ decisionCopy.cancelLabel }}</span>
              </UiButton>
            </div>
          </div>

          <!-- 2 · the picker: prominent search + rich results list.
               Enter decide (seleciona / cria por CPF / transfere / cadastra). -->
          <PosCustomerSearch
            ref="searchRef"
            :results="searchResults"
            :busy="searchBusy"
            :has-customer-ref="Boolean(customerLookup?.ref)"
            :pending-name="customerLookup?.ref ? '' : customerName"
            @search="$emit('search', $event)"
            @select="onSelect"
            @resolve-cpf="onResolveCpf"
            @transfer="onTransfer"
            @create-name-only="onCreateNameOnly"
            @conclude="onConclude"
          />

          <!-- 3 · create / edit form -->
          <div class="grid gap-3">
            <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {{ hasCustomer ? "Editar cadastro" : "Novo cadastro" }}
            </p>
            <div class="grid gap-3 sm:grid-cols-2">
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">Nome</span>
                <UiInput :model-value="customerName" placeholder="Nome no balcão" @update:model-value="$emit('update:customerName', String($event || ''))" />
              </label>
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">WhatsApp</span>
                <UiInput :model-value="customerPhone" inputmode="tel" placeholder="(43) 99999-0000" @update:model-value="$emit('update:customerPhone', String($event || ''))" />
              </label>
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">CPF/CNPJ</span>
                <UiInput :model-value="customerTaxId" inputmode="numeric" placeholder="Para fiscal" @update:model-value="$emit('update:customerTaxId', String($event || ''))" />
              </label>
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">E-mail</span>
                <UiInput :model-value="customerEmail" type="email" placeholder="cliente@email.com" @update:model-value="$emit('update:customerEmail', String($event || ''))" />
              </label>
            </div>
          </div>

          <!-- payment context only: comprovante (rides with the customer).
               O toggle "Emitir nota fiscal" saiu daqui e do checkout: emitir ou
               não é decisão da REGRA no servidor, nunca de quem está no caixa. O
               pedido do consumidor é o CPF, e ele mora no campo de identidade
               acima — um número, uma intenção. -->
          <div v-if="showFiscal" class="grid gap-3 border-t pt-4">
            <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Comprovante</p>
            <!-- MULTI: imprimir E enviar não competem. "Sem comprovante" é
                 nenhum canal marcado, não um terceiro botão. -->
            <div class="grid grid-cols-2 gap-2">
              <UiButton
                v-for="channel in receiptChannelOptions"
                :key="channel.ref"
                type="button"
                variant="outline"
                class="h-auto justify-center gap-1.5 whitespace-normal px-2 py-2 text-xs"
                :class="receiptChannels.includes(channel.ref) ? 'border-primary bg-primary/5' : ''"
                @click="toggleReceiptChannel(channel.ref)"
              >
                <Icon :name="receiptChannels.includes(channel.ref) ? 'lucide:check' : 'lucide:minus'" class="size-3.5" />
                {{ channel.label }}
              </UiButton>
            </div>
            <label v-if="receiptChannels.includes('email')" class="grid gap-1.5 text-sm">
              <span class="font-medium text-muted-foreground">E-mail do comprovante</span>
              <UiInput :model-value="receiptEmail" type="email" :placeholder="customerEmail || 'cliente@email.com'" @update:model-value="$emit('update:receiptEmail', String($event || ''))" />
              <span v-if="!receiptEmail.trim() && customerEmail.trim()" class="text-xs text-muted-foreground">
                Sem preencher, enviamos para o e-mail do cliente: <span class="font-medium text-foreground">{{ customerEmail }}</span>
              </span>
            </label>
          </div>
        </div>
      </div>

      <UiDialogFooter>
        <UiButton class="h-14 w-full" :disabled="Boolean(customerDecision)" @click="onConclude">
          Concluir
        </UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
