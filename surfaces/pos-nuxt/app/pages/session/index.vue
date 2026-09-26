<script setup lang="ts">
import type { ManagerAction } from "../../../../operator-kit/app/presentation/managerAuth";
// ANTESALA do PDV (benchmark Odoo POS): a tela de SESSÃO antes da venda. O
// operador abre o caixa (fundo de troco), registra sangria/suprimento e
// fecha o turno (contagem cega) aqui — não mais num diálogo espremido dentro da
// tela de venda. Sem turno aberto, a tela de venda redireciona para cá (com
// `?open=1`, e o diálogo de abertura já nasce aberto); com turno, o card
// "Continuar vendendo" leva de volta. BLIND: a antesala nunca mostra o valor
// esperado da gaveta — a conferência (esperado vs contado) fica na retaguarda.
// O fechamento do DIA (sobras/perdas) entra em `/session/closing`.
//
// TUDO É CARD (pedido do dono, 25/09/2026): cada opção da tela é um card que
// abre — um diálogo aqui mesmo, ou a página do fechamento/relatório. A
// organização (quais cards, em que ordem, com que destaque) é pura, em
// `presentation/cash`; a página só abre o que o card nomeia.
import { toast } from "vue-sonner";

import {
  amountInputError,
  amountToQ,
  attentionCount,
  attentionTiles,
  canRegisterMovement,
  canRequestChange,
  canSubmitCashAmount,
  changeDenominations,
  changeRequestSummary,
  endOfDayTiles,
  formatAmountInput,
  formatOpenedAt,
  formatRequestedAt,
  movementLabel,
  movementReasons,
  openShiftTile,
  sessionActionTiles,
  sessionScreenState,
} from "~/presentation/cash";
import type { SessionTile } from "~/presentation/cash";
import type { ManagerApproval } from "~/composables/usePosCashSession";
import type { DayClosingResponse } from "~/types/closing";

useHead({ title: "Sessão de caixa" });

const action = usePosAction();
const { pos, shift, actions, pending, refresh } = await usePosTerminal();

const OPERATOR_PERM = "cashman.operate_pos";
const { operator: activeOperator, lock } = useOperatorLock(OPERATOR_PERM);

const {
  busy,
  movementKinds,
  managerChallenge,
  openCashShift,
  closeCashShift,
  registerCashMovement,
  canOpenDrawer,
  drawerUnavailableReason,
  drawerProbing,
  openDrawerWithoutSale,
  probeDrawer,
  pendingChangeRequests,
  pendingCashRefunds,
  refundCash,
  accountBalances,
  settleAccount,
  requestChange,
  serveChangeRequest,
  cancelChangeRequest,
} = usePosCashSession({ pos, actions, refresh, action });

// Entrada do FECHAMENTO DO DIA (contagem cega de sobras): o gate é da API
// (`backstage.perform_closing`) — sondagem leve; 401/403 = card não aparece.
const { data: dayClosingData } = useFetch<DayClosingResponse>(
  "/api/v1/backstage/closing/",
  { key: "day-closing-entry", credentials: "include", lazy: true, server: false },
);
const dayClosing = computed(() => dayClosingData.value?.closing ?? null);

const screen = computed(() => {
  if (!pos.value) return "closed";
  return sessionScreenState(pos.value.cash_runtime, pos.value.has_open_cash_session);
});
const cashRuntime = computed(() => pos.value?.cash_runtime ?? null);
// Ausente vale `false`: contrato mudo não abre porta de dinheiro.
const canAuditCash = computed(() => cashRuntime.value?.can_audit_cash === true);

// Cada ato é um CARD, e o formulário (ou a lista) mora num diálogo que nasce
// recolhido. Ver o formulário é uma escolha, e a escolha é o que separa "abri a
// gaveta porque precisei" de "abri porque estava ali" — dois campos de dinheiro
// abertos o turno inteiro eram ruído em 99% das visitas e um toque errado no 1%
// restante. Nada some: cada um abre a um toque, e o card diz o que vai
// acontecer antes de o formulário aparecer.
const openShiftDialogOpen = ref(false);
const refundsDialogOpen = ref(false);
const changeRequestsDialogOpen = ref(false);
const accountsDialogOpen = ref(false);
const changeDialogOpen = ref(false);
const movementDialogOpen = ref(false);
const drawerDialogOpen = ref(false);
const closingDialogOpen = ref(false);
// A capability é a FONTE dos motivos de movimento e das denominações do troco.
// Repetir as listas em TypeScript seria assinar uma divergência para o dia em
// que uma moeda saísse de circulação.
const cashManagement = computed(() => pos.value?.checkout?.capabilities?.cash_management ?? null);
const openedAtDisplay = computed(() => formatOpenedAt(cashRuntime.value?.opened_at));
const salesCount = computed(() => shift.value?.count ?? 0);

// "Precisa de você": o que pede uma pessoa agora, contado para o cabeçalho.
// Zero = o bloco não existe; a antesala sem pendência é só status e ações.
const attention = computed(() => attentionCount({
  pendingCashRefunds: pendingCashRefunds.value,
  pendingChangeRequests: pendingChangeRequests.value,
  accountBalances: accountBalances.value,
}));

// Os cards de cada seção — as listas são puras; a página só abre o diálogo (ou
// navega) que o card nomeia.
const needsYouTiles = computed(() => attentionTiles({
  pendingCashRefunds: pendingCashRefunds.value,
  pendingChangeRequests: pendingChangeRequests.value,
  accountBalances: accountBalances.value,
}));
const actionTiles = computed(() => sessionActionTiles({
  movementKinds: movementKinds.value,
  canOpenDrawer: canOpenDrawer.value,
  drawerUnavailableReason: drawerUnavailableReason.value,
}));
const endOfDay = computed(() => endOfDayTiles({
  shiftOpen: screen.value === "open",
  justClosedShift: justClosedShift.value,
  canAuditCash: canAuditCash.value,
  dayClosing: dayClosing.value,
}));
// Fim de dia EM CURSO: acabou de fechar o caixa e o dia está por fechar. Aí o
// próximo passo sobe para o topo e o "Abrir caixa" deixa de ser o destaque.
const endOfDayInProgress = computed(() => endOfDay.value.some((t) => t.badge === "Próximo passo"));
const shiftTile = computed<SessionTile>(() => (screen.value === "closed"
  ? openShiftTile({
    floatSuggestionDisplay: floatSuggestionDisplay.value,
    endOfDayInProgress: endOfDayInProgress.value,
  })
  : {
    key: "continue_selling",
    icon: "lucide:shopping-basket",
    label: "Continuar vendendo",
    // ⚠️ `shift.count` conta o DIA INTEIRO do canal PDV: os dois balcões, os
    // turnos já fechados e o que o colega vendeu antes de você assumir. Ao
    // lado de "Aberto em" ele se lia como a contagem deste turno — e numa loja
    // de duas gavetas o operador nunca fechava com ela. O par honesto seria
    // "vendas neste turno" pelo `sales_count` da leitura X; enquanto ele não
    // sobe até aqui, a linha diz de quem é o número.
    description: `Turno aberto em ${openedAtDisplay.value} · ${salesCount.value} ${salesCount.value === 1 ? "venda" : "vendas"} hoje na loja`,
    disabled: false,
    tone: "primary",
  }));

function selectTile(tile: SessionTile) {
  if (tile.disabled) return;
  const key = tile.key;
  if (key === "open_shift") openShiftDialogOpen.value = true;
  else if (key === "continue_selling") void goToSaleBoard();
  else if (key === "attention:refunds") refundsDialogOpen.value = true;
  else if (key === "attention:change") changeRequestsDialogOpen.value = true;
  else if (key === "attention:accounts") accountsDialogOpen.value = true;
  else if (key === "request_change") changeDialogOpen.value = true;
  else if (key.startsWith("movement:")) openMovement(tile.kind || "");
  else if (key === "open_drawer") drawerDialogOpen.value = true;
  else if (key === "close_shift") closingDialogOpen.value = true;
  else if (key === "day_closing") void goToDayClosing();
  else if (key === "cash_report") void goToCashReport();
}

// A lista de pendência que zerou fecha o próprio diálogo: resolvida a última
// devolução, ficar olhando uma lista vazia é pedir um toque a mais para nada.
watch(() => pendingCashRefunds.value.length, (n) => { if (!n) refundsDialogOpen.value = false; });
watch(() => pendingChangeRequests.value.length, (n) => { if (!n) changeRequestsDialogOpen.value = false; });
watch(() => accountBalances.value.length, (n) => { if (!n) accountsDialogOpen.value = false; });

// O campo de valor nasce focado ao abrir o diálogo: tocar o tile já foi a
// decisão, digitar é o próximo gesto. O foco padrão do diálogo cairia no
// primeiro botão (o tipo, ou uma denominação), e a mão precisaria de um
// segundo alvo.
function focusOnOpen(event: Event, field: { inputRef: HTMLInputElement | null } | null) {
  event.preventDefault();
  void nextTick(() => field?.inputRef?.focus());
}
const changeAmountField = useTemplateRef<{ inputRef: HTMLInputElement | null }>("changeAmountField");
const openingAmountField = useTemplateRef<{ inputRef: HTMLInputElement | null }>("openingAmountField");
const closingAmountField = useTemplateRef<{ inputRef: HTMLInputElement | null }>("closingAmountField");

// ABERTURA GUIADA (pedido do dono): a antesala conduz. Quem chega pela venda
// sem turno (`?open=1`) já cai no diálogo, com o campo de valor focado; o
// placeholder sugere o fundo de troco que o GESTOR configurou no terminal, e
// Enter abre e segue para a venda. A sugestão é config fixa
// (`cash_runtime.default_float_q`) — nunca o contado de turnos, que vazaria o
// regime de contagem cega.
const openingAmount = ref("");
const openingError = computed(() => amountInputError(openingAmount.value));
const canOpen = computed(() => canSubmitCashAmount(openingAmount.value));
const floatSuggestionQ = computed(() => cashRuntime.value?.default_float_q || 0);
const floatSuggestionDisplay = computed(() => cashRuntime.value?.default_float_display || "");
const openingPlaceholder = computed(
  () => (floatSuggestionQ.value > 0 ? formatAmountInput(floatSuggestionQ.value) : "0,00"),
);
// A sugestão preenche a um toque, mas nunca sozinha: abrir o caixa com um
// número que ninguém digitou nem tocou seria default disfarçado de resposta.
function useFloatSuggestion() {
  if (floatSuggestionQ.value > 0) openingAmount.value = formatAmountInput(floatSuggestionQ.value);
}
// Contador por denominação (opcional) — o mesmo da contagem do fechamento.
const openingCounter = ref(false);
const route = useRoute();
onMounted(() => {
  if (route.query.open === "1" && screen.value === "closed") openShiftDialogOpen.value = true;
});

async function submitOpen() {
  const floatQ = amountToQ(openingAmount.value);
  if (floatQ === null) return;
  const ok = await openCashShift(openingAmount.value);
  if (ok) {
    // O toast repete o VALOR: é a última chance de pegar um dígito errado
    // antes de ele virar diferença no fechamento.
    toast.success(`Caixa aberto · fundo R$ ${formatAmountInput(floatQ)}`);
    openShiftDialogOpen.value = false;
    await navigateTo("/");
  }
}

async function goToSaleBoard() {
  await navigateTo("/");
}

async function goToCashReport() {
  await navigateTo("/session/report");
}

async function goToDayClosing() {
  await navigateTo("/session/closing");
}

// Tela do cliente: segunda janela do MESMO navegador, para arrastar ao monitor
// virado ao cliente. A abertura (e a sonda de versão que vai junto) mora no
// composable; a antessala e a venda chamam a MESMA peça, pelo rail.
const customerDisplayWindow = useCustomerDisplayWindow();
function openCustomerDisplay() {
  if (!customerDisplayWindow.open()) toast.error("O navegador bloqueou a Tela do Cliente.", {
    description: "Permita pop-ups para este site e tente novamente.",
  });
}

// Movimentos de gaveta: sangria (sai) / suprimento (entra).
//
// O motivo é obrigatório e vem em BOTÕES, como já acontece na abertura de gaveta
// ao lado. Motivo obrigatório só de digitar não sobrevive ao balcão: a fila anda,
// alguém escreve "sangria" no campo motivo, e a trilha fica com uma linha que
// repete o tipo e não conta nada. Com opções para tocar, o motivo responde o que
// a conferência vai perguntar depois — para onde o dinheiro foi.
const movementKind = ref("");
const movementAmount = ref("");
const movementError = computed(() => amountInputError(movementAmount.value));
// Escolher o tipo leva o foco direto ao valor: o toque no botão já respondeu a
// primeira pergunta, e a mão não deveria precisar de um segundo alvo.
const movementAmountField = useTemplateRef<{ inputRef: HTMLInputElement | null }>("movementAmountField");
// Escolhido e digitado são campos SEPARADOS, e um limpa o outro no ato: com um
// só, a tela mostraria dois motivos ao mesmo tempo e mandaria um deles calada.
const movementReasonPick = ref("");
const movementReasonOther = ref("");
const movementReasonOptions = computed(() => movementReasons(cashManagement.value, movementKind.value));
const movementReason = computed(() => movementReasonPick.value || movementReasonOther.value.trim());
const canSubmitMovement = computed(
  () => canRegisterMovement(movementKind.value, movementAmount.value, movementReason.value),
);

// Trocar de tipo zera o motivo: "Cofre" faz sentido numa sangria e nenhum num
// suprimento. Motivo herdado do tipo anterior entraria na trilha como mentira.
function pickMovementKind(kind: string) {
  movementKind.value = kind;
  clearMovementReason();
  void nextTick(() => movementAmountField.value?.inputRef?.focus());
}

// Saída e entrada são o MESMO diálogo com o tipo pré-escolhido pelo tile; o
// seletor de tipo continua dentro, para trocar. O título acompanha o tipo.
function openMovement(kind: string) {
  pickMovementKind(kind);
  movementDialogOpen.value = true;
}
const movementDialogTitle = computed(() => movementLabel(movementKind.value));

function pickMovementReason(reason: string) {
  movementReasonPick.value = reason;
  movementReasonOther.value = "";
}

function clearMovementReason() {
  movementReasonPick.value = "";
  movementReasonOther.value = "";
}

// Digitar desfaz o botão escolhido. O caminho inverso já está em
// `pickMovementReason`, e o "se tem texto" evita que a limpeza programática de lá
// volte para desmarcar o botão que acabou de ser escolhido.
watch(movementReasonOther, (typed) => {
  if (typed) movementReasonPick.value = "";
});
// Retirada de gaveta e atendimento de pedido de troco precisam da segunda
// assinatura: o servidor recusa com `manager_approval_required`, o diálogo sobe
// e a MESMA ação é reenviada com o PIN. O `managerChallenge` reabre o diálogo
// quando o PIN vem errado.
//
// Um diálogo só para as duas ações, e uma intenção dizendo qual reenviar: com
// dois diálogos, o PIN digitado num poderia reenviar a ação do outro — e nesse
// caso a assinatura gravada seria de uma coisa que o gerente não autorizou.
type ManagerIntent =
  | { action: "movement" }
  | { action: "serve_change"; ref: string }
  | { action: "refund_cash"; orderRef: string };
const managerIntent = ref<ManagerIntent>({ action: "movement" });
const managerAuthOpen = ref(false);
watch(managerChallenge, (challenge) => { if (challenge) managerAuthOpen.value = true; });

// A copy mora em `presentation/managerAuth`; aqui só se escolhe QUAL ato é.
const managerAuthAction = computed<ManagerAction>(() => {
  if (managerIntent.value.action === "serve_change") return "serve_change";
  if (managerIntent.value.action === "refund_cash") return "refund_cash";
  return "cash_out";
});

function onManagerAuthorize(username: string, pin: string) {
  autorizar({ username, pin });
}

// O crachá é a MESMA autorização, por outra porta: o servidor resolve a pessoa
// pelo token, exige a mesma `cashman.adjust_shift` e grava a mesma assinatura em
// `Entry.approved_by`. É a hora em que o gerente mais aparece no balcão, e era
// justamente onde o crachá dele não valia.
function onManagerBadge(badge: string) {
  autorizar({ badge });
}

function autorizar(aprovacao: { username?: string; pin?: string; badge?: string }) {
  managerAuthOpen.value = false;
  const intent = managerIntent.value;
  if (intent.action === "serve_change") serveChange(intent.ref, aprovacao);
  else if (intent.action === "refund_cash") refundPending(intent.orderRef, aprovacao);
  else submitMovement(aprovacao);
}

// Cancelar não é devolver: a venda cancelada (pelo gestor, de noite) deixa o
// dinheiro pendente até alguém com a gaveta aberta entregar. O PIN é do gerente
// porque dinheiro sai da gaveta, como na sangria.
async function refundPending(orderRef: string, managerApproval: ManagerApproval | null = null) {
  managerIntent.value = { action: "refund_cash", orderRef };
  const ok = await refundCash({ orderRef, managerApproval });
  if (ok) {
    managerChallenge.value = null;
    managerAuthOpen.value = false;
  }
}

// Conta na casa: o cliente veio acertar. Valor + método; em dinheiro entra neste
// turno (a gaveta abre para guardar), pix/cartão é atestado no balcão. Sem PIN:
// entrada não exige segunda assinatura (suprimento também não).
const settleCustomerRef = ref<string | null>(null);
const settleAmount = ref("");
const settleMethod = ref<"cash" | "pix" | "credit" | "debit" | "external">("cash");
function openSettle(customerRef: string, balanceQ: number) {
  settleCustomerRef.value = customerRef;
  settleAmount.value = (balanceQ / 100).toFixed(2).replace(".", ",");
  settleMethod.value = "cash";
}
async function submitSettle() {
  const customerRef = settleCustomerRef.value;
  if (!customerRef || !settleAmount.value.trim()) return;
  const ok = await settleAccount({ customerRef, amount: settleAmount.value.trim(), method: settleMethod.value });
  if (ok) settleCustomerRef.value = null;
}

async function submitMovement(managerApproval: ManagerApproval | null = null) {
  if (!canSubmitMovement.value) return;
  managerIntent.value = { action: "movement" };
  const ok = await registerCashMovement({
    kind: movementKind.value,
    amount: movementAmount.value,
    reason: movementReason.value,
    managerApproval,
  });
  if (ok) {
    managerChallenge.value = null;
    managerAuthOpen.value = false;
    movementAmount.value = "";
    clearMovementReason();
    movementDialogOpen.value = false;
  }
}

// Pedido de troco: o operador pede, alguém traz, e a troca acontece aqui no
// balcão, entre duas pessoas. Ninguém sai carregando dinheiro até o cofre.
//
// ⚠️ Nada disto é movimento de caixa. A troca é net zero (saem R$ 50, entram
// 5×R$ 10) e o esperado do fechamento não pode sentir nada.
const changeAmount = ref("");
const changeNote = ref("");
// As denominações marcadas, em centavos. Ordem de clique não importa: o servidor
// devolve ordenado do maior para o menor, que é como se conta dinheiro.
const changeDenominationsPicked = ref<number[]>([]);
const changeDenominationOptions = computed(() => changeDenominations(cashManagement.value));
const canSubmitChange = computed(() => canRequestChange(changeAmount.value));

function toggleDenomination(q: number) {
  const atuais = changeDenominationsPicked.value;
  changeDenominationsPicked.value = atuais.includes(q)
    ? atuais.filter((v) => v !== q)
    : [...atuais, q];
}

async function submitChangeRequest() {
  if (!canSubmitChange.value) return;
  const ok = await requestChange({
    amount: changeAmount.value,
    denominations: [...changeDenominationsPicked.value],
    note: changeNote.value,
  });
  if (ok) {
    changeAmount.value = "";
    changeDenominationsPicked.value = [];
    changeNote.value = "";
    changeDialogOpen.value = false;
  }
}

async function serveChange(ref_: string, managerApproval: ManagerApproval | null = null) {
  managerIntent.value = { action: "serve_change", ref: ref_ };
  const ok = await serveChangeRequest({ ref: ref_, managerApproval });
  if (ok) {
    managerChallenge.value = null;
    managerAuthOpen.value = false;
  }
}

// Cancelar descarta um pedido que o balcão ainda espera: confirma antes, e a
// confirmação é POR pedido — um "sim" genérico com dois pendentes na tela
// cancelaria o errado.
const cancellingChangeRef = ref("");
async function confirmCancelChange(ref_: string) {
  const ok = await cancelChangeRequest(ref_);
  if (ok) cancellingChangeRef.value = "";
}

// Abrir a gaveta sem venda. Um motivo é obrigatório porque este é o único dos
// quatro momentos que não deixa rastro sozinho — sem venda e sem movimento, a
// linha na trilha é tudo o que sobra. Os motivos comuns viram um toque; o
// digitado cobre o resto sem virar campo obrigatório no meio da fila.
const DRAWER_REASONS = ["Troco", "Conferência"] as const;
const drawerReason = ref("");
async function openDrawer(reason: string) {
  const chosen = reason.trim();
  if (!chosen) return;
  const ok = await openDrawerWithoutSale(chosen);
  if (ok) {
    drawerReason.value = "";
    drawerDialogOpen.value = false;
  }
}

// Teste de gaveta: a sonda só alcança a FILA do sistema. Se a gaveta está
// plugada na impressora, ou se abriu, quem confirma é o olho do operador.
const drawerProbeResult = ref<{ ok: boolean; message: string } | null>(null);
async function testDrawer() {
  drawerProbeResult.value = await probeDrawer();
  if (drawerProbeResult.value.ok) await openDrawerWithoutSale("Teste de gaveta");
}

// Fechar caixa (contagem cega) — destrutivo, exige confirmação explícita.
//
// O CTA só arma com um valor LEGÍVEL (zero incluso: gaveta esvaziada é
// contagem de verdade). Campo vazio virava "0" calado — o turno fechava com
// uma contagem que ninguém fez. E a confirmação ECOA o valor: é a última
// leitura antes de ele virar a única verdade do operador no livro.
const closingAmount = ref("");
const closingNotes = ref("");
const closingError = computed(() => amountInputError(closingAmount.value));
const canClose = computed(() => canSubmitCashAmount(closingAmount.value));
const closingEchoDisplay = computed(() => {
  const q = amountToQ(closingAmount.value);
  return q === null ? "" : formatAmountInput(q);
});
// Contador por denominação (opcional): qtd × cédula/moeda, soma ao vivo
// preenchendo o campo — para quem conta nota por nota.
const closingCounter = ref(false);
const confirmingClose = ref(false);
// Fechar o diálogo no meio da confirmação desarma a confirmação, e só ela: o
// valor contado e as observações ficam, para quem foi só espiar a gaveta
// não digitar tudo de novo — mas reabrir não pode cair direto no "Confirmar".
watch(closingDialogOpen, (open) => { if (!open) confirmingClose.value = false; });
// O fim de dia se ENCADEIA: fechado o caixa, a antesala oferece o próximo
// passo (fechamento do dia, se pendente e permitido) em vez de deixar o
// operador adivinhar que existem mais duas telas.
const justClosedShift = ref(false);
async function confirmClose() {
  if (!canClose.value) return;
  const ok = await closeCashShift({ amount: closingAmount.value, notes: closingNotes.value });
  confirmingClose.value = false;
  if (ok) {
    closingAmount.value = "";
    closingNotes.value = "";
    closingDialogOpen.value = false;
    closingCounter.value = false;
    justClosedShift.value = true;
  }
}

</script>

<template>
  <main class="flex flex-wrap content-start min-h-dvh bg-background text-foreground md:h-[100dvh] md:min-h-0 md:flex-nowrap md:overflow-hidden">
    <PosFunctionRail
      v-if="pos"
      :pos="pos"
      :has-open-cash-session="pos.has_open_cash_session"
      :operator-name="activeOperator?.name || ''"
      :pending="pending"
      view="session"
      @board="goToSaleBoard"
      @cash="() => {}"
      @display="openCustomerDisplay"
      @lock="lock()"
      @refresh="refresh()"
    />

    <div class="flex min-w-0 flex-1 flex-col md:min-h-0 md:overflow-hidden">
      <header class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2">
        <RailToggle />
        <h1 class="min-w-0 truncate text-lg font-semibold">Sessão de caixa</h1>
        <span v-if="pos" class="ml-auto truncate text-sm text-muted-foreground">
          {{ pos.terminal_label || "Terminal" }}
          <template v-if="screen === 'open'"> · {{ activeOperator?.name || cashRuntime?.operator_username }}</template>
        </span>
      </header>

      <div class="flex-1 md:min-h-0 md:overflow-y-auto">
        <!-- TUDO É CARD: quatro seções, cada uma uma grade de cards que abrem.
             A ordem é a do balcão — o gesto óbvio, o que pede gente, a gaveta,
             o fim do expediente — e o fim de dia EM CURSO (acabou de fechar o
             caixa, dia por fechar) sobe para o topo: `order-first`. As
             Encomendas não moram aqui: a porta delas é a barra lateral. -->
        <div class="mx-auto grid w-full max-w-2xl gap-6 p-4 md:py-8">
          <p
            v-if="screen === 'closed' && justClosedShift"
            class="order-first flex items-start gap-2 rounded-md border border-success/30 bg-success/10 px-3 py-2 text-sm"
            data-shift-closed
          >
            <Icon name="lucide:circle-check" class="mt-0.5 size-4 shrink-0 text-success" />
            <span>Caixa fechado. A contagem ficou registrada no turno; a conferência é da retaguarda.</span>
          </p>

          <!-- CAIXA: fechado, abrir; aberto, continuar vendendo. O card É o
               gesto óbvio da tela, e por isso é o cheio. -->
          <section class="grid gap-3" aria-labelledby="shift-title">
            <h2 id="shift-title" class="text-base font-semibold">Caixa</h2>
            <ul class="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <li class="col-span-2 sm:col-span-3">
                <PosSessionTile :tile="shiftTile" @select="selectTile" />
              </li>
            </ul>
          </section>

          <!-- PRECISA DE VOCÊ: só existe com pendência, um card por natureza,
               cada um com o SEU número. ⚠️ Sem crachá único: devolução em
               dinheiro (gaveta aberta, PIN de gerente), pedido de troco (alguém
               traz cédulas) e conta na casa (saldo que pode esperar a semana)
               são três urgências, e "4 pendências" decidia se o operador
               largava o balcão sem dizer para quê. -->
          <section
            v-if="screen === 'open' && attention"
            class="grid gap-3"
            data-needs-you
            aria-labelledby="needs-you-title"
          >
            <div class="flex items-center gap-2">
              <Icon name="lucide:bell-ring" class="size-4 text-warning" />
              <h2 id="needs-you-title" class="text-base font-semibold">Precisa de você</h2>
            </div>
            <ul class="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <li v-for="tile in needsYouTiles" :key="tile.key">
                <PosSessionTile :tile="tile" @select="selectTile" />
              </li>
            </ul>
          </section>

          <!-- GAVETA. ABRIR GAVETA É EXCEÇÃO: segue a um toque, com motivo e
               registro, mas não fica em exposição — é o buraco que a chave
               física deixava. Sem caminho de software o card DIZ por que, em
               vez de sumir. -->
          <section v-if="screen === 'open'" class="grid gap-3" aria-labelledby="drawer-actions-title">
            <h2 id="drawer-actions-title" class="text-base font-semibold">Gaveta</h2>
            <ul class="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <li v-for="tile in actionTiles" :key="tile.key">
                <PosSessionTile :tile="tile" @select="selectTile" />
              </li>
            </ul>
          </section>

          <!-- FIM DO EXPEDIENTE: fechar caixa → fechamento do dia → relatório.
               O relatório é de quem AUDITA (`cashman.audit_shift`), o
               fechamento do dia de quem a API deixou entrar; o servidor recusa
               por conta própria, isto só evita oferecer porta que vai bater na
               cara. -->
          <section
            v-if="endOfDay.length"
            class="grid gap-3"
            :class="endOfDayInProgress ? 'order-first' : ''"
            aria-labelledby="end-of-day-title"
          >
            <h2 id="end-of-day-title" class="text-base font-semibold">Fim do expediente</h2>
            <ul class="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <li v-for="tile in endOfDay" :key="tile.key">
                <PosSessionTile :tile="tile" @select="selectTile" />
              </li>
            </ul>
          </section>
        </div>
      </div>
    </div>

    <!-- ── Diálogos, um por card ───────────────────────────────────────────
         O PIN do gerente (`OperatorManagerAuth`, no fim) sobe por cima do
         diálogo aberto; o formulário digitado fica. -->

    <!-- Abrir caixa: o campo nasce focado e Enter abre — a antesala conduz, o
         operador só responde quanto tem na mão. -->
    <UiDialog v-model:open="openShiftDialogOpen">
      <UiDialogContent
        class="max-h-[85vh] overflow-y-auto sm:max-w-lg"
        data-session-dialog="open_shift"
        @open-auto-focus="focusOnOpen($event, openingAmountField)"
      >
        <UiDialogHeader>
          <div class="flex items-center gap-2">
            <Icon name="lucide:wallet" class="size-4 text-muted-foreground" />
            <UiDialogTitle>Abrir caixa</UiDialogTitle>
          </div>
          <UiDialogDescription>Conte o dinheiro da gaveta e informe o fundo de troco.</UiDialogDescription>
        </UiDialogHeader>
        <label class="grid gap-1 text-sm">
          <span class="font-medium text-muted-foreground">Fundo de troco</span>
          <UiInput
            ref="openingAmountField"
            v-model="openingAmount"
            inputmode="decimal"
            class="h-12 text-right text-lg tabular-nums"
            :placeholder="openingPlaceholder"
            :aria-invalid="openingError ? 'true' : undefined"
            @keydown.enter="submitOpen"
          />
        </label>
        <p v-if="openingError" class="text-xs text-destructive">{{ openingError }}</p>
        <!-- A sugestão preenche a UM toque, mas nunca sozinha: o botão diz o
             valor, e tocá-lo é o operador afirmando que é isso que tem na
             gaveta. -->
        <div class="flex flex-wrap gap-2">
          <UiButton
            v-if="floatSuggestionDisplay && !openingAmount"
            variant="outline"
            size="sm"
            data-float-suggestion
            @click="useFloatSuggestion"
          >
            <Icon name="lucide:check" class="size-4" />
            Está certo: {{ floatSuggestionDisplay }}
          </UiButton>
          <UiButton v-if="!openingCounter" variant="ghost" size="sm" @click="openingCounter = true">
            <Icon name="lucide:calculator" class="size-4" />
            Contar por cédulas e moedas
          </UiButton>
        </div>
        <PosDenominationCounter
          v-if="openingCounter"
          :denominations="changeDenominationOptions"
          :disabled="busy"
          @total-q="openingAmount = formatAmountInput($event)"
        />
        <UiButton size="lg" :disabled="busy || !canOpen" :loading="busy" @click="submitOpen">
          <Icon name="lucide:wallet" class="size-5" />
          Abrir caixa e vender
        </UiButton>
      </UiDialogContent>
    </UiDialog>

    <!-- Devoluções em dinheiro. Cancelar não é devolver: o gestor cancela de
         noite e ninguém abriu gaveta; a devolução fica aqui até quem está com a
         gaveta aberta entregar as notas. Só então Payman e livro registram. -->
    <UiDialog v-model:open="refundsDialogOpen">
      <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-lg" data-session-dialog="attention:refunds">
        <UiDialogHeader>
          <div class="flex items-center gap-2">
            <Icon name="lucide:rotate-ccw" class="size-4 text-muted-foreground" />
            <UiDialogTitle>Devoluções em dinheiro</UiDialogTitle>
          </div>
          <UiDialogDescription>Entregue o dinheiro ao cliente e toque em Devolver.</UiDialogDescription>
        </UiDialogHeader>
        <ul class="grid gap-2" aria-label="Devoluções em dinheiro pendentes">
          <li
            v-for="refund in pendingCashRefunds"
            :key="refund.order_ref"
            class="grid gap-2 rounded-md border bg-muted/30 p-3"
          >
            <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span class="text-sm font-medium tabular-nums">{{ refund.amount_display }}</span>
              <span class="text-xs text-muted-foreground">
                pedido {{ refund.order_ref }}<template v-if="refund.customer_name"> · {{ refund.customer_name }}</template>
              </span>
            </div>
            <UiButton size="sm" :disabled="busy" @click="refundPending(refund.order_ref)">
              <Icon name="lucide:hand-coins" class="size-4" />
              Devolver
            </UiButton>
          </li>
        </ul>
        <p class="text-xs text-muted-foreground">
          O dinheiro sai desta gaveta e fica registrado no turno. Um gerente autoriza com o PIN.
        </p>
      </UiDialogContent>
    </UiDialog>

    <!-- Pedidos de troco à espera: é aqui que a troca acontece, entre duas
         pessoas no balcão. O PEDIR mora no card "Pedir troco", da Gaveta. -->
    <UiDialog v-model:open="changeRequestsDialogOpen">
      <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-lg" data-session-dialog="attention:change">
        <UiDialogHeader>
          <div class="flex items-center gap-2">
            <Icon name="lucide:coins" class="size-4 text-muted-foreground" />
            <UiDialogTitle>Pedidos de troco</UiDialogTitle>
          </div>
          <UiDialogDescription>Chegou o troco? Atenda: o gerente autoriza aqui mesmo.</UiDialogDescription>
        </UiDialogHeader>
        <ul class="grid gap-2" aria-label="Pedidos de troco pendentes">
          <li
            v-for="request in pendingChangeRequests"
            :key="request.ref"
            class="grid gap-2 rounded-md border bg-muted/30 p-3"
          >
            <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
              <span class="text-sm font-medium">{{ changeRequestSummary(request, cashManagement) }}</span>
              <span class="text-xs text-muted-foreground">
                {{ request.requested_by }}<template v-if="formatRequestedAt(request.requested_at)"> · {{ formatRequestedAt(request.requested_at) }}</template>
              </span>
            </div>
            <p v-if="request.note" class="text-xs text-muted-foreground">{{ request.note }}</p>

            <div v-if="cancellingChangeRef !== request.ref" class="grid grid-cols-2 gap-2">
              <UiButton size="sm" :disabled="busy" @click="serveChange(request.ref)">
                <Icon name="lucide:hand-coins" class="size-4" />
                Atender
              </UiButton>
              <UiButton
                variant="outline"
                size="sm"
                :disabled="busy"
                @click="cancellingChangeRef = request.ref"
              >
                Cancelar pedido
              </UiButton>
            </div>
            <div v-else class="grid gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3">
              <p class="text-sm font-medium">Cancelar este pedido? Ninguém vai trazer o troco.</p>
              <div class="grid grid-cols-2 gap-2">
                <UiButton variant="outline" size="sm" :disabled="busy" @click="cancellingChangeRef = ''">
                  Voltar
                </UiButton>
                <UiButton
                  variant="destructive"
                  size="sm"
                  :disabled="busy"
                  :loading="busy"
                  @click="confirmCancelChange(request.ref)"
                >
                  Confirmar
                </UiButton>
              </div>
            </div>
          </li>
        </ul>
      </UiDialogContent>
    </UiDialog>

    <!-- Conta na casa: quem deve quanto, e o acerto. Em dinheiro entra neste
         turno (a gaveta abre para guardar); pix/cartão é atestado no balcão.
         Sem PIN: entrada não exige segunda assinatura. -->
    <UiDialog v-model:open="accountsDialogOpen">
      <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-lg" data-session-dialog="attention:accounts">
        <UiDialogHeader>
          <div class="flex items-center gap-2">
            <Icon name="lucide:book-user" class="size-4 text-muted-foreground" />
            <UiDialogTitle>Contas na casa</UiDialogTitle>
          </div>
          <UiDialogDescription>O cliente veio acertar? Toque em Receber acerto na conta certa.</UiDialogDescription>
        </UiDialogHeader>
        <div data-house-accounts>
          <ul class="grid gap-2" aria-label="Contas na casa com saldo em aberto">
            <li
              v-for="account in accountBalances"
              :key="account.customer_ref"
              class="grid gap-2 rounded-md border bg-muted/30 p-3"
            >
              <div class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span class="text-sm font-medium">{{ account.customer_name }}</span>
                <span class="text-sm tabular-nums">{{ account.balance_display }}</span>
                <span class="text-xs text-muted-foreground">
                  <!-- ⚠️ `account.intents` conta PaymentIntent, não
                       pedido: uma venda paga metade em dinheiro e metade
                       em conta gera um; duas idas à padaria podem virar
                       três. O relatório de caixa já separa "Vendas"
                       (order_ref distintos) de "Pagamentos" (intents) —
                       a palavra certa para este número já existia no
                       app, e não era esta. -->
                  {{ account.intents }} {{ account.intents === 1 ? "cobrança" : "cobranças" }} em aberto
                </span>
              </div>
              <template v-if="settleCustomerRef === account.customer_ref">
                <div class="grid gap-2 sm:grid-cols-[1fr_auto_auto] sm:items-end">
                  <label class="grid gap-1.5 text-sm">
                    <span class="font-medium text-muted-foreground">Recebido</span>
                    <UiInput
                      v-model="settleAmount"
                      inputmode="decimal"
                      placeholder="0,00"
                      class="text-right tabular-nums"
                      aria-label="Valor recebido no acerto"
                      @keydown.enter="submitSettle"
                    />
                  </label>
                  <label class="grid gap-1.5 text-sm">
                    <span class="font-medium text-muted-foreground">Como</span>
                    <UiNativeSelect v-model="settleMethod" aria-label="Método do acerto">
                      <option value="cash">Dinheiro</option>
                      <option value="pix">Pix</option>
                      <option value="credit">Crédito</option>
                      <option value="debit">Débito</option>
                      <option value="external">Outro</option>
                    </UiNativeSelect>
                  </label>
                  <div class="flex gap-2">
                    <UiButton size="sm" variant="outline" :disabled="busy" @click="settleCustomerRef = null">Cancelar</UiButton>
                    <UiButton size="sm" :disabled="busy || !settleAmount.trim()" @click="submitSettle">
                      <Icon name="lucide:check" class="size-4" />
                      Receber
                    </UiButton>
                  </div>
                </div>
                <p class="text-xs text-muted-foreground">
                  O acerto é por venda inteira, da mais antiga para a mais nova; o que não couber fica em aberto.
                </p>
              </template>
              <UiButton v-else size="sm" :disabled="busy" @click="openSettle(account.customer_ref, account.balance_q)">
                <Icon name="lucide:hand-coins" class="size-4" />
                Receber acerto
              </UiButton>
            </li>
          </ul>
        </div>
      </UiDialogContent>
    </UiDialog>

      <!-- Pedir troco: o dinheiro fica no balcão, o troco vem até ele.
           Antes o operador atravessava a loja até o cofre com dinheiro na
           mão; agora ele pede, alguém traz, e a troca acontece aqui, à
           vista das duas pessoas. Trocar não muda o total da gaveta. -->
      <UiDialog v-model:open="changeDialogOpen">
        <UiDialogContent
          class="max-h-[85vh] overflow-y-auto sm:max-w-lg"
          data-session-dialog="request_change"
          @open-auto-focus="focusOnOpen($event, changeAmountField)"
        >
          <UiDialogHeader>
            <div class="flex items-center gap-2">
              <Icon name="lucide:coins" class="size-4 text-muted-foreground" />
              <UiDialogTitle>Pedido de troco</UiDialogTitle>
            </div>
            <UiDialogDescription>
              Peça o troco em vez de sair do balcão com dinheiro. Um gerente traz e autoriza aqui mesmo.
            </UiDialogDescription>
          </UiDialogHeader>

          <!-- O VALOR primeiro, e exato. É a pergunta que quem vai ao cofre
               precisa respondida antes de sair andando. -->
          <label class="grid gap-1.5 text-sm">
            <span class="font-medium text-muted-foreground">Quanto</span>
            <UiInput
              ref="changeAmountField"
              v-model="changeAmount"
              inputmode="decimal"
              placeholder="0,00"
              class="text-right tabular-nums"
              @keydown.enter="submitChangeRequest"
            />
          </label>

          <!-- EM QUÊ. Cédula é retangular e verde, moeda é redonda e amarela,
               porque é assim que a mão reconhece no balcão sem parar para
               ler. Várias podem ser marcadas: "R$ 100 em notas de 5 e moedas
               de 0,50" é uma frase que se diz de verdade.

               Nada aqui é obrigatório: "me traz R$ 100" já é um pedido
               inteiro, e o gerente resolve com o que houver no cofre. -->
          <div class="grid gap-1.5">
            <span id="change-denom-label" class="text-sm font-medium text-muted-foreground">
              Em quê <span class="font-normal">(opcional)</span>
            </span>
            <div class="flex flex-wrap gap-2" role="group" aria-labelledby="change-denom-label">
              <button
                v-for="denom in changeDenominationOptions"
                :key="denom.q"
                type="button"
                :aria-pressed="changeDenominationsPicked.includes(denom.q)"
                :aria-label="`${denom.shape === 'note' ? 'Nota' : 'Moeda'} de ${denom.label}`"
                class="inline-flex items-center justify-center border text-sm font-semibold tabular-nums transition-colors disabled:opacity-50"
                :class="[
                  // Cédula é retangular, moeda é redonda — o desenho é a
                  // informação, e a mão acha antes do olho ler.
                  denom.shape === 'note' ? 'h-12 rounded-md px-4' : 'size-12 rounded-full',
                  denom.shape === 'note'
                    ? 'border-success/40 bg-success/10 text-success'
                    : 'border-warning/40 bg-warning/10 text-warning',
                  // Marcado é um ANEL, não um tom mais escuro: sob a luz do
                  // balcão dois tons da mesma cor viram um só, e o operador
                  // não saberia dizer o que pediu.
                  changeDenominationsPicked.includes(denom.q)
                    ? (denom.shape === 'note' ? 'ring-2 ring-success' : 'ring-2 ring-warning')
                    : '',
                ]"
                :disabled="busy"
                @click="toggleDenomination(denom.q)"
              >
                {{ denom.label }}
              </button>
            </div>
          </div>

          <UiInput
            v-model="changeNote"
            aria-label="Observação do pedido"
            placeholder="Observação (opcional)"
            @keydown.enter="submitChangeRequest"
          />

          <UiButton
            :disabled="busy || !canSubmitChange"
            @click="submitChangeRequest"
          >
            Preciso de troco
          </UiButton>

          <!-- Honestidade: o registro é trilha e dado, não um recado
               entregue. Ninguém está de olho numa tela de alertas aqui. -->
          <p class="flex items-start gap-2 text-xs text-muted-foreground">
            <Icon name="lucide:megaphone" class="mt-0.5 size-4 shrink-0" />
            <span>O pedido fica registrado no turno. Avise em voz alta também.</span>
          </p>
        </UiDialogContent>
      </UiDialog>

      <!-- Movimento de caixa: saída (sangria) / entrada (suprimento). Um
           diálogo para os dois, com o tipo que o tile escolheu e o seletor
           dentro, para trocar. -->
      <UiDialog v-model:open="movementDialogOpen">
        <UiDialogContent
          class="max-h-[85vh] overflow-y-auto sm:max-w-lg"
          data-session-dialog="movement"
          @open-auto-focus="focusOnOpen($event, movementAmountField)"
        >
          <UiDialogHeader>
            <UiDialogTitle>{{ movementDialogTitle }}</UiDialogTitle>
            <UiDialogDescription>Movimento de caixa</UiDialogDescription>
          </UiDialogHeader>
          <div class="grid gap-1.5">
            <span id="movement-kind-label" class="text-sm font-medium text-muted-foreground">Tipo</span>
            <div class="grid grid-cols-2 gap-2" role="group" aria-labelledby="movement-kind-label">
              <UiButton
                v-for="kind in movementKinds"
                :key="kind"
                variant="outline"
                size="sm"
                :aria-pressed="movementKind === kind"
                :class="movementKind === kind ? 'border-primary bg-primary/5' : ''"
                @click="pickMovementKind(kind)"
              >
                {{ movementLabel(kind) }}
              </UiButton>
            </div>
          </div>
          <label class="grid gap-1.5 text-sm">
            <span class="font-medium text-muted-foreground">Valor</span>
            <UiInput
              ref="movementAmountField"
              v-model="movementAmount"
              inputmode="decimal"
              placeholder="0,00"
              :aria-invalid="movementError ? 'true' : undefined"
            />
          </label>
          <p v-if="movementError" class="text-xs text-destructive">{{ movementError }}</p>

          <!-- Motivo obrigatório, em botões. O digitado fica como saída para o
               que não estava previsto, e é o único caminho quando o tipo não
               tem opções conhecidas. -->
          <div v-if="movementKind" class="grid gap-1.5">
            <span id="movement-reason-label" class="text-sm font-medium text-muted-foreground">
              {{ movementKind === "sangria" ? "Motivo (obrigatório)" : "Observação (opcional)" }}
            </span>
            <div
              v-if="movementReasonOptions.length"
              class="grid grid-cols-2 gap-2"
              role="group"
              aria-labelledby="movement-reason-label"
            >
              <UiButton
                v-for="reason in movementReasonOptions"
                :key="reason"
                variant="outline"
                size="sm"
                :aria-pressed="movementReasonPick === reason"
                :class="movementReasonPick === reason ? 'border-primary bg-primary/5' : ''"
                @click="pickMovementReason(reason)"
              >
                {{ reason }}
              </UiButton>
            </div>
            <UiInput
              v-model="movementReasonOther"
              :aria-label="movementReasonOptions.length ? 'Outro motivo' : 'Motivo'"
              :placeholder="movementReasonOptions.length ? 'Outro motivo' : 'Motivo'"
            />
          </div>

          <p v-if="movementKind === 'sangria'" class="flex items-start gap-2 text-xs text-muted-foreground">
            <Icon name="lucide:shield-check" class="mt-0.5 size-4 shrink-0" />
            <span>Tirar dinheiro da gaveta precisa da autorização de um gerente.</span>
          </p>
          <UiButton
            :disabled="busy || !canSubmitMovement"
            @click="submitMovement()"
          >
            Registrar movimento
          </UiButton>
        </UiDialogContent>
      </UiDialog>

      <!-- Abrir a gaveta sem venda: motivo obrigatório, porque é o único
           dos quatro momentos que não deixa rastro sozinho. -->
      <UiDialog v-model:open="drawerDialogOpen">
        <UiDialogContent class="max-h-[85vh] overflow-y-auto sm:max-w-lg" data-session-dialog="open_drawer">
          <UiDialogHeader>
            <div class="flex items-center gap-2">
              <Icon name="lucide:archive" class="size-4 text-muted-foreground" />
              <UiDialogTitle>Abrir gaveta</UiDialogTitle>
            </div>
            <UiDialogDescription>
              Abrir sem venda fica registrado no turno: quem abriu, quando e por quê.
            </UiDialogDescription>
          </UiDialogHeader>
          <div class="grid grid-cols-2 gap-2">
            <UiButton
              v-for="reason in DRAWER_REASONS"
              :key="reason"
              variant="outline"
              size="sm"
              :disabled="busy"
              @click="openDrawer(reason)"
            >
              {{ reason }}
            </UiButton>
          </div>
          <div class="grid grid-cols-[1fr_auto] gap-2">
            <UiInput v-model="drawerReason" placeholder="Outro motivo" @keydown.enter="openDrawer(drawerReason)" />
            <UiButton variant="outline" size="sm" :disabled="busy || !drawerReason.trim()" @click="openDrawer(drawerReason)">
              Abrir
            </UiButton>
          </div>
          <div class="mt-1 grid gap-2 border-t pt-3">
            <!-- ⚠️ A sonda ABRE a gaveta e registra a abertura no turno
                 (`drawer_open`, motivo "Teste de gaveta"), como qualquer
                 abertura sem venda. "Testar" prometia gesto sem
                 consequência, e quem testava três vezes deixava três
                 aberturas no relatório do dia sem saber. -->
            <UiButton variant="ghost" size="sm" :disabled="busy || drawerProbing" :loading="drawerProbing" @click="testDrawer">
              <Icon name="lucide:stethoscope" class="size-4" />
              Abrir para testar
            </UiButton>
            <p class="text-xs text-muted-foreground">
              Abre a gaveta e fica registrado no turno, como qualquer abertura sem venda.
            </p>
            <p v-if="drawerProbeResult" class="text-xs" :class="drawerProbeResult.ok ? 'text-muted-foreground' : 'text-destructive'">
              <template v-if="drawerProbeResult.ok">
                {{ drawerProbeResult.message }} A gaveta abriu? Se não abriu, confira o cabo dela na impressora.
              </template>
              <template v-else>{{ drawerProbeResult.message }}</template>
            </p>
          </div>
        </UiDialogContent>
      </UiDialog>

      <!-- Fechar caixa (contagem cega) — destrutivo; a confirmação com o
           eco do valor continua aqui dentro. -->
      <UiDialog v-model:open="closingDialogOpen">
        <UiDialogContent
          class="max-h-[85vh] overflow-y-auto sm:max-w-lg"
          data-session-dialog="close_shift"
          @open-auto-focus="focusOnOpen($event, closingAmountField)"
        >
          <UiDialogHeader>
            <UiDialogTitle>Fechar caixa</UiDialogTitle>
            <!-- O aviso da contagem cega É a descrição do diálogo: o
                 leitor de tela lê antes do campo, como o olho. -->
            <UiDialogDescription class="flex items-start gap-2 rounded-md border bg-muted/30 px-3 py-2 text-left text-xs">
              <Icon name="lucide:eye-off" class="mt-0.5 size-4 shrink-0" />
              <span>Contagem cega: conte o dinheiro do caixa e informe o valor. A conferência fica no gestor.</span>
            </UiDialogDescription>
          </UiDialogHeader>
          <label class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">Valor contado</span>
            <!-- Nasce focado: abrir o diálogo já foi a decisão, contar é
                 o próximo gesto. -->
            <UiInput
              ref="closingAmountField"
              v-model="closingAmount"
              inputmode="decimal"
              autofocus
              placeholder="0,00"
              :aria-invalid="closingError ? 'true' : undefined"
            />
          </label>
          <p v-if="closingError" class="text-xs text-destructive">{{ closingError }}</p>
          <UiButton
            v-if="!closingCounter"
            variant="ghost"
            size="sm"
            class="justify-self-start"
            @click="closingCounter = true"
          >
            <Icon name="lucide:calculator" class="size-4" />
            Contar por cédulas e moedas
          </UiButton>
          <PosDenominationCounter
            v-if="closingCounter"
            :denominations="changeDenominationOptions"
            :disabled="busy"
            @total-q="closingAmount = formatAmountInput($event)"
          />
          <label class="grid gap-1 text-sm">
            <span class="font-medium text-muted-foreground">Observações</span>
            <UiTextarea v-model="closingNotes" :rows="2" placeholder="Conferência, divergências" />
          </label>
          <div v-if="!confirmingClose">
            <!-- Só arma com um valor legível — vazio virava "0" calado, e o
                 turno fechava com uma contagem que ninguém fez. -->
            <!-- ⚠️ Este botão NÃO fecha: ele arma a confirmação. O
                 tile lá fora já se chama "Fechar caixa" (porta com nome
                 do destino); repetir o verbo do ato aqui ensinava a
                 apertar no automático, e quem encerrava o turno dizia a
                 palavra mais vaga da sequência ("Confirmar"). -->
            <UiButton variant="destructive" class="w-full" :disabled="busy || !canClose" @click="confirmingClose = true">
              Conferir e fechar
            </UiButton>
          </div>
          <div v-else class="grid gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3">
            <!-- O eco do valor: a última leitura antes de a contagem virar
                 a única palavra do operador no livro. -->
            <p class="text-sm font-medium">
              Confirmar fechamento do caixa? Contado: R$ {{ closingEchoDisplay }}. Esta ação encerra o turno.
            </p>
            <div class="grid grid-cols-2 gap-2">
              <UiButton variant="outline" :disabled="busy" @click="confirmingClose = false">Cancelar</UiButton>
              <!-- O degrau que PRATICA o ato é o único que o diz. -->
              <UiButton variant="destructive" :disabled="busy" :loading="busy" @click="confirmClose">
                Fechar o caixa
              </UiButton>
            </div>
          </div>
        </UiDialogContent>
      </UiDialog>

    <OperatorManagerAuth
      v-model:open="managerAuthOpen"
      :action="managerAuthAction"
      :operator-name="activeOperator?.name || ''"
      :managers="pos?.managers || []"
      :busy="busy"
      :error="managerChallenge?.code === 'manager_approval_invalid' ? managerChallenge.message : ''"
      @authorize="onManagerAuthorize"
      @authorize-badge="onManagerBadge"
    />
  </main>
</template>
