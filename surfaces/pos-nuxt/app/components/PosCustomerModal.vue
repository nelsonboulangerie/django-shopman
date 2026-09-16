<script setup lang="ts">
import { toast } from "vue-sonner";
// Customer picker (spec — Odoo "Choose Customer" clone, redesign 2026-06-10;
// estrutura única 2026-09-16).
// One SHARED modal for both the comanda header and the payment screen. UMA
// estrutura, sempre a mesma — a diferença "existente × novo" é dita por um
// SELO, não por abas:
//   1. the decision (contact conflict / receipt identity), when there is one,
//      above everything: it is what blocks the sale;
//   2. a prominent search → rich results list (shared PosCustomerSearch),
//      always on top: Enter decides, named acts;
//   3. the state badge: "Cadastro existente · Nome" (with "Remover cliente",
//      memory and alerts) or "Cliente novo";
//   4. the SAME form for both (nome, WhatsApp, CPF/CNPJ, e-mail);
//   5. "Padrões deste cliente" — the PERSISTENT defaults, only with a ref.
// ⚠️ The receipt of THIS sale (print / e-mail / CPF on the invoice) does NOT
// live here: it is the "Nota e comprovante" column of the payment screen. The
// modal sets the customer's DEFAULTS; the column decides the sale of NOW.
// Renders intent; the shell owns clearCustomer / resolveCustomer / search.
import type {
  POSCustomerLookupProjection,
  POSCustomerSearchResult,
} from "~/types/pos";
import { cpfTail } from "~/presentation/customerSearch";
import type { CustomerDecision, ServerConflictCandidate } from "~/presentation/customerDecision";
import { candidateSubtitle, candidateValue, customerDecisionCopy } from "~/presentation/customerDecision";

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
  /** Rascunho dos PADRÕES do cliente NOVO. Mora no shell (é ele que o manda
   *  no "Cadastrar cliente" como `fiscal_prefs`); o modal só o lê e pede a
   *  mudança por `applyPreference`. Com cadastro, a fonte é o lookup. */
  newCustomerPrefs?: { cpf_na_nota?: boolean; email_receipt?: boolean };
}>(), {
  customerDecision: null,
  customerMergeBusy: false,
  customerReleaseBusy: false,
  resolvedNew: false,
  newCustomerPrefs: () => ({}),
});

const emit = defineEmits<{
  "update:open": [boolean];
  "update:customerName": [string];
  "update:customerPhone": [string];
  "update:customerTaxId": [string];
  "update:customerEmail": [string];
  search: [string];
  selectResult: [POSCustomerSearchResult];
  clear: [];
  resolveCustomer: [done: (saved: boolean) => void];
  /** O operador assumiu a mudança (trocar de cliente / trocar o contato). */
  decisionConfirm: [ownerRef?: string];
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
  /** Um padrão virado vale NESTA venda, na hora — o shell aplica ao carrinho
   *  (e, sem cadastro, guarda o rascunho que viaja no cadastrar). */
  applyPreference: [key: "cpf_na_nota" | "email_receipt", value: boolean];
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

// O interruptor lê do cadastro (rascunho sincronizado do lookup) ou, sem
// cadastro, do rascunho que o shell guarda para o cadastrar.
function prefOn(key: "cpf_na_nota" | "email_receipt"): boolean {
  return props.customerLookup?.ref ? profileDraft[key] : Boolean(props.newCustomerPrefs?.[key]);
}
// Virar o interruptor: com cadastro, grava no perfil (POST parcial); sem
// cadastro, o shell guarda o rascunho. Nos dois casos a venda de AGORA muda
// na hora — "vale nesta venda e nas próximas".
function setProfilePref(key: "cpf_na_nota" | "email_receipt", value: boolean) {
  if (props.customerLookup?.ref) {
    profileDraft[key] = value;
    void saveProfile({ fiscal_prefs: { [key]: value } });
  }
  emit("applyPreference", key, value);
}

function saveProfileText() {
  void saveProfile({
    dietary_restrictions: profileDraft.dietary_restrictions,
    notes: profileDraft.notes,
  });
}

// Só um cadastro carregado representa cliente associado; texto digitado é rascunho.
const hasCustomer = computed(() => Boolean(props.customerLookup?.ref));
const displayName = computed(() =>
  props.customerName || props.customerLookup?.name || props.customerLookup?.email || props.customerLookup?.tax_id || "Cliente",
);
// O SELO diz o estado; o formulário é o mesmo nos dois. "Criado agora" é o
// cadastro que acabou de nascer pelo resolve — existente, mas não "encontrado".
const stateBadge = computed(() => {
  if (!hasCustomer.value) return "Cliente novo";
  return `${props.resolvedNew ? "Cadastro criado agora" : "Cadastro existente"} · ${displayName.value}`;
});
// O formulário DIVERGE do cadastro? Decide o rótulo do rodapé: com o cadastro
// intocado, "Concluir" só fecha — salvar o que não mudou era um POST à toa.
const formDirty = computed(() => {
  const lookup = props.customerLookup;
  if (!lookup?.ref) return false;
  const differs = (typed: string, stored: string | null | undefined) => typed.trim() !== (stored || "").trim();
  return differs(props.customerName, lookup.name)
    || differs(props.customerPhone, lookup.phone)
    || differs(props.customerTaxId, lookup.tax_id)
    || differs(props.customerEmail, lookup.email);
});
// Algum dado no formulário sem cadastro: o rodapé vira "Cadastrar cliente".
// E-mail entra porque o resolve do shell também o aceita sozinho.
const formFilled = computed(() =>
  [props.customerName, props.customerPhone, props.customerTaxId, props.customerEmail].some((v) => v.trim()),
);
const footerAction = computed<"conclude" | "save" | "create">(() => {
  if (hasCustomer.value) return formDirty.value ? "save" : "conclude";
  return formFilled.value ? "create" : "conclude";
});
const footerLabel = computed(() =>
  footerAction.value === "save" ? "Salvar cadastro" : footerAction.value === "create" ? "Cadastrar cliente" : "Concluir",
);
const memory = computed(() => props.customerLookup?.memory || null);
const identityChips = computed(() =>
  [props.customerPhone, props.customerTaxId, props.customerEmail].map((v) => v.trim()).filter(Boolean),
);

// Reset the shared search field whenever the modal reopens fresh.
watch(() => props.open, (open) => { if (!open) emit("search", ""); });

// A RECUSA TRAZ A TELA DE VOLTA. O "Concluir" fecha o modal e só depois a
// resposta do servidor chega: sem isto, a recusa nasceria atrás de uma tela
// fechada e o operador veria a venda seguir com o cliente errado.
const isReceiptDecision = computed(() => props.customerDecision?.kind === "receipt_identity");
const receiptTitleRef = ref<{ $el?: HTMLElement } | null>(null);
const receiptActionRef = ref<{ $el?: HTMLElement } | null>(null);
const decisionCopy = computed(() =>
  props.customerDecision ? customerDecisionCopy(props.customerDecision) : null,
);
watch(() => props.customerDecision, (decision, previous) => {
  if (decision && !props.open) emit("update:open", true);
  if (!decision && previous?.kind === "receipt_identity") emit("update:open", false);
  if (decision?.kind === "receipt_identity") void nextTick(() => receiptTitleRef.value?.$el?.focus());
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

const receiptPanelRef = ref<HTMLElement | null>(null);
const selectedReceiptOwner = ref("");
const receiptFields = computed(() => (props.customerDecision?.receiptFields || (props.customerDecision?.other ? [{
  field: props.customerDecision.field === "tax_id" ? "tax_id" as const : "email" as const,
  value: props.customerDecision.typed, owner: props.customerDecision.other,
  active: props.customerDecision.candidates?.find(c => c.ref === props.customerDecision?.other?.ref)?.owner_inactive !== true,
}] : [])).map(field => ({ ...field, owner: { ...field.owner, name: field.owner.name || (field.owner.ref ? formatReceiptValue(field.field, field.value) : '') } })));
const receiptOwners = computed(() => [...new Map(receiptFields.value.filter(f => f.owner.ref).map(f => [f.owner.ref, f])).values()]);
const receiptActiveOwners = computed(() => receiptOwners.value.filter(f => f.active !== false));
const receiptNewFieldsLabel = computed(() => receiptFields.value.filter(f => !f.owner.ref).map(f => f.field === 'tax_id' ? 'CPF' : 'e-mail').join(' e '));
const receiptActions = computed(() => {
  const choices: Array<{ ref: string; label: string }> = [];
  if (props.customerDecision?.receiptTaxIdOverwrite) return [{ ref: '__save_confirmed__', label: 'Trocar CPF e vincular ao pedido' }, { ref: '', label: 'Usar dados só neste pedido' }];
  if (props.customerDecision?.receiptCreate) choices.push({ ref: '__create__', label: 'Cadastrar e vincular ao pedido' });
  if (props.customerDecision?.receiptSave) choices.push({ ref: '__save__', label: `Salvar no cadastro de ${props.customerDecision.current?.name || 'cliente'}` });
  for (const field of receiptActiveOwners.value) choices.push({ ref: field.owner.ref,
    label: receiptNewFieldsLabel.value ? `Vincular ${field.owner.name} e salvar ${receiptNewFieldsLabel.value}`
      : receiptOwners.value.length === 1 ? 'Sim, vincular ao pedido' : `Vincular ${field.owner.name}` });
  choices.push({ ref: '', label: 'Usar dados só neste pedido' });
  return choices;
});
const receiptTitle = computed(() => {
  if (props.customerDecision?.receiptTaxIdOverwrite) return `Trocar CPF do cadastro${props.customerDecision.receiptTaxIdOverwrite.customerName ? ' de ' + props.customerDecision.receiptTaxIdOverwrite.customerName : ''}?`;
  if (confirmingAttend.value) {
    if (selectedReceiptOwner.value === '__create__') return 'Cadastrar e vincular ao pedido?';
    if (selectedReceiptOwner.value === '__save__') return `Salvar ${receiptNewFieldsLabel.value} no cadastro de ${props.customerDecision?.current?.name || 'cliente'}?`;
    return `Vincular ${receiptOwners.value.find(f => f.owner.ref === selectedReceiptOwner.value)?.owner.name || 'cliente'} ao pedido?`;
  }
  if (props.customerDecision?.receiptCreate) return 'Cadastrar o cliente deste pedido?';
  if (props.customerDecision?.receiptSave && !receiptOwners.value.length) return 'Salvar os dados no cadastro?';
  return receiptOwners.value.length === 1 ? `Este pedido é de ${receiptOwners.value[0]!.owner.name}?` : 'Quem é o cliente deste pedido?';
});
function activateReceiptAction(index: number) {
  const action = receiptActions.value[index];
  if (!action || props.lookupBusy) return;
  if (!action.ref) void cancelDecision();
  else chooseReceiptOwner(action.ref);
}
function formatReceiptValue(field: string, value: string) {
  return field === "tax_id" && /^\d{11}$/.test(value)
    ? value.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, "$1.$2.$3-$4") : value;
}
function chooseReceiptOwner(ref: string) {
  if (props.lookupBusy) return;
  selectedReceiptOwner.value = ref;
  confirmingAttend.value = true;
}
function receiptButtons() {
  return [...(receiptPanelRef.value?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") || [])];
}
watch(confirmingAttend, () => {
  if (isReceiptDecision.value) void nextTick(() => receiptTitleRef.value?.$el?.focus());
});
function onReceiptKey(event: KeyboardEvent) {
  if (!isReceiptDecision.value || event.altKey || event.ctrlKey || event.metaKey || event.isComposing) return;
  const key = event.key;
  if (!["1", "2", "3", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter", " ", "Escape"].includes(key)) return;
  event.stopPropagation();
  if (props.lookupBusy || event.repeat) { event.preventDefault(); return; }
  if (key === "Escape") {
    event.preventDefault();
    if (confirmingAttend.value) confirmingAttend.value = false;
    else emit("update:open", false);
    return;
  }
  if (key.startsWith("Arrow")) {
    event.preventDefault();
    const buttons = receiptButtons();
    const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const direction = key === "ArrowLeft" || key === "ArrowUp" ? -1 : 1;
    buttons[current < 0 ? (direction > 0 ? 0 : buttons.length - 1) : (current + direction + buttons.length) % buttons.length]?.focus();
  } else if (!confirmingAttend.value && ["1", "2", "3"].includes(key)) {
    event.preventDefault();
    activateReceiptAction(Number(key) - 1);
  }
  // Enter/Space usam o clique nativo do botão focado. Tab mantém a navegação do diálogo.
}

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

async function cancelDecision() {
  if (props.lookupBusy) return;
  const decision = props.customerDecision;
  emit("decisionCancel");
  if (decision?.kind !== "existing_customer") return;
  await nextTick();
  const input = decision.field === "phone" ? phoneInputRef : decision.field === "email" ? emailInputRef : taxIdInputRef;
  input.value?.inputRef?.focus();
}

function onSelect(result: POSCustomerSearchResult) {
  emit("selectResult", result);
}
const concludePending = ref(false);
function onConclude() {
  // Uma pergunta aberta na tela não se responde fechando a tela.
  if (props.customerDecision || props.lookupBusy || concludePending.value) return;
  // Nada a salvar (cadastro intocado, ou formulário vazio): concluir só fecha.
  if (footerAction.value === "conclude") {
    emit("update:open", false);
    return;
  }
  concludePending.value = true;
  emit("resolveCustomer", (saved) => {
    concludePending.value = false;
    if (saved) emit("update:open", false);
  });
}

// ── Atos NOMEADOS vindos do PosCustomerSearch ───────────────────────────────
// O formulário está sempre na tela: transferir é preencher o campo E levar o
// foco ao próximo dado que falta. Cadastrar continua exigindo o botão próprio.
// CPF sem resultado: o documento vai ao cadastro para revisão. Documento só
// para a nota permanece no fluxo fiscal separado.
function onResolveCpf(cpf: string) {
  emit("update:customerTaxId", cpf);
  void nextTick(() => nameInputRef.value?.inputRef?.focus());
}
// Telefone sem resultado: transfere para o campo do cadastro novo.
function onTransfer(payload: { field: "phone"; value: string }) {
  emit("update:customerPhone", payload.value);
  void nextTick(() => nameInputRef.value?.inputRef?.focus());
}
// Nome sem resultado vai ao formulário; o WhatsApp é o próximo dado que falta.
function onCreateNameOnly(name: string) {
  emit("update:customerName", name);
  void nextTick(() => phoneInputRef.value?.inputRef?.focus());
}

// Foco garantido na BUSCA ao abrir: sem isto o foco inicial do diálogo caía no
// primeiro focável — "Remover cliente", o pior lugar para um Enter distraído.
const searchRef = ref<{ focus: () => void; reset: () => void } | null>(null);
const nameInputRef = ref<{ inputRef?: HTMLInputElement } | null>(null);
const phoneInputRef = ref<{ inputRef?: HTMLInputElement } | null>(null);
const emailInputRef = ref<{ inputRef?: HTMLInputElement } | null>(null);
const taxIdInputRef = ref<{ inputRef?: HTMLInputElement } | null>(null);
function onOpenAutoFocus(event: Event) {
  event.preventDefault();
  void nextTick(() => {
    if (isReceiptDecision.value) receiptTitleRef.value?.$el?.focus();
    else if (!hasCustomer.value) searchRef.value?.focus();
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
    <!-- A decisão do documento usa largura compacta; o cadastro mantém seu formulário. -->
    <UiDialogContent class="max-h-[85vh] overflow-y-auto" :class="isReceiptDecision ? 'w-[calc(100%-2rem)] max-w-[360px] sm:max-w-[360px]' : 'sm:max-w-lg'" @open-auto-focus="onOpenAutoFocus" @keydown.capture="onReceiptKey">
      <UiDialogHeader>
        <UiDialogTitle ref="receiptTitleRef" :tabindex="isReceiptDecision ? -1 : undefined" :class="isReceiptDecision ? 'pr-4 text-left' : undefined">{{ isReceiptDecision ? receiptTitle : "Cliente" }}</UiDialogTitle>
        <UiDialogDescription v-if="!isReceiptDecision">
          Busque por nome, telefone, CPF ou e-mail — selecione um cadastro ou crie um novo.
        </UiDialogDescription>
      </UiDialogHeader>

      <div>
        <div class="grid gap-5">
          <!-- 1 · A PERGUNTA — e ela vem antes do resto porque é o que trava
               a venda. Duas situações, uma forma: o sistema NÃO decide sozinho.

               · o WhatsApp digitado já é de outro cadastro (trocar de cliente é
                 legítimo, mas pela porta da frente — nunca como efeito colateral
                 de digitar num formulário de edição);
               · o contato do cliente associado vai mudar (o telefone errado
                 finalmente tem conserto no balcão, com os dois valores ditos
                 antes de acontecer).

               Âmbar porque é ATENÇÃO, não destruição — a paleta do operador é
               neutra e cor aqui só existe por função. -->
          <div v-if="isReceiptDecision && decisionCopy" ref="receiptPanelRef" class="grid gap-4" data-receipt-choice aria-live="polite">
            <template v-if="!confirmingAttend">
              <div v-if="customerDecision?.receiptTaxIdOverwrite" class="grid gap-1 text-sm">
                <p>Atual: {{ formatReceiptValue('tax_id', customerDecision.receiptTaxIdOverwrite.from) }}</p>
                <p>Novo: {{ formatReceiptValue('tax_id', customerDecision.receiptTaxIdOverwrite.to) }}</p>
              </div>
              <div class="grid gap-3">
                <div v-for="field in receiptFields" :key="field.field" class="grid gap-1">
                  <p class="text-xs text-muted-foreground">{{ field.field === 'tax_id' ? 'CPF na nota' : 'Enviar por e-mail' }}</p>
                  <p class="text-sm break-all">{{ formatReceiptValue(field.field, field.value) }}</p>
                  <p v-if="receiptOwners.length > 1 && field.owner.ref" class="text-sm font-medium">{{ field.owner.name }}{{ field.active === false ? ' (inativo)' : '' }}</p>
                </div>
                <div v-if="receiptOwners.length === 1">
                  <p class="text-xs text-muted-foreground">Cadastro encontrado</p>
                  <p class="text-sm font-medium">{{ receiptOwners[0]!.owner.name }}{{ receiptOwners[0]!.active === false ? ' (inativo)' : '' }}</p>
                </div>
                <p v-if="customerDecision?.current" class="text-xs text-muted-foreground">Cliente do pedido: {{ customerDecision.current.name }}</p>
              </div>
              <div class="grid gap-2">
                <UiButton v-for="(action, index) in receiptActions" :key="action.ref" type="button" variant="secondary" class="min-h-12 h-auto justify-between whitespace-normal py-3 text-left" :disabled="lookupBusy" :aria-keyshortcuts="String(index + 1)" @click="activateReceiptAction(index)">
                  {{ action.label }} <kbd aria-hidden="true" class="text-xs opacity-70">{{ index + 1 }}</kbd>
                </UiButton>
              </div>
            </template>
            <template v-else>
              <p class="text-xs text-muted-foreground">{{ selectedReceiptOwner === '__create__' ? 'Os dados serão salvos em um novo cadastro.' : selectedReceiptOwner.startsWith('__save') ? 'Os dados do cadastro serão alterados.' : receiptNewFieldsLabel ? `Salvar ${receiptNewFieldsLabel} no cadastro escolhido. Preços e benefícios serão revisados.` : 'Preços e benefícios serão revisados.' }}</p>
              <div class="grid gap-2">
                <UiButton type="button" variant="secondary" class="min-h-12" :disabled="lookupBusy" @click="$emit('decisionConfirm', selectedReceiptOwner)">Confirmar cliente</UiButton>
                <UiButton type="button" variant="secondary" class="min-h-12" :disabled="lookupBusy" @click="confirmingAttend = false">Voltar</UiButton>
              </div>
            </template>
            <p class="text-xs text-muted-foreground">{{ confirmingAttend ? '' : '1–' + receiptActions.length + ' escolher · ' }}Tab / ↑ ↓ navegar<br>Enter acionar · Esc voltar</p>
          </div>
          <div
            v-if="customerDecision && decisionCopy && !isReceiptDecision"
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
                v-if="isReceiptDecision"
                ref="receiptActionRef"
                type="button"
                :disabled="lookupBusy"
                class="h-11 justify-center gap-2"
                @click="cancelDecision"
              >
                <Icon :name="decisionCopy.cancelIcon" class="size-4 shrink-0" />
                <span class="min-w-0 truncate">{{ decisionCopy.cancelLabel }}</span>
              </UiButton>
              <UiButton
                v-if="decisionCopy.confirmLabel"
                type="button"
                :disabled="lookupBusy"
                :variant="isReceiptDecision ? 'outline' : 'default'"
                class="h-11 justify-center gap-2"
                @click="askConfirm()"
              >
                <Icon :name="decisionCopy.confirmIcon" class="size-4 shrink-0" />
                <span class="min-w-0 truncate">{{ decisionCopy.confirmLabel }}</span>
              </UiButton>
              <UiButton v-if="!isReceiptDecision" type="button" variant="outline" class="h-11 justify-center gap-2" @click="cancelDecision">
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

          <!-- 2 · the picker, SEMPRE no topo: prominent search + rich results
               list. Enter decide (seleciona / cria por CPF / transfere / nomeia
               o cadastro só com o nome / conclui). Escolher um resultado ou
               transferir preenche o formulário logo abaixo — não há painel para
               trocar. -->
          <PosCustomerSearch
            v-if="!isReceiptDecision"
            ref="searchRef"
            :results="searchResults"
            :busy="searchBusy"
            :has-customer-ref="hasCustomer"
            :pending-name="hasCustomer ? '' : customerName"
            @search="$emit('search', $event)"
            @select="onSelect"
            @resolve-cpf="onResolveCpf"
            @transfer="onTransfer"
            @create-name-only="onCreateNameOnly"
            @conclude="onConclude"
          />

          <!-- 3 · UMA estrutura: selo de estado + o MESMO formulário para
               existente e novo. O selo (e o tom) é a única diferença nítida —
               abas "buscar × cadastrar" faziam o operador escolher um modo
               antes de saber se a pessoa já tinha cadastro. -->
          <div
            v-if="!isReceiptDecision"
            class="grid gap-3 rounded-md border p-4"
            :class="hasCustomer ? 'border-primary bg-primary/5' : 'bg-muted/30'"
            data-customer-state
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <p class="flex items-center gap-1.5 text-base font-semibold" role="status">
                  <Icon
                    :name="hasCustomer ? 'lucide:user-check' : 'lucide:user-round-plus'"
                    class="size-4 shrink-0"
                    :class="hasCustomer ? 'text-primary' : 'text-muted-foreground'"
                  />
                  <span class="truncate">{{ stateBadge }}</span>
                  <span
                    v-if="newCustomerNote"
                    class="inline-flex shrink-0 items-center gap-1 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
                  >
                    <Icon name="lucide:sparkles" class="size-3" />
                    {{ newCustomerNote }}
                  </span>
                </p>
                <p v-if="hasCustomer && identityChips.length" class="mt-0.5 truncate text-sm tabular-nums text-muted-foreground">
                  {{ identityChips.join(" · ") }}
                </p>
                <p v-else-if="!hasCustomer" class="mt-0.5 text-sm text-muted-foreground">
                  Preencha o que souber; só o nome já basta.
                </p>
              </div>
              <UiButton v-if="hasCustomer" type="button" variant="outline" size="sm" class="shrink-0 text-destructive" @click="$emit('clear')">
                <Icon name="lucide:user-x" class="size-4" />
                Remover cliente
              </UiButton>
            </div>
            <!-- Guestman memory (warmer than Odoo's raw "All Orders"): favourite +
                 last order, one tap to apply. -->
            <div v-if="hasCustomer && memory && (memory.favorite_item?.sku || memory.last_order_items?.length || memory.total_orders)" class="flex flex-wrap items-center gap-2">
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
            <div v-if="hasCustomer && (customerLookup?.dietary_restrictions || customerLookup?.is_birthday_today || customerLookup?.is_birthday_month)" class="flex flex-wrap items-center gap-2">
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

            <!-- 4 · the form — o MESMO para existente e novo. O e-mail daqui é
                 o do CADASTRO, e só grava no "Salvar cadastro"; o e-mail do
                 comprovante desta venda mora na tela de pagamento. -->
            <div class="grid gap-3 sm:grid-cols-2">
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">Nome</span>
                <UiInput ref="nameInputRef" :model-value="customerName" placeholder="Nome no balcão" @update:model-value="$emit('update:customerName', String($event || ''))" />
              </label>
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">WhatsApp</span>
                <UiInput ref="phoneInputRef" :model-value="customerPhone" inputmode="tel" placeholder="(43) 99999-0000" @update:model-value="$emit('update:customerPhone', String($event || ''))" />
              </label>
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">CPF/CNPJ</span>
                <UiInput ref="taxIdInputRef" :model-value="customerTaxId" inputmode="numeric" placeholder="Documento do cadastro" @update:model-value="$emit('update:customerTaxId', String($event || ''))" />
              </label>
              <label class="grid gap-1.5 text-sm">
                <span class="font-medium text-muted-foreground">E-mail</span>
                <UiInput ref="emailInputRef" :model-value="customerEmail" type="email" placeholder="cliente@email.com" @update:model-value="$emit('update:customerEmail', String($event || ''))" />
              </label>
            </div>

            <!-- 5 · PADRÕES do cliente: valem NESTA venda, na hora, e nas
                 próximas. Liga E desliga aqui — "hoje não" é desmarcar na
                 venda; "nunca mais" é desligar AQUI. Com cadastro, grava no
                 perfil; sem cadastro, o rascunho viaja no "Cadastrar cliente".
                 INTERRUPTORES, não botões-com-check: padrão é ESTADO ("sempre
                 assim"), e o switch diz de longe se está ligado. -->
            <div class="grid gap-2 border-t pt-3" :class="hasCustomer ? 'border-primary/20' : ''" data-customer-defaults>
              <p class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Padrões deste cliente</p>
              <p class="text-xs text-muted-foreground">Vale nesta venda e nas próximas.</p>
              <div class="grid divide-y rounded-md border">
                <label class="flex cursor-pointer items-center justify-between gap-3 px-3 py-2 text-sm">
                  <span class="flex min-w-0 items-center gap-2 font-medium">
                    <Icon name="lucide:id-card" class="size-4 shrink-0 text-muted-foreground" />
                    CPF na nota
                  </span>
                  <UiSwitch
                    :model-value="prefOn('cpf_na_nota')"
                    :disabled="profileSaving"
                    aria-label="CPF na nota"
                    @update:model-value="setProfilePref('cpf_na_nota', $event)"
                  />
                </label>
                <label class="flex cursor-pointer items-center justify-between gap-3 px-3 py-2 text-sm">
                  <span class="flex min-w-0 items-center gap-2 font-medium">
                    <Icon name="lucide:mail" class="size-4 shrink-0 text-muted-foreground" />
                    Nota por e-mail
                  </span>
                  <UiSwitch
                    :model-value="prefOn('email_receipt')"
                    :disabled="profileSaving"
                    aria-label="Nota por e-mail"
                    @update:model-value="setProfilePref('email_receipt', $event)"
                  />
                </label>
              </div>
              <!-- A resposta à pergunta do dono, visível: o fechamento da venda
                   LIGA o padrão sozinho (`_remember_fiscal_prefs` só liga);
                   desligar é gesto daqui. -->
              <p class="text-xs text-muted-foreground">Usar CPF ou e-mail numa venda liga o padrão sozinho; desligar é aqui.</p>
              <template v-if="hasCustomer">
                <label class="grid gap-1 text-sm">
                  <span class="text-xs font-medium text-muted-foreground">Restrições alimentares</span>
                  <UiInput v-model="profileDraft.dietary_restrictions" placeholder="Ex: alérgico a nozes" @blur="saveProfileText" />
                </label>
                <label class="grid gap-1 text-sm">
                  <span class="text-xs font-medium text-muted-foreground">Observações do balcão</span>
                  <UiTextarea v-model="profileDraft.notes" :rows="2" placeholder="Ex: prefere pão bem assado; busca às 17h" @blur="saveProfileText" />
                </label>
              </template>
              <p v-else class="text-xs text-muted-foreground">Restrições e observações ficam disponíveis depois de cadastrar.</p>
            </div>
          </div>
        </div>
      </div>

      <UiDialogFooter v-if="!isReceiptDecision">
        <UiButton class="h-14 w-full" :disabled="Boolean(customerDecision) || lookupBusy || concludePending" @click="onConclude">
          <Icon v-if="concludePending" name="lucide:loader-circle" class="mr-2 size-4 animate-spin" />
          {{ footerLabel }}
        </UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
