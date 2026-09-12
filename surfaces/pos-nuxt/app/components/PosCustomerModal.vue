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
import type { CustomerDecision, ServerConflictCandidate } from "~/presentation/customerDecision";
import { candidateSubtitle, candidateValue, customerDecisionCopy } from "~/presentation/customerDecision";
import type { ReceiptContactOffer } from "~/presentation/receiptContact";

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
  /** A unificação está em voo — o botão não pode disparar duas vezes. */
  customerMergeBusy?: boolean;
  /** A liberação do contato está em voo — mesmo motivo. */
  customerReleaseBusy?: boolean;
  /** Payment context: also show the fiscal/comprovante block. */
  showFiscal?: boolean;
  receiptChannels?: string[];
  receiptChannelOptions?: POSCheckoutOptionProjection[];
  receiptEmail?: string;
  /** A OFERTA sobre o e-mail do comprovante, decidida pela mesma função pura
   *  que a coluna do fechamento lê (`receiptSaveOffers`).
   *
   *  ⚠️ Ela precisa existir AQUI porque este campo é o GÊMEO do da coluna: quem
   *  digitava o e-mail por dentro do modal via o balão abrir lá atrás, do outro
   *  lado do overlay, e fechava o modal com a oferta JÁ MARCADA sem nunca ter
   *  sido perguntado. Padrão marcado + pergunta invisível = gravar calado com
   *  outro nome — exatamente o que este caminho existe para acabar. */
  receiptEmailOffer?: ReceiptContactOffer | null;
  saveReceiptContact?: boolean;
}>(), {
  customerDecision: null,
  customerMergeBusy: false,
  customerReleaseBusy: false,
  resolvedNew: false,
  showFiscal: false,
  receiptChannels: () => [],
  receiptChannelOptions: () => [],
  receiptEmail: "",
  receiptEmailOffer: null,
  saveReceiptContact: false,
});

const emit = defineEmits<{
  "update:open": [boolean];
  "update:customerName": [string];
  "update:customerPhone": [string];
  "update:customerTaxId": [string];
  "update:customerEmail": [string];
  "update:receiptChannels": [string[]];
  "update:receiptEmail": [string];
  "update:saveReceiptContact": [boolean];
  search: [string];
  selectResult: [POSCustomerSearchResult];
  clear: [];
  resolveCustomer: [];
  /** O operador assumiu a mudança (trocar de cliente / trocar o contato). */
  decisionConfirm: [];
  /** LIBERAR o contato preso num cadastro desativado — o valor a soltar viaja
   *  junto porque na LISTA ele é o da linha, não o do painel. */
  decisionRelease: [value: string];
  /** O operador ficou com o que estava — o valor digitado é descartado. */
  decisionCancel: [];
  /** É a MESMA pessoa: unificar os dois cadastros. */
  decisionMerge: [];
  /** Da LISTA de candidatos: atender ESTE. */
  decisionPick: [ServerConflictCandidate];
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

// Só um cadastro carregado representa cliente associado; texto digitado é rascunho.
const hasCustomer = computed(() => Boolean(props.customerLookup?.ref));
function initialCustomerPanel(): "search" | "form" {
  return props.customerLookup?.ref || props.customerName.trim() || props.customerPhone.trim() || props.customerTaxId.trim() || props.customerEmail.trim() ? "form" : "search";
}
const customerPanel = ref<"search" | "form">(initialCustomerPanel());
watch(() => props.open, (open) => {
  if (open) customerPanel.value = initialCustomerPanel();
});
function openNewCustomer() {
  if (props.customerLookup?.ref) emit("clear");
  customerPanel.value = "form";
}
watch(() => props.customerLookup?.ref, (ref) => {
  if (ref) customerPanel.value = "form";
});
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
// O contato que o painel libera: o que o operador digitou, ou o valor do dono
// quando a recusa veio sem o digitado.
const decisionReleaseValue = computed(
  () => props.customerDecision?.typed || props.customerDecision?.other?.value || "",
);

/**
 * A SEGUNDA palavra, e ela é assimétrica de propósito.
 *
 * Dois gestos aqui não são reversíveis: passar a venda para outro cadastro
 * (troca a identidade fiscal, a faixa de preço e as restrições do pedido) e
 * liberar um contato (apaga o registro do cadastro desativado). Os dois param e
 * perguntam de novo.
 *
 * ⚠️ O que NÃO pergunta de novo é a saída frequente — "Não, é só a nota",
 * "Manter Ana". Ela é um toque, sempre, e é isso que mantém a reconfirmação com
 * significado: fricção no caminho comum vira clique de reflexo, e aí a proteção
 * do caminho raro já não protege nada.
 *
 * `null` = ninguém está sendo perguntado. `""` = a liberação do painel (que não
 * tem valor por linha); qualquer outra string é a linha da lista de candidatos.
 */
const confirmingRelease = ref<string | null>(null);
const confirmingAttend = ref(false);

// A pergunta some quando a recusa muda: uma confirmação pendurada de outra
// decisão seria a pior espécie de sim — o operador respondendo a pergunta que
// não está mais na tela.
watch(() => props.customerDecision, () => {
  confirmingRelease.value = null;
  confirmingAttend.value = false;
});

function askRelease(value: string) {
  if (!decisionCopy.value?.release?.prompt) {
    emit("decisionRelease", value);
    return;
  }
  confirmingRelease.value = value;
}
function askConfirm() {
  if (!decisionCopy.value?.requiresConfirmation) {
    emit("decisionConfirm");
    return;
  }
  confirmingAttend.value = true;
}

function onSelect(result: POSCustomerSearchResult) {
  customerPanel.value = "form";
  emit("selectResult", result);
}
function onConclude() {
  // Uma pergunta aberta na tela não se responde fechando a tela.
  if (props.customerDecision || props.lookupBusy) return;
  if (customerPanel.value === "form") emit("resolveCustomer");
  emit("update:open", false);
}

// ── Atos NOMEADOS vindos do PosCustomerSearch ───────────────────────────────
// CPF sem resultado abre cadastro para revisão. Documento só para a nota
// permanece no fluxo fiscal separado.
function onResolveCpf(cpf: string) {
  emit("update:customerTaxId", cpf);
  customerPanel.value = "form";
}
// Telefone sem resultado: transfere para o campo do cadastro novo.
function onTransfer(payload: { field: "phone"; value: string }) {
  emit("update:customerPhone", payload.value);
  customerPanel.value = "form";
}
// Nome sem resultado abre o formulário; cadastrar exige o botão próprio.
function onCreateNameOnly(name: string) {
  emit("update:customerName", name);
  customerPanel.value = "form";
}

// Foco garantido na BUSCA ao abrir: sem isto o foco inicial do diálogo caía no
// primeiro focável — "Remover cliente", o pior lugar para um Enter distraído.
const searchRef = ref<{ focus: () => void; reset: () => void } | null>(null);
const nameInputRef = ref<{ inputRef?: HTMLInputElement } | null>(null);
function onOpenAutoFocus(event: Event) {
  event.preventDefault();
  void nextTick(() => {
    if (customerPanel.value === "search") searchRef.value?.focus();
    else nameInputRef.value?.inputRef?.focus();
  });
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
              <span v-if="customerLookup?.dietary_restrictions" class="inline-flex items-center gap-1 rounded-full border border-warning/50 bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">
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
            <p class="flex items-center gap-2 text-sm font-semibold text-warning">
              <Icon name="lucide:triangle-alert" class="size-4 shrink-0" />
              {{ decisionCopy.title }}
            </p>
            <p class="text-sm">{{ decisionCopy.body }}</p>

            <!-- A SEGUNDA PALAVRA. Aparece no lugar dos botões, não por cima
                 deles: um overlay sobre um alertdialog empilha duas camadas de
                 atenção e a de baixo some. Aqui o painel troca de pergunta, e a
                 saída de um toque ("não") continua a um toque. -->
            <div
              v-if="confirmingRelease !== null && decisionCopy.release?.prompt"
              class="grid gap-2 rounded-md border border-warning bg-background p-3"
              role="alertdialog"
              aria-live="assertive"
            >
              <p class="text-sm font-medium">{{ decisionCopy.release.prompt }}</p>
              <div class="grid gap-2 sm:grid-cols-2">
                <UiButton
                  type="button"
                  :disabled="customerReleaseBusy"
                  class="h-11 justify-center gap-2"
                  @click="$emit('decisionRelease', confirmingRelease); confirmingRelease = null"
                >
                  <Icon
                    :name="customerReleaseBusy ? 'lucide:loader-circle' : decisionCopy.release.icon"
                    class="size-4 shrink-0"
                    :class="customerReleaseBusy ? 'animate-spin' : ''"
                  />
                  <span class="min-w-0 truncate">Sim, liberar</span>
                </UiButton>
                <UiButton
                  type="button"
                  variant="outline"
                  class="h-11 justify-center gap-2"
                  @click="confirmingRelease = null"
                >
                  <Icon name="lucide:undo-2" class="size-4 shrink-0" />
                  <span class="min-w-0 truncate">Não liberar</span>
                </UiButton>
              </div>
            </div>

            <div
              v-else-if="confirmingAttend && decisionCopy.confirmPrompt"
              class="grid gap-2 rounded-md border border-warning bg-background p-3"
              role="alertdialog"
              aria-live="assertive"
            >
              <p class="text-sm font-medium">{{ decisionCopy.confirmPrompt }}</p>
              <div class="grid gap-2 sm:grid-cols-2">
                <UiButton
                  type="button"
                  class="h-11 justify-center gap-2"
                  @click="confirmingAttend = false; $emit('decisionConfirm')"
                >
                  <Icon :name="decisionCopy.confirmIcon" class="size-4 shrink-0" />
                  <span class="min-w-0 truncate">Sim, tenho certeza</span>
                </UiButton>
                <UiButton
                  type="button"
                  variant="outline"
                  class="h-11 justify-center gap-2"
                  @click="confirmingAttend = false"
                >
                  <Icon name="lucide:undo-2" class="size-4 shrink-0" />
                  <span class="min-w-0 truncate">Voltar</span>
                </UiButton>
              </div>
            </div>

            <!-- Sem UM campo culpado (dois ou mais intrusos, por campos
                 diferentes): a escolha é por LINHA. Antes disto o payload rico
                 já chegava do servidor e virava um toast que sumia. -->
            <ul
              v-if="customerDecision.kind === 'candidate_list' && confirmingRelease === null && !confirmingAttend"
              class="grid gap-2"
            >
              <li
                v-for="row in (customerDecision.candidates || [])"
                :key="row.ref"
                class="flex items-center gap-3 rounded-md border bg-background p-2"
              >
                <div class="min-w-0 flex-1">
                  <p class="truncate text-sm font-medium">
                    {{ row.name }}
                    <span v-if="row.is_current" class="text-xs font-normal text-muted-foreground">· na comanda</span>
                    <span v-else-if="row.owner_inactive" class="text-xs font-normal text-muted-foreground">· desativado</span>
                  </p>
                  <p class="truncate text-xs text-muted-foreground">{{ candidateSubtitle(row) }}</p>
                </div>
                <!-- Dono DESATIVADO não se atende: ele não aparece nem na
                     busca. A linha ficava com um botão desabilitado e nada
                     mais — o nome de quem segura o contato, e zero saída.
                     Liberar é a saída que o merge não dá. -->
                <UiButton
                  v-if="row.owner_inactive && decisionCopy.release"
                  type="button"
                  size="sm"
                  :disabled="customerReleaseBusy"
                  class="h-9 shrink-0 gap-2"
                  @click="askRelease(candidateValue(row, customerDecision.field))"
                >
                  <Icon
                    :name="customerReleaseBusy ? 'lucide:loader-circle' : decisionCopy.release.icon"
                    class="size-4 shrink-0"
                    :class="customerReleaseBusy ? 'animate-spin' : ''"
                  />
                  {{ decisionCopy.release.label }}
                </UiButton>
                <UiButton
                  v-else
                  type="button"
                  size="sm"
                  :variant="row.is_current ? 'outline' : 'default'"
                  :disabled="row.owner_inactive"
                  class="h-9 shrink-0 gap-2"
                  @click="$emit('decisionPick', row)"
                >
                  <Icon name="lucide:user-round-check" class="size-4 shrink-0" />
                  Atender este
                </UiButton>
              </li>
            </ul>

            <!-- LIBERAR — a saída do contato preso num cadastro desativado, e a
                 ação PRINCIPAL desse caso: atender não existe (o dono não
                 aparece na busca) e unificar o Core recusa. Na lista ela mora
                 na linha; aqui, em cima do par que fica. -->
            <UiButton
              v-if="decisionCopy.release && customerDecision.kind !== 'candidate_list' && confirmingRelease === null && !confirmingAttend"
              type="button"
              :disabled="customerReleaseBusy"
              class="h-11 w-full justify-center gap-2"
              @click="askRelease(decisionReleaseValue)"
            >
              <Icon
                :name="customerReleaseBusy ? 'lucide:loader-circle' : decisionCopy.release.icon"
                class="size-4 shrink-0"
                :class="customerReleaseBusy ? 'animate-spin' : ''"
              />
              <span class="min-w-0 truncate">{{ decisionCopy.release.label }}</span>
            </UiButton>

            <div
              v-if="confirmingRelease === null && !confirmingAttend"
              class="grid gap-2"
              :class="decisionCopy.confirmLabel ? 'sm:grid-cols-2' : ''"
            >
              <UiButton
                v-if="decisionCopy.confirmLabel"
                type="button"
                class="h-11 justify-center gap-2"
                @click="askConfirm()"
              >
                <Icon :name="decisionCopy.confirmIcon" class="size-4 shrink-0" />
                <span class="min-w-0 truncate">{{ decisionCopy.confirmLabel }}</span>
              </UiButton>
              <UiButton type="button" variant="outline" class="h-11 justify-center gap-2" @click="$emit('decisionCancel')">
                <Icon :name="decisionCopy.cancelIcon" class="size-4 shrink-0" />
                <span class="min-w-0 truncate">{{ decisionCopy.cancelLabel }}</span>
              </UiButton>
            </div>

            <!-- A TERCEIRA saída, e ela é de linha inteira porque não é o
                 caminho comum: os dois cadastros são a MESMA pessoa. -->
            <UiButton
              v-if="decisionCopy.merge && confirmingRelease === null && !confirmingAttend"
              type="button"
              variant="ghost"
              :disabled="customerMergeBusy"
              class="h-11 w-full justify-center gap-2"
              @click="$emit('decisionMerge')"
            >
              <Icon
                :name="customerMergeBusy ? 'lucide:loader-circle' : decisionCopy.merge.icon"
                class="size-4 shrink-0"
                :class="customerMergeBusy ? 'animate-spin' : ''"
              />
              <span class="min-w-0 truncate">{{ decisionCopy.merge.label }}</span>
            </UiButton>
          </div>

          <!-- 2 · the picker: prominent search + rich results list.
               Enter decide (seleciona / cria por CPF / transfere / cadastra). -->
          <div class="grid grid-cols-2 gap-2" aria-label="Escolher como identificar cliente">
            <UiButton type="button" :variant="customerPanel === 'search' ? 'default' : 'outline'" @click="customerPanel = 'search'">
              Buscar existente
            </UiButton>
            <UiButton type="button" :variant="customerPanel === 'form' ? 'default' : 'outline'" @click="openNewCustomer">
              Cadastrar novo
            </UiButton>
          </div>
          <PosCustomerSearch
            v-if="customerPanel === 'search'"
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
          <div v-if="customerPanel === 'form'" class="grid gap-3">
            <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {{ customerLookup?.ref ? "Editar cadastro" : "Novo cadastro" }}
            </p>
            <div class="grid gap-3 sm:grid-cols-2">
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">Nome</span>
                <UiInput ref="nameInputRef" :model-value="customerName" placeholder="Nome no balcão" @update:model-value="$emit('update:customerName', String($event || ''))" />
              </label>
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">WhatsApp</span>
                <UiInput :model-value="customerPhone" inputmode="tel" placeholder="(43) 99999-0000" @update:model-value="$emit('update:customerPhone', String($event || ''))" />
              </label>
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">CPF/CNPJ</span>
                <UiInput :model-value="customerTaxId" inputmode="numeric" placeholder="Documento do cadastro" @update:model-value="$emit('update:customerTaxId', String($event || ''))" />
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
            <!-- ⚠️ Sem `<label>` em volta: a oferta traz o interruptor dela num
                 `<label>` próprio, e rótulo dentro de rótulo faz o clique no
                 texto do campo alternar o interruptor. O vínculo do nome com o
                 campo passa a ser o `aria-label`. -->
            <div v-if="receiptChannels.includes('email')" class="grid gap-1.5 text-sm">
              <span class="font-medium text-muted-foreground">E-mail do comprovante</span>
              <!-- A MESMA pergunta da coluna, no campo GÊMEO. `top` porque logo
                   abaixo está o "Concluir": o balão não pode tapar o botão que
                   encerra o modal. -->
              <PosReceiptSaveOffer
                v-if="receiptEmailOffer"
                :offer="receiptEmailOffer"
                :checked="saveReceiptContact"
                side="top"
                @update:checked="$emit('update:saveReceiptContact', $event)"
              >
                <UiInput :model-value="receiptEmail" type="email" aria-label="E-mail do comprovante" :placeholder="customerEmail || 'cliente@email.com'" @update:model-value="$emit('update:receiptEmail', String($event || ''))" />
              </PosReceiptSaveOffer>
              <UiInput v-else :model-value="receiptEmail" type="email" aria-label="E-mail do comprovante" :placeholder="customerEmail || 'cliente@email.com'" @update:model-value="$emit('update:receiptEmail', String($event || ''))" />
              <span v-if="!receiptEmail.trim() && customerEmail.trim()" class="text-xs text-muted-foreground">
                Sem preencher, enviamos para o e-mail do cliente: <span class="font-medium text-foreground">{{ customerEmail }}</span>
              </span>
            </div>
          </div>
        </div>
      </div>

      <UiDialogFooter>
        <UiButton class="h-14 w-full" :disabled="Boolean(customerDecision) || lookupBusy" @click="onConclude">
          {{ customerPanel === "form" ? (customerLookup?.ref ? "Salvar cadastro" : "Cadastrar cliente") : "Concluir" }}
        </UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
