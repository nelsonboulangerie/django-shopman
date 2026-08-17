<script setup lang="ts">
// ANTESALA do PDV (benchmark Odoo POS): a tela de SESSÃO antes da venda. O
// operador abre o caixa (fundo de troco), registra sangria/suprimento e
// fecha o turno (contagem cega) aqui — não mais num diálogo espremido dentro da
// tela de venda. Sem turno aberto, a tela de venda redireciona para cá; com
// turno, o CTA "Continuar vendendo" leva de volta. BLIND: a antesala nunca
// mostra o valor esperado da gaveta — a conferência (esperado vs contado) fica
// no retaguarda. O fechamento do DIA (sobras/perdas) entra em `/session/closing`.
import {
  canRegisterMovement,
  formatOpenedAt,
  movementLabel,
  movementReasons,
  sessionScreenState,
} from "~/presentation/cash";
import type { DayClosingResponse } from "~/types/closing";

useHead({ title: "Sessão de caixa · Shopman POS" });

const action = usePosAction();
const { pos, shift, actions, pending, refresh } = await usePosTerminal();

const OPERATOR_PERM = "backstage.operate_pos";
const { operator: activeOperator, lock } = useOperatorLock(OPERATOR_PERM);

const {
  busy,
  movementKinds,
  managerChallenge,
  openCashShift,
  closeCashShift,
  closeBlockingShift,
  registerCashMovement,
  canOpenDrawer,
  drawerUnavailableReason,
  drawerProbing,
  openDrawerWithoutSale,
  probeDrawer,
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
const openedAtDisplay = computed(() => formatOpenedAt(cashRuntime.value?.opened_at));
const salesCount = computed(() => shift.value?.count ?? 0);

// Abrir caixa → direto para a venda (o motivo de estar na antesala acabou).
const openingAmount = ref("");
async function submitOpen() {
  const ok = await openCashShift(openingAmount.value);
  if (ok) await navigateTo("/");
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
// Escolhido e digitado são campos SEPARADOS, e um limpa o outro no ato: com um
// só, a tela mostraria dois motivos ao mesmo tempo e mandaria um deles calada.
const movementReasonPick = ref("");
const movementReasonOther = ref("");
const movementReasonOptions = computed(() => movementReasons(movementKind.value));
const movementReason = computed(() => movementReasonPick.value || movementReasonOther.value.trim());
const canSubmitMovement = computed(
  () => canRegisterMovement(movementKind.value, movementAmount.value, movementReason.value),
);

// Trocar de tipo zera o motivo: "Cofre" faz sentido numa sangria e nenhum num
// suprimento. Motivo herdado do tipo anterior entraria na trilha como mentira.
function pickMovementKind(kind: string) {
  movementKind.value = kind;
  clearMovementReason();
}

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
// Retirada de gaveta precisa da segunda assinatura: o servidor recusa com
// `manager_approval_required`, o diálogo sobe e o mesmo movimento é reenviado
// com o PIN. O `managerChallenge` reabre o diálogo quando o PIN vem errado.
const managerAuthOpen = ref(false);
watch(managerChallenge, (challenge) => { if (challenge) managerAuthOpen.value = true; });

async function submitMovement(managerApproval: { username: string; pin: string } | null = null) {
  if (!canSubmitMovement.value) return;
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
  }
}

function onMovementAuthorize(username: string, pin: string) {
  managerAuthOpen.value = false;
  submitMovement({ username, pin });
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
  if (ok) drawerReason.value = "";
}

// Teste de gaveta: a sonda só alcança a FILA do sistema. Se a gaveta está
// plugada na impressora, ou se abriu, quem confirma é o olho do operador.
const drawerProbeResult = ref<{ ok: boolean; message: string } | null>(null);
async function testDrawer() {
  drawerProbeResult.value = await probeDrawer();
  if (drawerProbeResult.value.ok) await openDrawerWithoutSale("Teste de gaveta");
}

// Fechar caixa (contagem cega) — destrutivo, exige confirmação explícita.
const closingAmount = ref("");
const closingNotes = ref("");
const confirmingClose = ref(false);
async function confirmClose() {
  const ok = await closeCashShift({ amount: closingAmount.value, notes: closingNotes.value });
  confirmingClose.value = false;
  if (ok) {
    closingAmount.value = "";
    closingNotes.value = "";
  }
}

// Fechamento cego do turno BLOQUEANTE (gerente ou dono destrava o terminal).
const blockingAmount = ref("");
const blockingNotes = ref("");
const confirmingBlocking = ref(false);
async function confirmCloseBlocking() {
  const shiftId = cashRuntime.value?.blocking_shift_id;
  if (!shiftId) return;
  const ok = await closeBlockingShift({
    shift_id: shiftId,
    amount: blockingAmount.value,
    notes: blockingNotes.value,
  });
  confirmingBlocking.value = false;
  if (ok) {
    blockingAmount.value = "";
    blockingNotes.value = "";
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
      @board="navigateTo('/')"
      @cash="() => {}"
      @lock="lock()"
      @refresh="refresh()"
    />

    <div class="flex min-w-0 flex-1 flex-col md:min-h-0 md:overflow-hidden">
      <header class="flex shrink-0 items-center gap-3 border-b border-border bg-card px-4 py-2">
        <RailToggle />
        <h1 class="min-w-0 truncate text-lg font-semibold leading-tight tracking-tight">Sessão de caixa</h1>
        <span v-if="pos" class="ml-auto truncate text-sm text-muted-foreground">
          {{ pos.terminal_label || "Terminal" }}
          <template v-if="screen === 'open'"> · {{ activeOperator?.name || cashRuntime?.operator_username }}</template>
        </span>
      </header>

      <div class="flex-1 md:min-h-0 md:overflow-y-auto">
        <div class="mx-auto grid w-full max-w-xl gap-4 p-4 md:py-8">
          <!-- Terminal ocupado: turno aberto por outro operador -->
          <section v-if="screen === 'occupied'" class="grid gap-2 rounded-lg border border-warning/40 bg-warning/10 p-4">
            <div class="flex items-center gap-2">
              <Icon name="lucide:lock" class="size-4 text-amber-700" />
              <p class="text-sm font-semibold text-amber-800">Terminal ocupado</p>
            </div>
            <p class="text-sm text-amber-800">
              Turno aberto por <strong>{{ cashRuntime?.blocking_operator_username }}</strong>
              <template v-if="cashRuntime?.blocking_shift_id"> (turno #{{ cashRuntime.blocking_shift_id }})</template>.
            </p>
            <p v-if="cashRuntime?.blocking_message" class="text-xs text-amber-700">{{ cashRuntime.blocking_message }}</p>

            <!-- Gerente ou dono do turno: fecha (contagem cega) e libera o terminal aqui mesmo. -->
            <template v-if="cashRuntime?.can_close_blocking">
              <div v-if="!confirmingBlocking" class="mt-1">
                <UiButton variant="outline" size="sm" class="w-full border-warning/50 text-amber-800 hover:bg-warning/10" :disabled="busy" @click="confirmingBlocking = true">
                  Fechar turno #{{ cashRuntime.blocking_shift_id }} (contagem cega)
                </UiButton>
              </div>
              <div v-else class="mt-1 grid gap-2 rounded-md border border-warning/40 bg-background p-3">
                <div class="flex items-start gap-2 text-xs text-muted-foreground">
                  <Icon name="lucide:eye-off" class="mt-0.5 size-4 shrink-0" />
                  <span>Contagem cega: conte o dinheiro do caixa e informe o valor. A conferência fica no gestor.</span>
                </div>
                <label class="grid gap-1 text-sm">
                  <span class="font-medium text-muted-foreground">Valor contado</span>
                  <UiInput v-model="blockingAmount" inputmode="decimal" placeholder="0,00" />
                </label>
                <label class="grid gap-1 text-sm">
                  <span class="font-medium text-muted-foreground">Observações</span>
                  <UiTextarea v-model="blockingNotes" :rows="2" placeholder="Motivo (turno órfão, troca de operador…)" />
                </label>
                <div class="grid grid-cols-2 gap-2">
                  <UiButton variant="outline" :disabled="busy" @click="confirmingBlocking = false">Cancelar</UiButton>
                  <UiButton variant="destructive" :disabled="busy" :loading="busy" @click="confirmCloseBlocking">
                    Fechar e liberar
                  </UiButton>
                </div>
              </div>
            </template>
            <p v-else class="text-xs text-muted-foreground">
              Só o gerente ou o operador dono do turno pode fechá-lo. Chame o gerente ou feche no gestor.
            </p>
          </section>

          <!-- Caixa fechado: abrir turno -->
          <section v-else-if="screen === 'closed'" class="grid gap-3 rounded-lg border bg-card p-4">
            <div class="grid gap-1">
              <h2 class="text-base font-semibold">Abrir caixa</h2>
              <p class="text-sm text-muted-foreground">
                Abra o caixa antes de vender. Informe o valor de abertura (fundo de troco).
              </p>
            </div>
            <label class="grid gap-1 text-sm">
              <span class="font-medium text-muted-foreground">Valor de abertura</span>
              <UiInput v-model="openingAmount" inputmode="decimal" placeholder="0,00" @keydown.enter="submitOpen" />
            </label>
            <UiButton size="lg" :disabled="busy" :loading="busy" @click="submitOpen">
              <Icon name="lucide:wallet" class="size-5" />
              Abrir caixa e vender
            </UiButton>
          </section>

          <!-- Turno aberto: status (cego), continuar, movimentos, fechamento -->
          <template v-else>
            <section class="grid gap-3 rounded-lg border bg-card p-4">
              <div class="grid grid-cols-2 gap-2 rounded-md border bg-muted/40 p-3 text-sm">
                <div class="flex flex-col">
                  <span class="text-xs text-muted-foreground">Aberto em</span>
                  <span class="font-medium tabular-nums">{{ openedAtDisplay }}</span>
                </div>
                <div class="flex flex-col">
                  <span class="text-xs text-muted-foreground">Vendas hoje</span>
                  <span class="font-medium tabular-nums">{{ salesCount }}</span>
                </div>
              </div>
              <UiButton size="lg" @click="navigateTo('/')">
                <Icon name="lucide:shopping-basket" class="size-5" />
                Continuar vendendo
              </UiButton>
            </section>

            <section class="grid gap-3 rounded-lg border bg-card p-4">
              <h2 class="text-base font-semibold">Movimento de caixa</h2>
              <div class="grid gap-1.5">
                <span id="movement-kind-label" class="text-sm font-medium text-muted-foreground">Tipo</span>
                <div class="grid grid-cols-3 gap-2" role="group" aria-labelledby="movement-kind-label">
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
                <UiInput v-model="movementAmount" inputmode="decimal" placeholder="0,00" />
              </label>

              <!-- Motivo obrigatório, em botões. O digitado fica como saída para o
                   que não estava previsto, e é o único caminho quando o tipo não
                   tem opções conhecidas. -->
              <div v-if="movementKind" class="grid gap-1.5">
                <span id="movement-reason-label" class="text-sm font-medium text-muted-foreground">
                  Motivo (obrigatório)
                </span>
                <div
                  v-if="movementReasonOptions.length"
                  class="grid grid-cols-2 gap-2 sm:grid-cols-4"
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
                variant="outline"
                size="sm"
                :disabled="busy || !canSubmitMovement"
                @click="submitMovement()"
              >
                Registrar movimento
              </UiButton>
            </section>

            <!-- Gaveta: só aparece onde existe caminho de software. Num balcão
                 de gaveta com chave, um botão que não abre nada seria pior que
                 botão nenhum. -->
            <section class="grid gap-2 rounded-lg border bg-card p-4">
              <div class="flex items-center gap-2">
                <Icon name="lucide:archive" class="size-4 text-muted-foreground" />
                <h2 class="text-base font-semibold">Abrir gaveta</h2>
              </div>

              <!-- Sem caminho de software o card DIZ por que, em vez de sumir.
                   Sumir calado fez o dono procurar um botão que nunca ia
                   aparecer, achando que o PDV estava quebrado. -->
              <p v-if="!canOpenDrawer" class="text-sm text-muted-foreground">
                {{ drawerUnavailableReason }}
              </p>

              <template v-else>
              <p class="text-sm text-muted-foreground">
                Abrir sem venda fica registrado no turno: quem abriu, quando e por quê.
              </p>
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
                <UiButton variant="ghost" size="sm" :disabled="busy || drawerProbing" :loading="drawerProbing" @click="testDrawer">
                  <Icon name="lucide:stethoscope" class="size-4" />
                  Testar gaveta
                </UiButton>
                <p v-if="drawerProbeResult" class="text-xs" :class="drawerProbeResult.ok ? 'text-muted-foreground' : 'text-destructive'">
                  <template v-if="drawerProbeResult.ok">
                    {{ drawerProbeResult.message }} A gaveta abriu? Se não abriu, confira o cabo dela na impressora.
                  </template>
                  <template v-else>{{ drawerProbeResult.message }}</template>
                </p>
              </div>
              </template>
            </section>

            <section class="grid gap-2 rounded-lg border bg-card p-4">
              <h2 class="text-base font-semibold">Fechar caixa</h2>
              <div class="flex items-start gap-2 rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground">
                <Icon name="lucide:eye-off" class="mt-0.5 size-4 shrink-0" />
                <span>Contagem cega: conte o dinheiro do caixa e informe o valor. A conferência fica no gestor.</span>
              </div>
              <label class="grid gap-1 text-sm">
                <span class="font-medium text-muted-foreground">Valor contado</span>
                <UiInput v-model="closingAmount" inputmode="decimal" placeholder="0,00" />
              </label>
              <label class="grid gap-1 text-sm">
                <span class="font-medium text-muted-foreground">Observações</span>
                <UiTextarea v-model="closingNotes" :rows="2" placeholder="Conferência, divergências" />
              </label>
              <div v-if="!confirmingClose">
                <UiButton variant="destructive" class="w-full" :disabled="busy" @click="confirmingClose = true">
                  Fechar caixa
                </UiButton>
              </div>
              <div v-else class="grid gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3">
                <p class="text-sm font-medium">Confirmar fechamento do caixa? Esta ação encerra o turno.</p>
                <div class="grid grid-cols-2 gap-2">
                  <UiButton variant="outline" :disabled="busy" @click="confirmingClose = false">Cancelar</UiButton>
                  <UiButton variant="destructive" :disabled="busy" :loading="busy" @click="confirmClose">
                    Confirmar
                  </UiButton>
                </div>
              </div>
            </section>
          </template>

          <!-- Relatório de caixa: leituras X/Z e histórico de turnos do dia. -->
          <section class="grid gap-2 rounded-lg border bg-card p-4">
            <div class="flex items-center gap-2">
              <Icon name="lucide:receipt-text" class="size-4 text-muted-foreground" />
              <h2 class="text-base font-semibold">Relatório de caixa</h2>
            </div>
            <p class="text-sm text-muted-foreground">
              Leitura X do turno aberto, leituras Z dos turnos fechados e o histórico do dia.
            </p>
            <UiButton variant="outline" @click="navigateTo('/session/report')">
              Ver relatório
            </UiButton>
          </section>

          <!-- Fechamento do DIA (gerente): contagem cega de sobras/perdas. -->
          <section v-if="dayClosing" class="grid gap-2 rounded-lg border bg-card p-4">
            <div class="flex items-center gap-2">
              <Icon name="lucide:clipboard-check" class="size-4 text-muted-foreground" />
              <h2 class="text-base font-semibold">Fechamento do dia</h2>
            </div>
            <p class="text-sm text-muted-foreground">
              <template v-if="dayClosing.already_closed">{{ dayClosing.existing_closing_display }}</template>
              <template v-else>{{ dayClosing.today_display }} · contagem cega de sobras e perdas.</template>
            </p>
            <UiButton variant="outline" @click="navigateTo('/session/closing')">
              {{ dayClosing.already_closed ? "Ver fechamento" : "Fazer o fechamento" }}
            </UiButton>
          </section>
        </div>
      </div>
    </div>

    <PosManagerAuthDialog
      v-model:open="managerAuthOpen"
      reason-text="Retirar dinheiro da gaveta é exceção auditada: um gerente precisa autorizar."
      :managers="pos?.managers || []"
      :busy="busy"
      :error="managerChallenge?.code === 'manager_approval_invalid' ? managerChallenge.message : ''"
      @authorize="onMovementAuthorize"
    />
  </main>
</template>
