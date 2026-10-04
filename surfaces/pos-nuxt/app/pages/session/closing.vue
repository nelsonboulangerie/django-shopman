<script setup lang="ts">
// FECHAMENTO DO DIA na antesala (WP-ADM-2): a contagem cega de sobras/perdas
// sai do Admin/Unfold para o ritual de fim de dia do PDV, ao lado do fechar
// caixa. Mesma projection e mesmo service da retaguarda (GET/POST
// /api/v1/backstage/closing/), gate `backstage.perform_closing` (Gerente).
// Rótulo visível de sobra aproveitável = "Ontem".
//
// ⚠️ A TELA TEM DOIS MOMENTOS, e a ordem é a regra:
//
//   ANTES da contagem — só o que se conta e o que IMPEDE fechar.
//   DEPOIS de registrada — o quadro do dia inteiro.
//
// A tela nasceu em paridade com o Admin e mostrava "Produção do dia"
// (planejado/feito/perda por SKU) e "Discrepâncias" (disponível por SKU) ACIMA
// dos campos de contagem. Isso é o gabarito em cima da prova: feito menos
// vendido é a resposta que o operador deveria descobrir contando. Uma contagem
// com o número na tela não é cega, é confirmação — e o fechamento às cegas
// existe justamente para pegar o que a conta não pega.
//
// Produção pendente é a exceção parcial, porque é BLOQUEIO: ordem aberta tem
// que ser resolvida antes de encerrar. Antes da contagem ela aparece como
// aviso e contagem de ordens, sem SKU e sem quantidade; a tabela inteira volta
// depois.
//
// ⚠️ SÓ SE CONTA O QUE A CASA PRODUZ (decisão do dono, 25/09/2026). A lista
// vem filtrada do servidor (ficha ativa); revenda não entra, porque não vence
// de um dia para o outro e o estoque dela anda pela venda e pelo recebimento.
//
// A contagem é um corredor: ordem do NOME (é o que está na etiqueta), Enter
// leva ao próximo campo, o progresso diz quanto falta, e o botão de registrar
// fica preso ao pé da tela — contar trinta itens não pode terminar numa
// rolagem à procura do botão.
import {
  allQuantitiesFilled,
  buildQuantitiesPayload,
  closingBadge,
  closingCountOrder,
  closingCountSummary,
  closingSteps,
  countedItems,
  firstUnfilledItemName,
  pendingStatusDisplay,
  piecesLabel,
  productionRows,
  sanitizeQtyInput,
} from "~/presentation/closing";
import { oldestPendingDate, productionGridUrl, productionWorkOrderUrl } from "~/presentation/crossAppLinks";
import type { ClosingPendingProduction } from "~/types/closing";
import { DRAWER_DENOMINATIONS, formatAmountInput } from "~/presentation/cash";

useHead({ title: "Fim do dia" });

const action = usePosAction();
const runtimeConfig = useRuntimeConfig();
const productionUrl = computed(() => String(runtimeConfig.public.productionUrl || ""));
// Sair do PDV para a Produção é troca de APP: instalado, o destino tem janela
// própria. Quem decide `target`/`rel` é o kit, nunca um `_blank` na mão.
const { attrsFor } = useOperatorAppLink();
// UMA ordem: a tabela mostra o `ref`, e o link leva ATÉ ele (data + busca).
function workOrderHref(row: ClosingPendingProduction): string {
  return productionWorkOrderUrl(productionUrl.value, row);
}

// A projection do PDV entra só pelo `can_audit_cash`: o próximo passo do fim
// de dia (o relatório) é porta que bate na cara de quem não audita, e a tela
// não oferece porta que vai bater.
const { pos, actions, refresh: refreshPos } = await usePosTerminal();
const canAuditCash = computed(() => pos.value?.cash_runtime?.can_audit_cash === true);

const { closing, pending, accessDenied, submitting, submit, answering, answerEpisode } = await useDayClosing({ action });

const dayProduction = computed(() => productionRows(closing.value?.production_summary));

// A grade da Produção no dia do bloqueio mais VELHO. A grade abre em hoje por
// padrão e ordem atrasada é de ontem: sem a data, "Abrir a Produção" entregaria
// uma grade sem nada para resolver.
const productionGrid = computed(() =>
  productionGridUrl(
    productionUrl.value,
    oldestPendingDate(closing.value?.pending_production ?? []),
  ),
);

// A ordem da tela (pelo nome) é a ordem de TUDO: da lista, do Enter e da dica
// que acusa o item que falta — a dica na ordem do servidor apontava um item
// lá embaixo enquanto o de cima estava vazio.
const countItems = computed(() => closingCountOrder(closing.value?.items ?? []));

// Contagem cega: um input por SKU, começa VAZIO (contar de verdade, não
// aceitar default). O CTA só arma quando toda linha tem um número.
const quantities = reactive<Record<string, string>>({});
const canSubmit = computed(
  () => !!closing.value && !closing.value.already_closed
    && allQuantitiesFilled(closing.value.items, quantities),
);
// A dica acusa O ITEM que falta, não "todos": um "1,5" colado deixava a tela
// aparentemente preenchida e a dica mandava procurar sem dizer onde.
const unfilledItemName = computed(
  () => (closing.value ? firstUnfilledItemName(countItems.value, quantities) : ""),
);

// Só dígitos no @input: quantidade é inteira e nunca negativa, e o que não
// for número não deve nem chegar a morar no campo.
function setQuantity(sku: string, raw: string) {
  quantities[sku] = sanitizeQtyInput(raw);
}

const countedTotal = computed(() => countedItems(countItems.value, quantities));

// Enter leva ao PRÓXIMO campo; no último, ao botão de registrar. Contar é
// olhar a vitrine e digitar — a mão não deveria ir ao mouse entre um e outro.
const countList = useTemplateRef<HTMLElement>("countList");
const registerButton = useTemplateRef<{ $el: HTMLElement }>("registerButton");
function focusNextCount(index: number) {
  const inputs = countList.value?.querySelectorAll<HTMLInputElement>("input[data-count-input]") ?? [];
  const next = inputs[index + 1];
  if (next) {
    next.focus();
    next.select();
  } else {
    registerButton.value?.$el?.focus();
  }
}

const confirming = ref(false);
// Fim de dia encadeado: registrado o fechamento, a tela oferece o próximo
// passo em vez de voltar sozinha ao começo do corredor.
const justClosedDay = ref(false);
async function goToCashSession() {
  await navigateTo("/session");
}

async function goToCashReport() {
  await navigateTo("/session/report");
}

// ── O corredor da v4 (`fim-do-dia.jpg`): 1 Fechar caixa · 2 Contar a vitrine · 3 Fechar
// o dia. O passo 1 é a contagem cega da gaveta DENTRO do corredor, com o mesmo
// contador por cédula da Sessão de caixa (`PosDenominationCounter`, desenho do
// corredor) e o mesmo fechamento de turno (`closeCashShift`). Os passos 2 e 3:
// contar a vitrine, revisar o resumo (em peças, nunca em reais) e selar.
const cashOpen = computed<boolean | null>(() => {
  const runtime = pos.value?.cash_runtime;
  return runtime ? Boolean(runtime.has_open_shift) : null;
});
const step = ref<"cash" | "count" | "day">(cashOpen.value ? "cash" : "count");

// PASSO 1: a contagem cega da gaveta. Nada de esperado, nem antes nem depois (o
// veredito da conferência fica com o gerente: decisão do dono). O selo ecoa o número.
const { busy: cashBusy, closeCashShift } = usePosCashSession({ pos, actions, refresh: refreshPos, action });
const drawerMode = ref<"denominations" | "total">("denominations");
const drawerQ = ref(0);
const drawerFilled = ref(0);
const drawerTotal = ref(0);
const drawerNote = ref("");
const drawerNoteOpen = ref(false);
const drawerConfirming = ref(false);
const denominations = DRAWER_DENOMINATIONS;
const drawerDisplay = computed(() => `R$ ${formatAmountInput(drawerQ.value).replace(/\B(?=(\d{3})+(?!\d))/g, ".")}`);
const drawerMissing = computed(() => Math.max(0, drawerTotal.value - drawerFilled.value));
const drawerShift = computed(() => {
  const runtime = pos.value?.cash_runtime;
  if (!runtime?.opened_at) return "";
  const at = new Date(runtime.opened_at);
  const time = Number.isNaN(at.getTime()) ? "" : at.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  return [runtime.terminal_label || pos.value?.terminal_label || "", time ? `turno aberto às ${time}` : "", runtime.operator_username ? `por ${runtime.operator_username}` : ""].filter(Boolean).join(" · ");
});
watch(drawerMode, () => {
  drawerQ.value = 0;
  drawerConfirming.value = false;
});
async function confirmDrawer() {
  const ok = await closeCashShift({ amount: formatAmountInput(drawerQ.value), notes: drawerNote.value.trim() });
  drawerConfirming.value = false;
  if (ok) step.value = "count";
}
const steps = computed(() =>
  closingSteps({
    cashOpen: cashOpen.value,
    counted: countedTotal.value,
    total: countItems.value.length,
    step: step.value,
    dayClosed: Boolean(closing.value?.already_closed),
  }),
);
const summary = computed(() => closingCountSummary(countItems.value, quantities));
// "Maior sobra: Baguette (8) · Ver tudo" (v4 passo 3): sai das contagens, em peças.
const biggestLeftover = computed(() => {
  let best: { name: string; qty: number } | null = null;
  for (const item of countItems.value) {
    const qty = Number.parseInt(String(quantities[item.sku] ?? ""), 10);
    if (Number.isFinite(qty) && qty > 0 && (!best || qty > best.qty)) best = { name: item.name, qty };
  }
  return best;
});
const hourlyShape = computed(() => closing.value?.hourly_shape ?? null);
function goToReview() {
  if (!canSubmit.value) return;
  step.value = "day";
}
// O caixa ainda aberto volta ao passo 1 do próprio corredor (a mesma contagem cega).
function goToCloseCash() {
  step.value = "cash";
}

// "Explicar o dia estranho": uma escolha por episódio, mais o detalhe se quiser.
const episodeChoice = reactive<Record<number, string>>({});
const episodeNote = reactive<Record<number, string>>({});
async function sendEpisode(episodeId: number, kindRef: string) {
  episodeChoice[episodeId] = kindRef;
  await answerEpisode(episodeId, kindRef, (episodeNote[episodeId] || "").trim());
}

const liveStatus = usePosLiveStatus();
// O selo do app no cabeçalho do corredor (a cor do PDV, como no rail).
const appColor = String(
  (runtimeConfig.public.operatorPwa as { identity?: { color?: string } } | undefined)?.identity?.color || "var(--primary)",
);

async function confirmSubmit() {
  if (!closing.value || !canSubmit.value) return;
  const ok = await submit(buildQuantitiesPayload(closing.value.items, quantities));
  confirming.value = false;
  if (ok) {
    for (const key of Object.keys(quantities)) quantities[key] = "";
    justClosedDay.value = true;
  }
}
</script>

<template>
  <main class="flex min-h-dvh flex-col bg-background text-foreground" data-closing-corridor>
    <!-- FIM DO DIA (v4, `fim-do-dia.jpg`): um corredor só, de quem fecha. Cabeçalho com
         o título, o ao vivo e o terminal; os três passos no topo; a CONFERÊNCIA cega no
         meio; o gesto de cada passo preso ao pé. -->
    <header class="flex shrink-0 flex-wrap items-center gap-3 border-b border-border bg-card px-4 py-2.5">
      <span class="grid size-10 shrink-0 place-items-center rounded-lg text-white" :style="{ background: appColor }" aria-hidden="true">
        <Icon name="lucide:shopping-basket" class="size-5" />
      </span>
      <div class="min-w-0">
        <h1 class="op-heading">Fim do dia</h1>
        <p class="mt-1 flex items-center gap-2 op-micro text-muted-foreground">
          <OperatorLiveStatus
            :tone="liveStatus.view.value.tone"
            :time="liveStatus.time.value"
            :label="liveStatus.view.value.label"
            :detail="liveStatus.view.value.detail"
          />
          <span v-if="pos">{{ pos.terminal_label }}</span>
          <span v-if="closing">· {{ closing.today_display }}</span>
        </p>
      </div>
      <div class="flex-1" />
      <span
        v-if="closing?.operator_display"
        class="inline-flex h-11 items-center gap-1.5 rounded-full bg-secondary px-4 op-label font-semibold"
        data-closing-operator
      >
        <Icon name="lucide:user-round" class="size-4" aria-hidden="true" />{{ closing.operator_display }}
      </span>
      <button
        type="button"
        class="inline-flex h-11 items-center gap-1.5 rounded-full border border-border bg-card px-4 op-label font-semibold transition hover:bg-accent"
        aria-label="Voltar à sessão de caixa"
        title="Sair: o que já foi contado fica na tela até você voltar"
        @click="goToCashSession"
      >
        <Icon name="lucide:x" class="size-4" />
        Sair
      </button>
    </header>

    <!-- Os três passos: cada um diz a hora e o estado, nunca valor. -->
    <ol
      v-if="closing && !accessDenied"
      class="flex shrink-0 items-center gap-3 overflow-x-auto border-b border-border bg-card px-4 py-3 no-scrollbar"
      aria-label="Passos do fim do dia"
      data-closing-steps
    >
      <template v-for="(item, index) in steps" :key="item.key">
        <li v-if="index" class="h-0.5 min-w-6 flex-1 rounded-full" :class="steps[index - 1]?.state === 'done' ? 'bg-success' : 'bg-border'" aria-hidden="true" />
        <li class="flex shrink-0 items-center gap-2.5" :aria-current="item.state === 'current' ? 'step' : undefined" :data-closing-step="item.key" :data-state="item.state">
          <span
            class="grid size-10 shrink-0 place-items-center rounded-full op-title"
            :class="item.state === 'done'
              ? 'bg-success text-white'
              : item.state === 'current'
                ? 'bg-primary text-primary-foreground'
                : 'bg-secondary text-muted-foreground'"
          >
            <Icon v-if="item.state === 'done'" name="lucide:check" class="size-5" />
            <template v-else>{{ index + 1 }}</template>
          </span>
          <span class="leading-tight">
            <span class="block op-label font-semibold" :class="item.state === 'todo' ? 'text-muted-foreground' : ''">{{ item.label }}</span>
            <span class="block op-micro text-muted-foreground tnum">{{ item.detail }}</span>
          </span>
        </li>
      </template>
    </ol>

    <div class="mx-auto grid w-full max-w-3xl flex-1 content-start gap-4 p-4 md:py-6">
      <!-- Sem permissão: fechamento é ritual do gerente. -->
      <section v-if="accessDenied" class="grid gap-2 rounded-xl border bg-card p-4">
        <div class="flex items-center gap-2">
          <Icon name="lucide:lock" class="size-4 text-muted-foreground" />
          <h2 class="op-title">Fechamento é do gerente</h2>
        </div>
        <p class="op-body text-muted-foreground">
          Sua conta não tem permissão para realizar o fechamento do dia. Chame quem cuida do encerramento.
        </p>
        <UiButton variant="outline" size="sm" @click="goToCashSession">Voltar à sessão de caixa</UiButton>
      </section>

      <template v-else-if="closing">
        <UiAlert v-if="closing.already_closed" class="border-success/30 bg-success/10 text-success">
          <Icon name="lucide:circle-check" class="size-4" />
          <UiAlertTitle>Dia fechado</UiAlertTitle>
          <UiAlertDescription>{{ closing.existing_closing_display }}</UiAlertDescription>
        </UiAlert>

        <!-- Fim de dia encadeado: registrado o fechamento, o próximo passo vem
             até a mão. Relatório só para quem audita: porta que bateria na
             cara não é oferta. -->
        <section v-if="justClosedDay && closing.already_closed" class="grid gap-2 rounded-xl border bg-card p-4">
          <p class="op-body text-muted-foreground">
            Fechamento registrado. O quadro do dia está logo abaixo.
          </p>
          <div class="grid gap-2 sm:grid-cols-2">
            <UiButton v-if="canAuditCash" variant="outline" @click="goToCashReport">
              <Icon name="lucide:receipt-text" class="size-4" />
              Ver relatório de caixa
            </UiButton>
            <UiButton variant="outline" @click="goToCashSession">
              <Icon name="lucide:arrow-left" class="size-4" />
              Voltar à sessão de caixa
            </UiButton>
          </div>
        </section>

        <!-- PASSO 1 (v4 `fim-do-dia.jpg` a): quanto tem na gaveta. Contagem cega por
             desenho: nenhum valor esperado na tela, nem depois. Por cédula ou só o
             total (os dois modos de hoje), uma linha ativa por vez, o numérico da
             tela e o selo que aponta e ecoa: "Contei R$ X · Confirmar". -->
        <section
          v-if="!closing.already_closed && step === 'cash' && cashOpen"
          class="grid gap-4"
          data-closing-cash-count
        >
          <div class="flex flex-wrap items-start gap-3">
            <div class="min-w-0 flex-1">
              <h2 class="op-heading">Quanto tem na gaveta?</h2>
              <p v-if="drawerShift" class="mt-1 op-micro text-muted-foreground">{{ drawerShift }}</p>
            </div>
            <div class="inline-flex h-11 items-center gap-1 rounded-md bg-secondary p-1" role="group" aria-label="Como contar">
              <button
                type="button"
                class="h-full rounded px-3 op-label transition"
                :class="drawerMode === 'denominations' ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground'"
                :aria-pressed="drawerMode === 'denominations'"
                @click="drawerMode = 'denominations'"
              >Por cédula</button>
              <button
                type="button"
                class="h-full rounded px-3 op-label transition"
                :class="drawerMode === 'total' ? 'bg-card font-semibold shadow-sm' : 'text-muted-foreground'"
                :aria-pressed="drawerMode === 'total'"
                @click="drawerMode = 'total'"
              >Só o total</button>
            </div>
          </div>
          <p class="flex items-start gap-2 rounded-lg bg-secondary px-3 py-2 op-body text-muted-foreground">
            <Icon name="lucide:eye-off" class="mt-0.5 size-4 shrink-0" />
            <span>Contagem cega: o esperado não aparece, nem depois. Conte o que está na gaveta.</span>
          </p>
          <PosDenominationCounter
            :key="drawerMode"
            layout="corridor"
            :mode="drawerMode"
            :denominations="denominations"
            :disabled="cashBusy"
            @total-q="drawerQ = $event"
            @progress="(filled, total) => { drawerFilled = filled; drawerTotal = total; }"
            @note="drawerNoteOpen = true"
          />
          <UiInput
            v-if="drawerNoteOpen || drawerNote"
            v-model="drawerNote"
            class="h-12"
            placeholder="Observação da contagem (ex.: nota rasgada separada)"
            aria-label="Observação da contagem da gaveta"
          />
          <div class="sticky bottom-0 -mx-4 grid gap-1.5 border-t bg-background/95 px-4 py-3 backdrop-blur">
            <UiButton
              v-if="!drawerConfirming"
              size="lg"
              variant="outline"
              class="h-14 w-full border-2 border-dashed border-primary/60 text-base"
              :disabled="cashBusy"
              data-closing-cash-confirm
              @click="drawerConfirming = true"
            >
              <Icon name="lucide:arrow-down" class="size-5" />
              Contei {{ drawerDisplay }} · Confirmar
            </UiButton>
            <div v-else class="grid gap-2 rounded-xl border border-primary/40 bg-card p-3 shadow-lg">
              <p class="op-body font-semibold">Fechar o caixa com {{ drawerDisplay }} contados? O turno encerra aqui.</p>
              <div class="grid grid-cols-2 gap-2">
                <UiButton variant="outline" :disabled="cashBusy" @click="drawerConfirming = false">Voltar à contagem</UiButton>
                <UiButton :disabled="cashBusy" :loading="cashBusy" data-closing-cash-seal @click="confirmDrawer">Fechar o caixa</UiButton>
              </div>
            </div>
            <p class="text-center op-micro text-muted-foreground">
              <template v-if="drawerMode === 'denominations' && drawerMissing">Faltam {{ drawerMissing }} {{ drawerMissing === 1 ? "valor" : "valores" }}. Valor em branco conta como zero ao confirmar; o total se repete para você conferir.</template>
              <template v-else>O total se repete para você conferir antes de fechar.</template>
            </p>
            <button type="button" class="justify-self-center op-micro text-muted-foreground underline underline-offset-2" @click="step = 'count'">
              Contar a vitrine primeiro
            </button>
          </div>
        </section>

        <!-- BLOQUEIO, antes da contagem. Diz QUANTAS ordens faltam e para onde
             ir; não diz SKU nem quantidade, que é o que entregaria a resposta.
             A tabela completa aparece depois que a contagem é registrada. -->
        <section
          v-if="!closing.already_closed && closing.has_pending_production && step !== 'cash'"
          class="grid gap-2 rounded-xl border border-warning/40 bg-warning/10 p-4"
        >
          <div class="flex items-center gap-2">
            <Icon name="lucide:triangle-alert" class="size-4 text-warning" />
            <h2 class="op-title">Produção em aberto</h2>
          </div>
          <p class="op-body text-muted-foreground">
            {{ closing.pending_production.length === 1
              ? "Uma ordem de produção ainda está aberta."
              : `${closing.pending_production.length} ordens de produção ainda estão abertas.` }}
            Conclua ou estorne antes de encerrar o dia.
          </p>
          <!-- A contagem é CEGA: aqui o link não pode apontar para uma ordem,
               porque a ordem carrega SKU. Leva à grade da Produção no dia do
               bloqueio mais velho, e o rótulo promete só isso. -->
          <a
            v-if="productionGrid"
            class="op-label font-semibold underline underline-offset-4"
            :href="productionGrid"
            v-bind="attrsFor(productionGrid)"
            data-production-link
          >
            Abrir a Produção
          </a>
        </section>

        <!-- Produção pendente -->
        <section v-if="closing.already_closed && closing.has_pending_production" class="grid gap-2 rounded-xl border bg-card p-4">
          <div class="flex items-center gap-2">
            <h2 class="op-title">Produção pendente</h2>
            <span class="inline-flex items-center rounded-md border border-warning/50 bg-warning/10 px-1.5 py-0.5 text-xs font-medium text-warning">
              {{ closing.pending_production.length }}
            </span>
          </div>
          <p class="text-sm text-muted-foreground">
            Ordens que seguiam abertas quando o dia foi encerrado. Elas ficaram registradas neste fechamento; toque na ordem para abri-la na Produção.
          </p>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-xs text-muted-foreground">
                  <th class="py-1.5 pr-3 font-medium">Ordem</th>
                  <th class="py-1.5 pr-3 font-medium">SKU</th>
                  <th class="py-1.5 pr-3 font-medium">Status</th>
                  <th class="py-1.5 pr-3 font-medium">Qtd</th>
                  <th class="py-1.5 font-medium">Alvo</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in closing.pending_production" :key="row.ref" class="border-b border-border/60 last:border-0">
                  <!-- O `ref` na tela É o caminho: o link abre a Produção no dia
                       da ordem, já filtrada por ela. Antes o botão da seção
                       jogava o operador na raiz e ele reencontrava à mão. -->
                  <td class="py-1.5 pr-3 font-medium">
                    <a
                      v-if="workOrderHref(row)"
                      class="underline underline-offset-4"
                      :href="workOrderHref(row)"
                      v-bind="attrsFor(workOrderHref(row))"
                      :aria-label="`Abrir a ordem ${row.ref} na Produção`"
                      data-work-order-link
                    >{{ row.ref }}</a>
                    <template v-else>{{ row.ref }}</template>
                  </td>
                  <td class="py-1.5 pr-3">{{ row.output_sku }}</td>
                  <td class="py-1.5 pr-3" :class="row.is_overdue ? 'text-destructive' : ''">{{ pendingStatusDisplay(row) }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.quantity }}</td>
                  <td class="py-1.5 tabular-nums">{{ row.target_date_display }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <a
            v-if="productionGrid"
            class="text-sm font-medium underline underline-offset-4"
            :href="productionGrid"
            v-bind="attrsFor(productionGrid)"
            data-production-link
          >
            Abrir a Produção
          </a>
        </section>

        <!-- Produção do dia (pós-contagem: é a resposta da prova) -->
        <section v-if="closing.already_closed" class="grid gap-2 rounded-xl border bg-card p-4">
          <h2 class="op-title">Produção do dia</h2>
          <p v-if="!dayProduction.length" class="text-sm text-muted-foreground">Sem produção registrada hoje.</p>
          <div v-else class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-xs text-muted-foreground">
                  <th class="py-1.5 pr-3 font-medium">SKU</th>
                  <th class="py-1.5 pr-3 font-medium">Planejado</th>
                  <th class="py-1.5 pr-3 font-medium">Feito</th>
                  <th class="py-1.5 font-medium">Perda</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in dayProduction" :key="row.sku" class="border-b border-border/60 last:border-0">
                  <td class="py-1.5 pr-3 font-medium">{{ row.sku }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.planned }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.finished }}</td>
                  <td class="py-1.5 tabular-nums">{{ row.loss }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- Encomendas dos próximos dias -->
        <section v-if="closing.already_closed && closing.has_upcoming_preorders" class="grid gap-2 rounded-xl border bg-card p-4">
          <div class="flex items-center gap-2">
            <h2 class="op-title">Encomendas para os próximos dias</h2>
            <span class="inline-flex items-center rounded-md border border-border bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
              {{ closing.upcoming_preorders.length }}
            </span>
          </div>
          <p class="text-sm text-muted-foreground">
            Todas as encomendas confirmadas ou a confirmar com data depois de hoje, qualquer que seja o dia em que foram feitas. Saem do estoque na data combinada.
          </p>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-xs text-muted-foreground">
                  <th class="py-1.5 pr-3 font-medium">Data</th>
                  <th class="py-1.5 font-medium">Pedidos</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in closing.upcoming_preorders" :key="row.date" class="border-b border-border/60 last:border-0">
                  <td class="py-1.5 pr-3">{{ row.date_display }}</td>
                  <td class="py-1.5 tabular-nums">{{ row.orders_count }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- Discrepâncias -->
        <section v-if="closing.already_closed && closing.reconciliation_errors.length" class="grid gap-2 rounded-xl border border-destructive/40 bg-card p-4">
          <h2 class="op-title text-destructive">Discrepâncias detectadas</h2>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b text-left text-xs text-muted-foreground">
                  <th class="py-1.5 pr-3 font-medium">SKU</th>
                  <th class="py-1.5 pr-3 font-medium">Vendido</th>
                  <th class="py-1.5 pr-3 font-medium">Disponível</th>
                  <th class="py-1.5 font-medium">Déficit</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in closing.reconciliation_errors" :key="row.sku" class="border-b border-border/60 last:border-0">
                  <td class="py-1.5 pr-3 font-medium">{{ row.sku }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.sold_qty }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.available_qty }}</td>
                  <td class="py-1.5 tabular-nums text-destructive">{{ row.deficit_qty }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- PASSO 2: contar a vitrine (CONFERÊNCIA cega, por produto). -->
        <section v-if="closing.already_closed || step === 'count'" class="grid gap-3 rounded-xl border bg-card p-4" data-closing-count>
          <div class="flex items-baseline justify-between gap-2">
            <div>
              <p class="op-eyebrow text-muted-foreground">Contagem final</p>
              <h2 class="op-heading">O que sobrou na vitrine?</h2>
            </div>
            <span
              v-if="closing.has_items && !closing.already_closed"
              class="op-label tnum text-muted-foreground"
              data-count-progress
            >{{ countedTotal }} de {{ countItems.length }} contados</span>
          </div>
          <p class="flex items-start gap-2 rounded-lg bg-secondary px-3 py-2 op-body text-muted-foreground">
            <Icon name="lucide:eye-off" class="mt-0.5 size-4 shrink-0" />
            <span>Contagem cega: conte o que sobrou do que a casa produz (revenda não entra). Nada sobrou? Digite 0. O sistema trata destino e perdas.</span>
          </p>
          <p v-if="!closing.has_items" class="op-body text-muted-foreground">Nada produzido na casa em estoque para contar.</p>
          <div v-else ref="countList" class="grid gap-1.5">
            <div
              v-for="(item, index) in countItems"
              :key="item.sku"
              class="flex items-center gap-3 rounded-lg border border-border px-3 py-2 transition"
              :class="/^\d+$/.test((quantities[item.sku] ?? '').trim()) ? 'bg-card' : 'bg-background'"
            >
              <div class="min-w-0 flex-1">
                <p class="truncate op-title" :title="item.name">{{ item.name }}</p>
                <p class="op-micro font-mono text-muted-foreground">{{ item.sku }}</p>
              </div>
              <span
                class="inline-flex h-6 shrink-0 items-center rounded-full border px-2 op-micro font-semibold"
                :class="closingBadge(item.classification).css"
              >
                {{ closingBadge(item.classification).label }}
              </span>
              <!-- Só dígitos no @input: o "1,5" colado não chega a morar no
                   campo, e o CTA não trava por um caractere invisível. -->
              <!-- Sem placeholder "0": um zero cinza parece contado, e a
                   contagem cega começa VAZIA. -->
              <UiInput
                :model-value="quantities[item.sku]"
                inputmode="numeric"
                enterkeyhint="next"
                class="h-12 w-24 text-right op-title tabular-nums focus-visible:border-2 focus-visible:border-primary"
                :disabled="closing.already_closed || submitting"
                :aria-label="`Sobras de ${item.name}`"
                data-count-input
                @update:model-value="setQuantity(item.sku, $event)"
                @keydown.enter.prevent="focusNextCount(index)"
              />
            </div>
          </div>

          <!-- Preso ao pé: o selo que aponta e ecoa (v4). Contar trinta itens não
               termina numa rolagem à procura do botão. -->
          <div
            v-if="closing.has_items && !closing.already_closed"
            class="sticky bottom-0 -mx-4 -mb-4 mt-1 border-t bg-card/95 px-4 py-3 backdrop-blur"
          >
            <UiButton
              ref="registerButton"
              size="lg"
              class="h-14 w-full text-base"
              :class="canSubmit ? '' : 'border-2 border-dashed border-primary/40 bg-transparent text-foreground'"
              :disabled="!canSubmit || submitting"
              data-closing-review
              @click="goToReview"
            >
              <Icon name="lucide:arrow-down" class="size-5" />
              Contei {{ piecesLabel(summary.keep + summary.loss + summary.mixed) }} · Revisar e fechar o dia
            </UiButton>
            <!-- A dica aponta o item, não "todos": procurar um campo vazio
                 numa lista aparentemente preenchida era a parte difícil. -->
            <p v-if="!canSubmit" class="mt-1.5 text-center op-micro text-muted-foreground">
              <template v-if="unfilledItemName">Falta a contagem de {{ unfilledItemName }}.</template>
              <template v-else>Preencha a contagem de todos os itens para registrar.</template>
            </p>
          </div>
        </section>

        <!-- PASSO 3: o dia, depois de contado. Às cegas até o fim, para todos: peças,
             estados e a pergunta do dia estranho; nunca reais. -->
        <template v-if="!closing.already_closed && step === 'day'">
          <h2 class="op-heading" data-closing-day>O dia, depois de contado</h2>
          <div class="grid gap-3 md:grid-cols-2">
            <section class="grid content-start gap-2 rounded-xl border bg-card p-4" data-closing-cash>
              <p class="flex items-center gap-1.5 op-eyebrow text-muted-foreground"><Icon name="lucide:wallet" class="size-3.5" />Caixa</p>
              <div class="flex items-center gap-3">
                <span
                  class="grid size-10 shrink-0 place-items-center rounded-full"
                  :class="cashOpen === false ? 'bg-success/15 text-success' : 'bg-warning/15 text-warning'"
                >
                  <Icon :name="cashOpen === false ? 'lucide:circle-check' : 'lucide:clock'" class="size-5" />
                </span>
                <div>
                  <p class="op-title" :class="cashOpen === false ? 'text-success' : ''">{{ cashOpen === false ? "Caixa fechado" : "Caixa ainda aberto" }}</p>
                  <p class="op-micro text-muted-foreground">{{ cashOpen === false ? "contagem cega registrada no turno" : "feche antes ou depois: a contagem é a mesma" }}</p>
                </div>
              </div>
              <p class="flex items-center gap-1.5 rounded-lg bg-secondary px-3 py-2 op-micro text-muted-foreground">
                <Icon name="lucide:eye-off" class="size-3.5 shrink-0" />
                Fechamento às cegas: valores só na auditoria
              </p>
              <UiButton v-if="cashOpen" variant="outline" size="sm" @click="goToCloseCash">Fechar caixa</UiButton>
            </section>
            <section class="grid content-start gap-2 rounded-xl border bg-card p-4" data-closing-showcase>
              <p class="flex items-center gap-1.5 op-eyebrow text-muted-foreground"><Icon name="lucide:store" class="size-3.5" />Vitrine</p>
              <dl class="grid gap-1.5 op-body">
                <div class="flex justify-between gap-2"><dt class="text-muted-foreground">Ficam para amanhã</dt><dd class="op-title tnum">{{ piecesLabel(summary.keep) }}</dd></div>
                <div class="flex justify-between gap-2"><dt class="text-muted-foreground">Viram perda</dt><dd class="op-title tnum">{{ piecesLabel(summary.loss) }}</dd></div>
                <div v-if="summary.mixed" class="flex justify-between gap-2"><dt class="text-muted-foreground">Lote misto (parte vence)</dt><dd class="op-title tnum">{{ piecesLabel(summary.mixed) }}</dd></div>
              </dl>
              <button
                v-if="biggestLeftover"
                type="button"
                class="flex items-center justify-between gap-2 rounded-lg bg-secondary px-3 py-2 text-left op-label"
                data-closing-biggest
                @click="step = 'count'"
              >
                <span class="font-semibold">Maior sobra: {{ biggestLeftover.name }} ({{ biggestLeftover.qty }})</span>
                <span class="shrink-0 font-semibold text-primary">Ver tudo</span>
              </button>
              <button v-else type="button" class="justify-self-start op-label font-semibold text-primary underline underline-offset-4" @click="step = 'count'">
                Voltar à contagem
              </button>
            </section>
          </div>

          <section class="flex items-center gap-3 rounded-xl border bg-card p-4" data-closing-production>
            <Icon
              :name="closing.has_pending_production ? 'lucide:triangle-alert' : 'lucide:circle-check'"
              class="size-5 shrink-0"
              :class="closing.has_pending_production ? 'text-warning' : 'text-success'"
            />
            <p class="min-w-0 flex-1 op-body">
              {{ closing.has_pending_production
                ? (closing.pending_production.length === 1 ? "Produção: uma ordem ainda aberta" : `Produção: ${closing.pending_production.length} ordens ainda abertas`)
                : "Produção: todos os lotes de hoje fechados" }}
            </p>
            <span class="inline-flex h-6 items-center gap-1 rounded-full bg-secondary px-2 op-micro font-semibold text-muted-foreground">
              <Icon name="lucide:sparkles" class="size-3.5" />automático
            </span>
          </section>

          <!-- EXPLICAR O DIA ESTRANHO: só aparece quando o sistema notou um sinal. A
               resposta marca o dia (o plano e o B.I. não aprendem com ele). -->
          <section
            v-for="episode in closing.pending_episodes || []"
            :key="episode.id"
            class="grid gap-3 rounded-xl border-2 border-primary/60 bg-card p-4"
            data-closing-episode
          >
            <div class="flex items-start gap-3">
              <span class="grid size-10 shrink-0 place-items-center rounded-full bg-secondary text-primary">
                <Icon name="lucide:trending-down" class="size-5" />
              </span>
              <div class="min-w-0">
                <p class="op-eyebrow text-primary">Explicar o dia estranho</p>
                <p class="op-title">{{ episode.signal }}. Aconteceu algo?</p>
                <p class="op-micro text-muted-foreground tnum">
                  {{ hourlyShape?.drop_after ? `O movimento caiu depois das ${hourlyShape.drop_after}.` : episode.window_display }}
                </p>
              </div>
            </div>
            <PosHourlyShape v-if="hourlyShape" :shape="hourlyShape" />
            <div class="flex flex-wrap gap-2" role="group" :aria-label="`O que houve: ${episode.signal}`">
              <button
                v-for="option in closing.episode_options || []"
                :key="option.ref"
                type="button"
                class="inline-flex h-12 items-center gap-1.5 rounded-full border px-4 op-label font-semibold transition hover:bg-accent disabled:opacity-50"
                :class="episodeChoice[episode.id] === option.ref ? 'border-primary bg-primary/10' : 'border-border bg-card'"
                :aria-pressed="episodeChoice[episode.id] === option.ref"
                :title="option.hint || undefined"
                :disabled="answering !== null"
                @click="sendEpisode(episode.id, option.ref)"
              >
                <Icon v-if="episodeChoice[episode.id] === option.ref" name="lucide:check" class="size-4" />
                {{ option.label }}
              </button>
              <button
                type="button"
                class="inline-flex h-12 items-center rounded-full border border-dashed border-border px-4 op-label text-muted-foreground transition hover:bg-accent disabled:opacity-50"
                :disabled="answering !== null"
                @click="sendEpisode(episode.id, '')"
              >
                Não houve nada
              </button>
            </div>
            <UiInput
              v-model="episodeNote[episode.id]"
              class="h-12"
              placeholder="Detalhe, se quiser (ex.: temporal às 14h, rua alagada)"
              :aria-label="`Detalhe do que houve: ${episode.signal}`"
            />
            <p class="flex items-start gap-1.5 op-micro text-muted-foreground">
              <Icon name="lucide:chart-no-axes-column" class="mt-0.5 size-3.5 shrink-0" />
              A resposta marca o dia: a projeção e a sugestão do plano não aprendem com um dia assim como se fosse normal.
            </p>
          </section>

          <!-- O selo irreversível, com a consequência escrita embaixo. -->
          <div class="sticky bottom-0 -mx-4 mt-1 grid gap-1.5 border-t bg-background/95 px-4 py-3 backdrop-blur">
            <div v-if="!confirming" class="flex gap-2">
              <UiButton variant="outline" size="lg" class="h-14" @click="step = 'count'">
                <Icon name="lucide:arrow-left" class="size-4" />
                Vitrine
              </UiButton>
              <UiButton size="lg" class="h-14 flex-1 text-base" :disabled="!canSubmit || submitting" data-closing-seal @click="confirming = true">
                <Icon name="lucide:lock" class="size-5" />
                Fechar o dia {{ closing.today_display }}
              </UiButton>
            </div>
            <div v-else class="grid gap-2 rounded-xl border border-destructive/40 bg-card p-3 shadow-lg">
              <p class="op-body font-semibold">
                Confirmar o fechamento do dia {{ closing.today_display }}? Sobras viram "Ontem" ou perda e a contagem é registrada.
              </p>
              <div class="grid grid-cols-2 gap-2">
                <UiButton variant="outline" :disabled="submitting" @click="confirming = false">Cancelar</UiButton>
                <UiButton variant="destructive" :disabled="submitting" :loading="submitting" @click="confirmSubmit">
                  Confirmar fechamento
                </UiButton>
              </div>
            </div>
            <p class="text-center op-micro text-muted-foreground">Não reabre: um fechamento por dia. Sobras entram como estoque de ontem, perdas saem pelo lote.</p>
          </div>
        </template>
      </template>

      <section v-else-if="pending" class="grid place-items-center rounded-xl border bg-card p-8">
        <Icon name="line-md:loading-loop" class="size-6 text-muted-foreground" />
      </section>
    </div>
  </main>
</template>
