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
// leva ao próximo campo, o progresso diz quanto falta, e o gesto de cada passo
// fica fora da rolagem — contar trinta itens não pode terminar numa rolagem à
// procura do botão. Fase 2 (onda do PDV): no celular o gesto é a ação na base do kit
// (`OperatorActionBar`, em fluxo, irmã da região que rola); na mesa ele sobe para o
// cabeçalho, que não rola. As confirmações são o diálogo da casa (`useConfirm`).
import type { OperatorActionBarAction } from "../../../../operator-kit/app/presentation/actionBar";
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

// Enter leva ao PRÓXIMO campo; no último, ao gesto de revisar. Contar é
// olhar a vitrine e digitar — a mão não deveria ir ao mouse entre um e outro.
// O gesto mora em dois lugares (cabeçalho na mesa, base no celular) e o CSS mostra
// um só: o foco vai para o que está na tela.
const countList = useTemplateRef<HTMLElement>("countList");
function focusNextCount(index: number) {
  const inputs = countList.value?.querySelectorAll<HTMLInputElement>("input[data-count-input]") ?? [];
  const next = inputs[index + 1];
  if (next) {
    next.focus();
    next.select();
    return;
  }
  const targets = [
    ...document.querySelectorAll<HTMLElement>("[data-closing-review], [data-closing-bar] [data-operator-action-bar-action]"),
  ];
  (targets.find((el) => el.offsetParent !== null) ?? targets[0])?.focus();
}

// Fim de dia encadeado: registrado o fechamento, a tela oferece o próximo
// passo em vez de voltar sozinha ao começo do corredor. Os caminhos de volta
// são links (`to`): sem espera para declarar.
const justClosedDay = ref(false);
const confirm = useConfirm();

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
const drawerModes = [
  { label: "Por cédula", value: "denominations" },
  { label: "Só o total", value: "total" },
];
watch(drawerMode, () => {
  drawerQ.value = 0;
});
// O selo ecoa o número antes de fechar: é a última leitura antes de ele virar a única
// palavra do operador no livro.
async function confirmDrawer() {
  const ok = await confirm({
    tone: "primary",
    title: `Fechar o caixa com ${drawerDisplay.value} contados?`,
    description: "O turno encerra aqui. A contagem fica registrada no turno; a conferência é da retaguarda.",
    confirmLabel: "Fechar o caixa",
    cancelLabel: "Voltar à contagem",
  });
  if (!ok) return;
  const closed = await closeCashShift({ amount: formatAmountInput(drawerQ.value), notes: drawerNote.value.trim() });
  if (closed) step.value = "count";
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

// O selo irreversível: a confirmação diz a consequência antes do toque.
async function confirmSubmit() {
  if (!closing.value || !canSubmit.value) return;
  const day = closing.value.today_display;
  const ok = await confirm({
    title: `Fechar o dia ${day}?`,
    description: 'Sobras viram "Ontem" ou perda e a contagem é registrada. Não reabre: um fechamento por dia.',
    confirmLabel: `Fechar o dia ${day}`,
    cancelLabel: "Voltar ao resumo",
  });
  if (!ok || !closing.value) return;
  const done = await submit(buildQuantitiesPayload(closing.value.items, quantities));
  if (done) {
    for (const key of Object.keys(quantities)) quantities[key] = "";
    justClosedDay.value = true;
  }
}

// O gesto do passo, declarado como dados: a mesma ação na base do celular
// (`OperatorActionBar`) e no cabeçalho da mesa. `kind` dá a marca de cada passo.
type ClosingBar = { kind: "cash" | "count" | "day"; action: OperatorActionBarAction; secondary?: OperatorActionBarAction };
const bar = computed<ClosingBar | null>(() => {
  const current = closing.value;
  if (!current || accessDenied.value || current.already_closed) return null;
  if (step.value === "cash" && cashOpen.value) {
    return {
      kind: "cash",
      action: {
        label: `Contei ${drawerDisplay.value} · Confirmar`,
        icon: "i-lucide-wallet",
        loading: cashBusy.value,
        disabled: cashBusy.value,
        onSelect: () => void confirmDrawer(),
      },
    };
  }
  if (step.value === "day") {
    return {
      kind: "day",
      action: {
        label: `Fechar o dia ${current.today_display}`,
        icon: "i-lucide-lock",
        loading: submitting.value,
        disabled: !canSubmit.value || submitting.value,
        onSelect: () => void confirmSubmit(),
      },
      secondary: { label: "Vitrine", icon: "i-lucide-arrow-left", onSelect: () => { step.value = "count"; } },
    };
  }
  if (current.has_items) {
    return {
      kind: "count",
      action: {
        label: `Contei ${piecesLabel(summary.value.keep + summary.value.loss + summary.value.mixed)} · Revisar e fechar o dia`,
        icon: "i-lucide-list-checks",
        disabled: !canSubmit.value || submitting.value,
        // A dica aponta o item, não "todos": procurar um campo vazio numa lista
        // aparentemente preenchida era a parte difícil.
        reason: unfilledItemName.value
          ? `Falta a contagem de ${unfilledItemName.value}.`
          : "Preencha a contagem de todos os itens para registrar.",
        onSelect: goToReview,
      },
    };
  }
  return null;
});
// A marca de teste e de foco de cada passo, no botão da mesa.
const BAR_MARK = { cash: "data-closing-cash-confirm", count: "data-closing-review", day: "data-closing-seal" } as const;
const barMark = computed(() => (bar.value ? { [BAR_MARK[bar.value.kind]]: "" } : {}));
const barReason = computed(() => {
  const action = bar.value?.action;
  return action?.disabled && action.reason ? action.reason : "";
});

// As tabelas do quadro do dia (depois da contagem), na tabela da suíte.
const NUM = { class: { th: "text-right", td: "text-right tabular-nums whitespace-nowrap" } };
const pendingColumns = [
  { id: "ref", header: "Ordem" },
  { accessorKey: "output_sku", header: "SKU" },
  { id: "status", header: "Status" },
  { accessorKey: "quantity", header: "Qtd", meta: NUM },
  { accessorKey: "target_date_display", header: "Alvo" },
];
const productionColumns = [
  { accessorKey: "sku", header: "SKU" },
  { accessorKey: "planned", header: "Planejado", meta: NUM },
  { accessorKey: "finished", header: "Feito", meta: NUM },
  { accessorKey: "loss", header: "Perda", meta: NUM },
];
const preorderColumns = [
  { accessorKey: "date_display", header: "Data" },
  { accessorKey: "orders_count", header: "Pedidos", meta: NUM },
];
const discrepancyColumns = [
  { accessorKey: "sku", header: "SKU" },
  { accessorKey: "sold_qty", header: "Vendido", meta: NUM },
  { accessorKey: "available_qty", header: "Disponível", meta: NUM },
  { id: "deficit", header: "Déficit", meta: NUM },
];
</script>


<template>
  <main class="flex h-dvh flex-col bg-background text-foreground" data-closing-corridor>
    <!-- FIM DO DIA (v4, `fim-do-dia.jpg`): um corredor só, de quem fecha. Cabeçalho com
         o título, o ao vivo e o terminal; os três passos no topo; a CONFERÊNCIA cega no
         meio, numa região que rola; o gesto de cada passo fora da rolagem. -->
    <!-- O cabeçalho da suíte (o mesmo `OperatorPageHeader` das outras telas), no papel
         de corredor: sem campo de busca, sem Avisos, sem navegação; a saída é o "Sair".
         ⚠️ O kit não tem a variante `task` do cabeçalho: o corredor é o cabeçalho comum
         com `:inbox="false"` e a busca só no atalho. -->
    <OperatorPageHeader title="Fim do dia" :inbox="false">
      <!-- A busca da suíte só no Ctrl K (e na lupa do celular): no corredor não há campo
           de busca na tela, e o "/" não tira a pessoa da contagem. -->
      <template #search>
        <OperatorSuiteSearch variant="hotkey" placeholder="Buscar pedido, cliente, produto ou tela" />
      </template>
      <template #lead>
        <span class="grid size-8 shrink-0 place-items-center rounded-md text-white" :style="{ background: appColor }" aria-hidden="true">
          <Icon name="lucide:shopping-basket" class="size-4" />
        </span>
      </template>
      <template #status>
        <OperatorLiveStatus
          :tone="liveStatus.view.value.tone"
          :time="liveStatus.time.value"
          :label="liveStatus.view.value.label"
          :detail="liveStatus.view.value.detail"
        />
        <span v-if="pos" class="text-xs text-muted-foreground">{{ pos.terminal_label }}<template v-if="closing"> · {{ closing.today_display }}</template></span>
      </template>
      <template #actions>
        <NuxtBadge
          v-if="closing?.operator_display"
          color="neutral"
          icon="i-lucide-user-round"
          :label="closing.operator_display"
          class="max-sm:hidden"
          data-closing-operator
        />
        <NuxtButton
          color="neutral"
          variant="outline"
          icon="i-lucide-x"
          label="Sair"
          to="/session"
          aria-label="Sair do fim do dia e voltar à sessão de caixa"
          title="Sair: o que já foi contado fica na tela até você voltar"
          data-closing-exit
        />
        <!-- Na mesa, o gesto do passo mora aqui, no cabeçalho que não rola (a ação na
             base do kit só existe abaixo de `lg`). -->
        <NuxtButton
          v-if="bar?.secondary"
          class="max-lg:hidden"
          color="neutral"
          variant="outline"
          :icon="bar.secondary.icon"
          :label="bar.secondary.label"
          @click="bar.secondary.onSelect?.($event)"
        />
        <NuxtButton
          v-if="bar"
          class="max-lg:hidden"
          color="primary"
          :icon="bar.action.icon"
          :label="bar.action.label"
          :loading="bar.action.loading"
          :disabled="bar.action.disabled"
          v-bind="barMark"
          @click="bar.action.onSelect?.($event)"
        />
      </template>
    </OperatorPageHeader>

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

    <div class="min-h-0 flex-1 overflow-y-auto">
      <div class="mx-auto grid w-full max-w-3xl content-start gap-4 p-4 md:py-6">
        <!-- Sem permissão: fechamento é ritual do gerente. -->
        <OperatorScreenState
          v-if="accessDenied"
          state="empty"
          icon="i-lucide-lock"
          title="Fechamento é do gerente"
          description="Sua conta não tem permissão para realizar o fechamento do dia. Chame quem cuida do encerramento."
        >
          <template #actions>
            <NuxtButton color="neutral" variant="outline" icon="i-lucide-arrow-left" label="Voltar à sessão de caixa" to="/session" />
          </template>
        </OperatorScreenState>

        <template v-else-if="closing">
          <NuxtAlert
            v-if="closing.already_closed"
            color="success"
            variant="subtle"
            icon="i-lucide-circle-check"
            title="Dia fechado"
            :description="closing.existing_closing_display"
          />

          <!-- Fim de dia encadeado: registrado o fechamento, o próximo passo vem
               até a mão. Relatório só para quem audita: porta que bateria na
               cara não é oferta. -->
          <NuxtCard v-if="justClosedDay && closing.already_closed">
            <div class="grid gap-3">
              <p class="op-body text-muted-foreground">
                Fechamento registrado. O quadro do dia está logo abaixo.
              </p>
              <div class="grid gap-2 sm:grid-cols-2">
                <NuxtButton
                  v-if="canAuditCash"
                  color="neutral"
                  variant="outline"
                  block
                  icon="i-lucide-receipt-text"
                  label="Ver relatório de caixa"
                  to="/session/report"
                />
                <NuxtButton
                  color="neutral"
                  variant="outline"
                  block
                  icon="i-lucide-arrow-left"
                  label="Voltar à sessão de caixa"
                  to="/session"
                />
              </div>
            </div>
          </NuxtCard>

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
              <NuxtTabs
                v-model="drawerMode"
                :items="drawerModes"
                :content="false"
                variant="pill"
                aria-label="Como contar"
                data-closing-drawer-mode
              />
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
            <NuxtInput
              v-if="drawerNoteOpen || drawerNote"
              v-model="drawerNote"
              size="xl"
              class="w-full"
              placeholder="Observação da contagem (ex.: nota rasgada separada)"
              aria-label="Observação da contagem da gaveta"
            />
            <p class="op-micro text-muted-foreground">
              <template v-if="drawerMode === 'denominations' && drawerMissing">Faltam {{ drawerMissing }} {{ drawerMissing === 1 ? "valor" : "valores" }}. Valor em branco conta como zero ao confirmar; o total se repete para você conferir.</template>
              <template v-else>O total se repete para você conferir antes de fechar.</template>
            </p>
            <NuxtButton
              class="justify-self-start"
              color="neutral"
              variant="ghost"
              label="Contar a vitrine primeiro"
              data-closing-skip-cash
              @click="step = 'count'"
            />
          </section>

          <!-- BLOQUEIO, antes da contagem. Diz QUANTAS ordens faltam e para onde
               ir; não diz SKU nem quantidade, que é o que entregaria a resposta.
               A tabela completa aparece depois que a contagem é registrada. -->
          <NuxtAlert
            v-if="!closing.already_closed && closing.has_pending_production && step !== 'cash'"
            color="warning"
            variant="subtle"
            icon="i-lucide-triangle-alert"
            title="Produção em aberto"
          >
            <template #description>
              <span class="grid gap-1">
                <span>
                  {{ closing.pending_production.length === 1
                    ? "Uma ordem de produção ainda está aberta."
                    : `${closing.pending_production.length} ordens de produção ainda estão abertas.` }}
                  Conclua ou estorne antes de encerrar o dia.
                </span>
                <!-- A contagem é CEGA: aqui o link não pode apontar para uma ordem,
                     porque a ordem carrega SKU. Leva à grade da Produção no dia do
                     bloqueio mais velho, e o rótulo promete só isso. -->
                <a
                  v-if="productionGrid"
                  class="font-semibold underline underline-offset-4"
                  :href="productionGrid"
                  v-bind="attrsFor(productionGrid)"
                  data-production-link
                >Abrir a Produção</a>
              </span>
            </template>
          </NuxtAlert>

          <!-- Produção pendente -->
          <section v-if="closing.already_closed && closing.has_pending_production" class="grid gap-2" aria-labelledby="pending-production-title">
            <div class="flex items-center gap-2">
              <h2 id="pending-production-title" class="op-title">Produção pendente</h2>
              <NuxtBadge color="warning" :label="String(closing.pending_production.length)" />
            </div>
            <p class="text-sm text-muted-foreground">
              Ordens que seguiam abertas quando o dia foi encerrado. Elas ficaram registradas neste fechamento; toque na ordem para abri-la na Produção.
            </p>
            <OperatorTable
              :data="closing.pending_production"
              :columns="pendingColumns"
              :row-key="(row) => row.ref"
              caption="Ordens de produção pendentes no fechamento"
            >
              <!-- O `ref` na tela É o caminho: o link abre a Produção no dia
                   da ordem, já filtrada por ela. -->
              <template #ref-cell="{ row }">
                <a
                  v-if="workOrderHref(row.original)"
                  class="font-medium whitespace-nowrap underline underline-offset-4"
                  :href="workOrderHref(row.original)"
                  v-bind="attrsFor(workOrderHref(row.original))"
                  :aria-label="`Abrir a ordem ${row.original.ref} na Produção`"
                  data-work-order-link
                >{{ row.original.ref }}</a>
                <span v-else class="font-medium">{{ row.original.ref }}</span>
              </template>
              <template #status-cell="{ row }">
                <span :class="row.original.is_overdue ? 'text-error' : ''">{{ pendingStatusDisplay(row.original) }}</span>
              </template>
            </OperatorTable>
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
          <section v-if="closing.already_closed" class="grid gap-2" aria-labelledby="day-production-title">
            <h2 id="day-production-title" class="op-title">Produção do dia</h2>
            <p v-if="!dayProduction.length" class="text-sm text-muted-foreground">Sem produção registrada hoje.</p>
            <OperatorTable
              v-else
              :data="dayProduction"
              :columns="productionColumns"
              :row-key="(row) => row.sku"
              caption="Produção do dia"
            />
          </section>

          <!-- Encomendas dos próximos dias -->
          <section v-if="closing.already_closed && closing.has_upcoming_preorders" class="grid gap-2" aria-labelledby="upcoming-title">
            <div class="flex items-center gap-2">
              <h2 id="upcoming-title" class="op-title">Encomendas para os próximos dias</h2>
              <NuxtBadge color="neutral" :label="String(closing.upcoming_preorders.length)" />
            </div>
            <p class="text-sm text-muted-foreground">
              Todas as encomendas confirmadas ou a confirmar com data depois de hoje, qualquer que seja o dia em que foram feitas. Saem do estoque na data combinada.
            </p>
            <OperatorTable
              :data="closing.upcoming_preorders"
              :columns="preorderColumns"
              :row-key="(row) => row.date"
              caption="Encomendas para os próximos dias"
            />
          </section>

          <!-- Discrepâncias -->
          <section v-if="closing.already_closed && closing.reconciliation_errors.length" class="grid gap-2" aria-labelledby="discrepancies-title">
            <h2 id="discrepancies-title" class="op-title text-error">Discrepâncias detectadas</h2>
            <OperatorTable
              :data="closing.reconciliation_errors"
              :columns="discrepancyColumns"
              :row-key="(row) => row.sku"
              caption="Discrepâncias entre vendido e disponível"
            >
              <template #deficit-cell="{ row }">
                <span class="text-error">{{ row.original.deficit_qty }}</span>
              </template>
            </OperatorTable>
          </section>

          <!-- PASSO 2: contar a vitrine (CONFERÊNCIA cega, por produto). -->
          <NuxtCard v-if="closing.already_closed || step === 'count'" data-closing-count>
            <div class="grid gap-3">
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
                  class="flex items-center gap-3 rounded-lg px-3 py-2 transition"
                  :class="/^\d+$/.test((quantities[item.sku] ?? '').trim()) ? 'bg-elevated' : 'bg-muted/40'"
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
                  <NuxtInput
                    :model-value="quantities[item.sku]"
                    size="xl"
                    inputmode="numeric"
                    enterkeyhint="next"
                    class="w-24 shrink-0"
                    :ui="{ base: 'text-right tabular-nums font-semibold' }"
                    :disabled="closing.already_closed || submitting"
                    :aria-label="`Sobras de ${item.name}`"
                    data-count-input
                    @update:model-value="setQuantity(item.sku, String($event ?? ''))"
                    @keydown.enter.prevent="focusNextCount(index)"
                  />
                </div>
              </div>
              <!-- Na mesa o gesto está no cabeçalho; o motivo de ele não poder ainda
                   fica escrito aqui, onde se conta. No celular quem diz é a base. -->
              <p
                v-if="bar?.kind === 'count' && barReason"
                class="op-micro text-muted-foreground max-lg:hidden"
                role="status"
                data-closing-count-reason
              >
                {{ barReason }}
              </p>
            </div>
          </NuxtCard>

          <!-- PASSO 3: o dia, depois de contado. Às cegas até o fim, para todos: peças,
               estados e a pergunta do dia estranho; nunca reais. -->
          <template v-if="!closing.already_closed && step === 'day'">
            <h2 class="op-heading" data-closing-day>O dia, depois de contado</h2>
            <div class="grid gap-3 md:grid-cols-2">
              <NuxtCard data-closing-cash>
                <div class="grid content-start gap-2">
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
                  <NuxtButton v-if="cashOpen" color="neutral" variant="outline" label="Fechar caixa" @click="goToCloseCash" />
                </div>
              </NuxtCard>
              <NuxtCard data-closing-showcase>
                <div class="grid content-start gap-2">
                  <p class="flex items-center gap-1.5 op-eyebrow text-muted-foreground"><Icon name="lucide:store" class="size-3.5" />Vitrine</p>
                  <dl class="grid gap-1.5 op-body">
                    <div class="flex justify-between gap-2"><dt class="text-muted-foreground">Ficam para amanhã</dt><dd class="op-title tnum">{{ piecesLabel(summary.keep) }}</dd></div>
                    <div class="flex justify-between gap-2"><dt class="text-muted-foreground">Viram perda</dt><dd class="op-title tnum">{{ piecesLabel(summary.loss) }}</dd></div>
                    <div v-if="summary.mixed" class="flex justify-between gap-2"><dt class="text-muted-foreground">Lote misto (parte vence)</dt><dd class="op-title tnum">{{ piecesLabel(summary.mixed) }}</dd></div>
                  </dl>
                  <NuxtButton
                    v-if="biggestLeftover"
                    color="neutral"
                    variant="outline"
                    block
                    trailing-icon="i-lucide-chevron-right"
                    :label="`Maior sobra: ${biggestLeftover.name} (${biggestLeftover.qty}) · Ver tudo`"
                    :ui="{ label: 'text-clip whitespace-normal text-left' }"
                    data-closing-biggest
                    @click="step = 'count'"
                  />
                  <NuxtButton
                    v-else
                    class="justify-self-start"
                    color="primary"
                    variant="ghost"
                    label="Voltar à contagem"
                    @click="step = 'count'"
                  />
                </div>
              </NuxtCard>
            </div>

            <NuxtCard data-closing-production>
              <div class="flex items-center gap-3">
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
                <NuxtBadge color="neutral" icon="i-lucide-sparkles" label="automático" />
              </div>
            </NuxtCard>

            <!-- EXPLICAR O DIA ESTRANHO: só aparece quando o sistema notou um sinal. A
                 resposta marca o dia (o plano e o B.I. não aprendem com ele). -->
            <NuxtCard
              v-for="episode in closing.pending_episodes || []"
              :key="episode.id"
              class="ring-2 ring-primary/60"
              data-closing-episode
            >
              <div class="grid gap-3">
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
                  <NuxtButton
                    v-for="option in closing.episode_options || []"
                    :key="option.ref"
                    size="xl"
                    :color="episodeChoice[episode.id] === option.ref ? 'primary' : 'neutral'"
                    :variant="episodeChoice[episode.id] === option.ref ? 'soft' : 'outline'"
                    :icon="episodeChoice[episode.id] === option.ref ? 'i-lucide-check' : undefined"
                    :label="option.label"
                    :aria-pressed="episodeChoice[episode.id] === option.ref"
                    :title="option.hint || undefined"
                    :disabled="answering !== null"
                    @click="sendEpisode(episode.id, option.ref)"
                  />
                  <NuxtButton
                    size="xl"
                    color="neutral"
                    variant="ghost"
                    label="Não houve nada"
                    :disabled="answering !== null"
                    @click="sendEpisode(episode.id, '')"
                  />
                </div>
                <NuxtInput
                  v-model="episodeNote[episode.id]"
                  size="xl"
                  class="w-full"
                  placeholder="Detalhe, se quiser (ex.: temporal às 14h, rua alagada)"
                  :aria-label="`Detalhe do que houve: ${episode.signal}`"
                />
                <p class="flex items-start gap-1.5 op-micro text-muted-foreground">
                  <Icon name="lucide:chart-no-axes-column" class="mt-0.5 size-3.5 shrink-0" />
                  A resposta marca o dia: a projeção e a sugestão do plano não aprendem com um dia assim como se fosse normal.
                </p>
              </div>
            </NuxtCard>

            <!-- A consequência do selo, escrita antes do toque. -->
            <p class="op-micro text-muted-foreground">Não reabre: um fechamento por dia. Sobras entram como estoque de ontem, perdas saem pelo lote.</p>
          </template>
        </template>

        <OperatorScreenState v-else-if="pending" state="loading" what="o fechamento do dia" />
      </div>
    </div>

    <!-- No celular, o gesto do passo na base (`OperatorActionBar`), em fluxo depois da
         região que rola; na mesa ele está no cabeçalho. -->
    <OperatorActionBar
      v-if="bar"
      :action="bar.action"
      :secondary="bar.secondary"
      label="Gesto do fim do dia"
      :data-closing-bar="bar.kind"
    />
  </main>
</template>
