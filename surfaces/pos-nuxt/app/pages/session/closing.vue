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
  countedItems,
  firstUnfilledItemName,
  pendingStatusDisplay,
  productionRows,
  sanitizeQtyInput,
} from "~/presentation/closing";
import { oldestPendingDate, productionGridUrl, productionWorkOrderUrl } from "~/presentation/crossAppLinks";
import type { ClosingPendingProduction } from "~/types/closing";

useHead({ title: "Fechamento do dia" });

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
const { pos } = await usePosTerminal();
const canAuditCash = computed(() => pos.value?.cash_runtime?.can_audit_cash === true);

const { closing, pending, accessDenied, submitting, submit } = await useDayClosing({ action });

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
  <main class="min-h-dvh bg-background text-foreground">
    <header class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2">
      <UiButton
        variant="ghost"
        size="icon-sm"
        aria-label="Voltar à sessão de caixa"
        title="Sessão de caixa"
        @click="goToCashSession"
      >
        <Icon name="lucide:arrow-left" class="size-5" />
      </UiButton>
      <h1 class="min-w-0 truncate text-lg font-semibold">Fechamento do dia</h1>
      <span v-if="closing" class="ml-auto truncate text-sm text-muted-foreground">
        {{ closing.today_display }} · contagem cega do que a casa produz
      </span>
    </header>

    <div class="mx-auto grid w-full max-w-2xl gap-4 p-4 md:py-8">
      <!-- Sem permissão: fechamento é ritual do gerente. -->
      <section v-if="accessDenied" class="grid gap-2 rounded-md border bg-card p-4">
        <div class="flex items-center gap-2">
          <Icon name="lucide:lock" class="size-4 text-muted-foreground" />
          <h2 class="text-base font-semibold">Fechamento é do gerente</h2>
        </div>
        <p class="text-sm text-muted-foreground">
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
             até a mão. Relatório só para quem audita — porta que bateria na
             cara não é oferta. -->
        <section v-if="justClosedDay && closing.already_closed" class="grid gap-2 rounded-md border bg-card p-4">
          <p class="text-sm text-muted-foreground">
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

        <!-- BLOQUEIO, antes da contagem. Diz QUANTAS ordens faltam e para onde
             ir; não diz SKU nem quantidade, que é o que entregaria a resposta.
             A tabela completa aparece depois que a contagem é registrada. -->
        <section
          v-if="!closing.already_closed && closing.has_pending_production"
          class="grid gap-2 rounded-md border border-warning/40 bg-warning/10 p-4"
        >
          <div class="flex items-center gap-2">
            <Icon name="lucide:triangle-alert" class="size-4 text-warning" />
            <h2 class="text-base font-semibold">Produção em aberto</h2>
          </div>
          <p class="text-sm text-muted-foreground">
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
            class="text-sm font-medium underline underline-offset-4"
            :href="productionGrid"
            v-bind="attrsFor(productionGrid)"
            data-production-link
          >
            Abrir a Produção
          </a>
        </section>

        <!-- Produção pendente -->
        <section v-if="closing.already_closed && closing.has_pending_production" class="grid gap-2 rounded-md border bg-card p-4">
          <div class="flex items-center gap-2">
            <h2 class="text-base font-semibold">Produção pendente</h2>
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
        <section v-if="closing.already_closed" class="grid gap-2 rounded-md border bg-card p-4">
          <h2 class="text-base font-semibold">Produção do dia</h2>
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
        <section v-if="closing.already_closed && closing.has_upcoming_preorders" class="grid gap-2 rounded-md border bg-card p-4">
          <div class="flex items-center gap-2">
            <h2 class="text-base font-semibold">Encomendas para os próximos dias</h2>
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
                  <th class="py-1.5 pr-3 font-medium">Pedidos</th>
                  <th class="py-1.5 font-medium">Total</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in closing.upcoming_preorders" :key="row.date" class="border-b border-border/60 last:border-0">
                  <td class="py-1.5 pr-3">{{ row.date_display }}</td>
                  <td class="py-1.5 pr-3 tabular-nums">{{ row.orders_count }}</td>
                  <td class="py-1.5 tabular-nums">{{ row.total_display }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <!-- Discrepâncias -->
        <section v-if="closing.already_closed && closing.reconciliation_errors.length" class="grid gap-2 rounded-md border border-destructive/40 bg-card p-4">
          <h2 class="text-base font-semibold text-destructive">Discrepâncias detectadas</h2>
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

        <!-- Contagem final (cega) -->
        <section class="grid gap-2 rounded-md border bg-card p-4">
          <div class="flex items-baseline justify-between gap-2">
            <h2 class="text-base font-semibold">Contagem final</h2>
            <span
              v-if="closing.has_items && !closing.already_closed"
              class="text-sm tabular-nums text-muted-foreground"
              data-count-progress
            >{{ countedTotal }} de {{ countItems.length }} contados</span>
          </div>
          <p class="text-sm text-muted-foreground">
            Conte o que sobrou do que a casa produz — revenda não entra. Nada sobrou? Digite 0.
            O sistema trata destino e perdas.
          </p>
          <p v-if="!closing.has_items" class="text-sm text-muted-foreground">Nada produzido na casa em estoque para contar.</p>
          <div v-else ref="countList" class="grid gap-1.5">
            <div
              v-for="(item, index) in countItems"
              :key="item.sku"
              class="flex items-center gap-3 rounded-md border border-border/60 px-3 py-2"
            >
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-medium">{{ item.name }}</p>
                <p class="text-xs text-muted-foreground">{{ item.sku }}</p>
              </div>
              <span
                class="inline-flex shrink-0 items-center rounded-md border px-1.5 py-0.5 text-xs font-medium"
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
                class="h-11 w-20 text-right text-base tabular-nums"
                :disabled="closing.already_closed || submitting"
                :aria-label="`Sobras de ${item.name}`"
                data-count-input
                @update:model-value="setQuantity(item.sku, $event)"
                @keydown.enter.prevent="focusNextCount(index)"
              />
            </div>
          </div>

          <template v-if="closing.has_items && !closing.already_closed">
            <!-- Preso ao pé da tela: o botão acompanha a lista. -->
            <div
              v-if="!confirming"
              class="sticky bottom-0 -mx-4 -mb-4 mt-1 border-t bg-card/95 px-4 py-3 backdrop-blur"
            >
              <UiButton ref="registerButton" size="lg" class="w-full" :disabled="!canSubmit || submitting" @click="confirming = true">
                <Icon name="lucide:clipboard-check" class="size-5" />
                Registrar contagem final
              </UiButton>
              <!-- A dica aponta o item, não "todos": procurar um campo vazio
                   numa lista aparentemente preenchida era a parte difícil. -->
              <p v-if="!canSubmit" class="mt-1.5 text-xs text-muted-foreground">
                <template v-if="unfilledItemName">Falta a contagem de {{ unfilledItemName }}.</template>
                <template v-else>Preencha a contagem de todos os itens para registrar.</template>
              </p>
            </div>
            <div v-else class="sticky bottom-0 mt-1 grid gap-2 rounded-md border border-destructive/40 bg-card p-3 shadow-lg">
              <p class="text-sm font-medium">
                Confirmar o fechamento do dia {{ closing.today_display }}? Sobras viram "Ontem" ou perda e a contagem é registrada.
              </p>
              <div class="grid grid-cols-2 gap-2">
                <UiButton variant="outline" :disabled="submitting" @click="confirming = false">Cancelar</UiButton>
                <UiButton variant="destructive" :disabled="submitting" :loading="submitting" @click="confirmSubmit">
                  Confirmar fechamento
                </UiButton>
              </div>
            </div>
          </template>
        </section>
      </template>

      <section v-else-if="pending" class="grid place-items-center rounded-md border bg-card p-8">
        <Icon name="line-md:loading-loop" class="size-6 text-muted-foreground" />
      </section>
    </div>
  </main>
</template>
