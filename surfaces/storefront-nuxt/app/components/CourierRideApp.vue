<script setup lang="ts">
// A página do entregador da casa em HIPERFOCO (DEV-2026-030, M2). Telas aprovadas pelo dono
// em 16/11/2026: plano `docs/plans/DELIVERY-MULTI-SERVICE-PLAN.md` §4.5.2, prévia
// `/preview-multisservico/5` (#2511).
//
// A linguagem é fechada, e a auditoria do PR a mede na tela real:
//   · texto em 3 tamanhos só: grande 1.75rem/800, normal 1.125rem/500, pequeno 0.9375rem/500
//     (rem: acompanham a fonte do celular);
//   · paleta própria e neutra (`--cr-*`), texto sempre preto ou branco, sem borda nem fio;
//   · código do pedido sempre no mesmo badge, na linha de cima, nunca ao lado de um título;
//   · tudo à esquerda; centralizado só o texto de botão; um botão principal por tela, preso
//     no rodapé; a cor da rota só no quadrado da letra.
// Hiperfoco é sagrado: tema e "Adicionar à tela inicial" moram só na tela inicial.
import {
  type CourierStop,
  type ProblemKind,
  PROBLEM_CASES,
  THEME_CHOICES,
  bagTip,
  bagsText,
  closedTitle,
  doorMoney,
  doorPlace,
  earnedText,
  money,
  mapsUrl,
  nextStop,
  openStops,
  paymentChoices,
  pickupBlocks,
  problemNote,
  quoted,
  refusalText,
  remainingText,
  rideName,
  rideTone,
  screenFor,
  settleBlocks,
  showsSettings,
  telUrl,
  todayText,
  unseenCancelledStop,
  waitText,
  wazeUrl,
  UNDO_SECONDS
} from '~/presentation/courierRide'

const props = defineProps<{ token: string }>()
const token = computed(() => props.token)

const ride = useCourierRide(token)
const { theme, setTheme } = useCourierTheme()
const { plan: installPlanRef, install, isStandalone } = usePwaInstall()

const view = ride.view
const screen = computed(() => (props.token ? screenFor(view.value, ride.local.value) : 'home'))
const tone = computed(() => rideTone(view.value?.letter))
const stops = computed(() => view.value?.stops || [])
const remaining = computed(() => (view.value ? openStops(view.value).length : 0))
const driving = computed<CourierStop | null>(() => (view.value ? nextStop(view.value) : null))
const door = computed<CourierStop | null>(() => {
  const refs = [ride.pending.value?.orderRef, ride.local.value.arrivedRef, ride.local.value.noAnswerRef]
  return stops.value.find(stop => refs.includes(stop.ref)) || null
})
const doorBlocks = computed(() => (door.value ? doorMoney(door.value, view.value?.machine) : []))
const cancelledStop = computed(() => (view.value ? unseenCancelledStop(view.value, ride.local.value) : null))
const settle = computed(() => (view.value ? settleBlocks(view.value) : []))
const refusal = computed(() => (view.value ? refusalText(view.value) : { title: '', note: '' }))

// O Desfazer cobre a porta até vencer: a tela de trás continua a da entrega.
const showDoor = computed(() => screen.value === 'door' || Boolean(ride.pending.value))

// ── Folhas da porta ─────────────────────────────────────────────────────────
const sheet = ref<'' | 'problem' | 'payment' | 'install'>('')
function closeSheet () { sheet.value = '' }
async function chooseProblem (kind: ProblemKind) {
  if (kind === 'other_payment') {
    sheet.value = 'payment'
    return
  }
  const stop = door.value
  closeSheet()
  if (stop) await ride.problem(stop.ref, kind)
}
async function choosePayment (payment: string) {
  const stop = door.value
  closeSheet()
  if (stop) await ride.problem(stop.ref, 'other_payment', payment)
}

function delivered () {
  const stop = door.value
  if (stop) ride.deliver(stop.ref, stop.code)
}

// ── Fechada: o resumo fica um instante e a página volta à tela inicial ──────
let endTimer: ReturnType<typeof setTimeout> | null = null
watch(screen, (value) => {
  if (endTimer) clearTimeout(endTimer)
  if (value === 'closed') endTimer = setTimeout(() => ride.seeEnd(), 10_000)
})
onBeforeUnmount(() => { if (endTimer) clearTimeout(endTimer) })

// ── Tela inicial ────────────────────────────────────────────────────────────
const canInstall = computed(() => !isStandalone.value && installPlanRef.value.kind !== 'none')
const installSteps = computed(() => installPlanRef.value.steps.map(step => step.text.replace(/\*\*/g, '')))
const installing = ref(false)
async function addToHome () {
  if (installPlanRef.value.kind !== 'prompt') {
    sheet.value = 'install'
    return
  }
  installing.value = true
  try {
    await install()
  } finally {
    installing.value = false
  }
}
const greeting = computed(() => (view.value?.courier ? `Olá, ${view.value.courier.split(' ')[0]}` : 'Olá'))
const homeNote = computed(() => (view.value?.moment === 'reassigned'
  ? 'Esta rota passou para outra pessoa.'
  : 'Nenhuma corrida agora. A próxima chega pelo WhatsApp.'))

const wasOnRoute = computed(() => Boolean(ride.local.value.wasOnRoute))

// O tema vira atributo na raiz; "Do celular" segue o `prefers-color-scheme`.
const themeColor = ref('#ffffff')
function syncThemeColor () {
  if (!import.meta.client) return
  const dark = theme.value === 'dark' || (theme.value === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)
  themeColor.value = dark ? '#000000' : '#ffffff'
}
watch(theme, syncThemeColor)
onMounted(syncThemeColor)
useHead(() => ({ meta: [{ key: 'theme-color', name: 'theme-color', content: themeColor.value }] }))

const firstName = (stop: CourierStop | null) => stop?.name || ''
</script>

<template>
  <div class="cr" :data-theme="theme" :data-screen="screen">
    <!-- ══ Carregando ══ -->
    <div v-if="screen === 'loading'" class="cr-screen" aria-busy="true">
      <p class="cr-small">Abrindo a rota…</p>
    </div>

    <!-- ══ Tela inicial: o único lugar de configuração ══ -->
    <template v-else-if="screen === 'home'">
      <div class="cr-screen">
        <div class="cr-stack">
          <p class="cr-small">Nelson Boulangerie</p>
          <h1 class="cr-big">{{ greeting }}</h1>
          <p class="cr-base">{{ homeNote }}</p>
        </div>
        <div v-if="view?.today_q !== undefined" class="cr-block">
          <p class="cr-small">Hoje</p>
          <p class="cr-big">{{ money(view?.today_q) }}</p>
          <p class="cr-base">a receber</p>
        </div>
        <div v-if="showsSettings(screen)" class="cr-stack cr-gap">
          <p class="cr-small">Tema</p>
          <div class="cr-row">
            <UiButton
v-for="choice in THEME_CHOICES"
              :key="choice.value"
              variant="ghost"
             
              class="cr-chip"
              :class="theme === choice.value ? 'is-on' : ''"
              :aria-pressed="theme === choice.value"
              @click="setTheme(choice.value)"
            >
              {{ choice.label }}
            </UiButton>
          </div>
        </div>
        <ClientOnly>
          <UiButton v-if="canInstall" variant="ghost" class="cr-secondary cr-full" :disabled="installing" @click="addToHome">
            Adicionar à tela inicial
          </UiButton>
        </ClientOnly>
      </div>
    </template>

    <!-- ══ Confirmar o link: nada da rota antes do toque ══ -->
    <template v-else-if="screen === 'confirm'">
      <div class="cr-screen cr-center-y">
        <div class="cr-stack">
          <p class="cr-small">Nelson Boulangerie</p>
          <h1 class="cr-big">Esta rota é do {{ view?.courier }}.</h1>
          <p class="cr-base">Se não é você, feche esta página.</p>
        </div>
      </div>
      <div class="cr-footer">
        <UiButton variant="ghost" class="cr-primary" :disabled="ride.busy.value" @click="ride.claim()">
          Sou o {{ view?.courier }}, abrir
        </UiButton>
      </div>
    </template>

    <!-- ══ No balcão (e esperando um pedido) ══ -->
    <template v-else-if="screen === 'pickup' || screen === 'pickup_wait'">
      <div class="cr-screen">
        <div class="cr-head">
          <span v-if="tone" class="cr-letter" :style="{ background: tone.bg, color: tone.fg }">{{ view?.letter }}</span>
          <div class="cr-stack">
            <p class="cr-small">{{ rideName(view!) }}</p>
            <h1 class="cr-big">Pegue no balcão</h1>
          </div>
        </div>
        <div class="cr-list">
          <div v-for="block in pickupBlocks(view!)" :key="block.code" class="cr-block">
            <div class="cr-between">
              <span class="cr-badge">{{ block.code }}</span>
              <span :class="block.statusStrong ? 'cr-base' : 'cr-small'">{{ block.status }}</span>
            </div>
            <p v-for="line in block.lines" :key="line" class="cr-base">{{ line }}</p>
          </div>
        </div>
        <p v-if="bagTip(view!)" class="cr-small">{{ bagTip(view!) }}</p>
      </div>
      <div class="cr-footer">
        <UiButton v-if="screen === 'pickup'" variant="ghost" class="cr-primary" :disabled="ride.busy.value" @click="ride.depart()">
          Saí da loja
        </UiButton>
        <p v-else class="cr-wait">{{ waitText(view!) }}</p>
      </div>
    </template>

    <!-- ══ Na entrega (o Desfazer e as folhas passam por cima) ══ -->
    <template v-else-if="showDoor && door && screen !== 'no_answer'">
      <div class="cr-screen" :class="ride.pending.value || sheet ? 'is-behind' : ''">
        <div class="cr-stack">
          <p class="cr-small cr-inline">
            <span v-if="tone" class="cr-letter-sm" :style="{ background: tone.bg, color: tone.fg }">{{ view?.letter }}</span>
            {{ remainingText(remaining) }}
          </p>
          <h1 class="cr-big">{{ door.name || door.code }}</h1>
          <p v-if="door.complement" class="cr-base">{{ door.complement }}</p>
          <p class="cr-small">{{ doorPlace(door) }}</p>
        </div>
        <div class="cr-list">
          <p v-if="quoted(door.instructions)" class="cr-block cr-base">{{ quoted(door.instructions) }}</p>
          <div class="cr-block">
            <span class="cr-badge">{{ door.code }}</span>
            <p v-if="bagsText(door.bags)" class="cr-base">{{ bagsText(door.bags) }}</p>
          </div>
          <div v-for="due in doorBlocks" :key="due.label" class="cr-block">
            <p class="cr-small">{{ due.label }}</p>
            <p class="cr-big">{{ due.amount }}</p>
            <p class="cr-base">{{ due.note }}</p>
          </div>
          <p v-if="!doorBlocks.length" class="cr-block cr-base">Já pago. Só entregar.</p>
        </div>
      </div>
      <div v-if="!ride.pending.value" class="cr-footer">
        <UiButton variant="ghost" class="cr-primary" :disabled="ride.busy.value" @click="delivered">Entreguei {{ door.code }}</UiButton>
        <div class="cr-row">
          <a v-if="telUrl(door.phone)" class="cr-secondary" :href="telUrl(door.phone)">Ligar</a>
          <UiButton variant="ghost" class="cr-secondary" @click="sheet = 'problem'">Problema</UiButton>
        </div>
      </div>
    </template>

    <!-- ══ Ninguém atendeu: a espera curta ══ -->
    <template v-else-if="screen === 'no_answer' && door">
      <div class="cr-screen cr-center-y">
        <div class="cr-stack">
          <span class="cr-badge">{{ door.code }}</span>
          <h1 class="cr-big">Espere 2 minutos</h1>
        </div>
        <p class="cr-base">A loja está ligando para {{ door.name || 'o cliente' }}.</p>
        <p class="cr-small">Sem resposta, a loja diz pelo telefone o que fazer com a sacola.</p>
      </div>
      <div class="cr-footer">
        <UiButton variant="ghost" class="cr-secondary cr-full" @click="ride.answered()">{{ door.name || 'O cliente' }} atendeu</UiButton>
      </div>
    </template>

    <!-- ══ Dirigindo: o endereço em destaque ══ -->
    <template v-else-if="screen === 'drive' && driving">
      <div class="cr-screen cr-center-y">
        <div class="cr-stack">
          <p class="cr-small cr-inline">
            <span v-if="tone" class="cr-letter-sm" :style="{ background: tone.bg, color: tone.fg }">{{ view?.letter }}</span>
            {{ remainingText(remaining) }}
          </p>
          <h1 class="cr-big">{{ driving.street }}</h1>
          <p v-if="driving.neighborhood" class="cr-small">{{ driving.neighborhood }}</p>
        </div>
        <div class="cr-stack">
          <span class="cr-badge">{{ driving.code }}</span>
          <p class="cr-base">{{ firstName(driving) }}</p>
        </div>
      </div>
      <div class="cr-footer">
        <div class="cr-row">
          <a class="cr-secondary" :href="wazeUrl(driving)" target="_blank" rel="noopener noreferrer">Abrir no Waze</a>
          <a class="cr-secondary" :href="mapsUrl(driving)" target="_blank" rel="noopener noreferrer">Abrir no mapa</a>
        </div>
        <UiButton variant="ghost" class="cr-primary" @click="ride.arrive(driving.ref)">Cheguei</UiButton>
      </div>
    </template>

    <!-- ══ Voltando: só o acerto ══ -->
    <template v-else-if="screen === 'back'">
      <div class="cr-screen cr-center-y">
        <h1 class="cr-big">Entregue no caixa</h1>
        <div class="cr-list">
          <div v-for="block in settle" :key="block.join()" class="cr-block">
            <template v-if="block.length === 2">
              <p class="cr-small">{{ block[0] }}</p>
              <p class="cr-big">{{ block[1] }}</p>
            </template>
            <p v-else class="cr-base">{{ block[0] }}</p>
          </div>
          <p v-if="!settle.length" class="cr-block cr-base">Nada a entregar no caixa.</p>
        </div>
        <p class="cr-small">O balcão confere e fecha a rota.</p>
      </div>
    </template>

    <!-- ══ Fechada ══ -->
    <div v-else-if="screen === 'closed'" class="cr-screen cr-center-y">
      <span v-if="tone" class="cr-letter-lg" :style="{ background: tone.bg, color: tone.fg }">{{ view?.letter }}</span>
      <h1 class="cr-big">{{ closedTitle(view!) }}</h1>
      <p v-if="earnedText(view?.value_q)" class="cr-base">{{ earnedText(view?.value_q) }}</p>
      <p class="cr-small">{{ todayText(view?.today_q) }}</p>
    </div>

    <!-- ══ Cancelado: o forte, oposto ao tema, na frente de tudo ══ -->
    <div v-else-if="screen === 'cancelled' || (screen === 'stop_cancelled' && cancelledStop)" class="cr-screen cr-strong cr-center-y">
      <div class="cr-stack">
        <span v-if="cancelledStop" class="cr-badge cr-badge-strong">{{ cancelledStop.code }}</span>
        <h1 class="cr-big">Foi cancelado.</h1>
      </div>
      <p class="cr-base">
        {{ screen === 'stop_cancelled' || wasOnRoute ? 'Não entregue. Traga a sacola de volta.' : 'Não precisa vir.' }}
      </p>
      <UiButton
variant="ghost"
       
        class="cr-primary cr-primary-inverse"
        @click="cancelledStop ? ride.seeCancelled(cancelledStop.code) : ride.seeEnd()"
      >
        Entendi
      </UiButton>
    </div>

    <!-- ══ Link recusado ══ -->
    <div v-else class="cr-screen cr-center-y">
      <h1 class="cr-big">{{ refusal.title }}</h1>
      <p class="cr-small">{{ refusal.note }}</p>
    </div>

    <!-- ══ Desfazer: 10 s antes de avisar o cliente ══ -->
    <div v-if="ride.pending.value" class="cr-bar" role="status">
      <span class="cr-bar-text">{{ ride.pending.value.code }} entregue.</span>
      <UiButton variant="ghost" class="cr-bar-action" @click="ride.undo()">Desfazer</UiButton>
      <span class="cr-bar-clock" :style="{ width: `${(ride.undoLeft.value / UNDO_SECONDS) * 100}%` }" aria-hidden="true" />
    </div>
    <div v-else-if="ride.notice.value" class="cr-bar" role="status">
      <span class="cr-bar-text">{{ ride.notice.value }}</span>
    </div>

    <!-- ══ Folhas ══ -->
    <div v-if="sheet" class="cr-scrim" @click.self="closeSheet">
      <div class="cr-sheet" role="dialog" aria-modal="true">
        <template v-if="sheet === 'problem' && door">
          <div class="cr-stack">
            <span class="cr-badge">{{ door.code }}</span>
            <h2 class="cr-big">Qual o problema?</h2>
          </div>
          <UiButton v-for="item in PROBLEM_CASES" :key="item.kind" variant="ghost" class="cr-choice" :disabled="ride.busy.value" @click="chooseProblem(item.kind)">
            {{ item.label }}
          </UiButton>
          <p class="cr-small">{{ problemNote(door) }}</p>
        </template>
        <template v-else-if="sheet === 'payment' && door">
          <div class="cr-stack">
            <span class="cr-badge">{{ door.code }}</span>
            <h2 class="cr-big">Como pagou?</h2>
          </div>
          <UiButton v-for="item in paymentChoices(view?.machine)" :key="item.payment" variant="ghost" class="cr-choice" :disabled="ride.busy.value" @click="choosePayment(item.payment)">
            {{ item.label }}
          </UiButton>
          <p class="cr-small">Pix só pela maquininha: assim o pagamento aparece na loja na hora.</p>
        </template>
        <template v-else-if="sheet === 'install'">
          <h2 class="cr-big">Adicionar à tela inicial</h2>
          <p v-for="(step, index) in installSteps" :key="step" class="cr-base">{{ index + 1 }}. {{ step }}</p>
          <p v-if="!installSteps.length" class="cr-base">Use o menu do navegador e escolha Adicionar à tela inicial.</p>
        </template>
        <UiButton variant="ghost" class="cr-secondary cr-full" @click="closeSheet">Fechar</UiButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Paleta própria e neutra (dono, 16/11): branco, preto e dois cinzas claros. */
.cr {
  --cr-bg: #ffffff;
  --cr-block: #f5f5f5;
  --cr-badge: #d4d4d4;
  --cr-strong: #000000;
  --cr-fg: #000000;
  --cr-on-strong: #ffffff;
}
.cr[data-theme='dark'] {
  --cr-bg: #000000;
  --cr-block: #262626;
  --cr-badge: #525252;
  --cr-strong: #ffffff;
  --cr-fg: #ffffff;
  --cr-on-strong: #000000;
}
@media (prefers-color-scheme: dark) {
  .cr[data-theme='system'] {
    --cr-bg: #000000;
    --cr-block: #262626;
    --cr-badge: #525252;
    --cr-strong: #ffffff;
    --cr-fg: #ffffff;
    --cr-on-strong: #000000;
  }
}

.cr {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--cr-bg);
  color: var(--cr-fg);
  text-align: left;
  -webkit-text-size-adjust: 100%;
}
.cr * { box-sizing: border-box; margin: 0; }

/* Os três tamanhos. Nada mais. */
.cr-big { font-size: 1.75rem; font-weight: 800; line-height: 1.15; overflow-wrap: anywhere; }
.cr-base { font-size: 1.125rem; font-weight: 500; line-height: 1.35; overflow-wrap: anywhere; }
.cr-small { font-size: 0.9375rem; font-weight: 500; line-height: 1.35; overflow-wrap: anywhere; }

.cr-screen {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  gap: 1.75rem;
  overflow-y: auto;
  padding:
    max(1.25rem, env(safe-area-inset-top))
    max(1.25rem, env(safe-area-inset-right))
    1.25rem
    max(1.25rem, env(safe-area-inset-left));
  transition: opacity 0.2s;
}
.cr-screen.is-behind { opacity: 0.3; }
.cr-center-y { justify-content: center; }
.cr-stack { display: flex; flex-direction: column; gap: 0.375rem; align-items: flex-start; }
.cr-gap { gap: 0.75rem; align-self: stretch; }
.cr-list { display: flex; flex-direction: column; gap: 0.75rem; }
.cr-row { display: flex; gap: 0.5rem; width: 100%; }
.cr-between { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; }
.cr-head { display: flex; align-items: center; gap: 0.75rem; }
.cr-inline { display: flex; align-items: center; gap: 0.5rem; }

.cr-block {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.375rem;
  border-radius: 1rem;
  background: var(--cr-block);
  padding: 1rem;
}
.cr-between, .cr-block > .cr-between { align-self: stretch; }

.cr-badge {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  border-radius: 0.5rem;
  background: var(--cr-badge);
  padding: 0.125rem 0.5rem;
  font-size: 0.9375rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--cr-fg);
}
.cr-badge-strong { background: var(--cr-bg); color: var(--cr-fg); }

.cr-letter, .cr-letter-sm, .cr-letter-lg {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  font-weight: 800;
}
.cr-letter { width: 3rem; height: 3rem; border-radius: 0.75rem; font-size: 1.75rem; }
.cr-letter-sm { width: 1.5rem; height: 1.5rem; border-radius: 0.375rem; font-size: 0.9375rem; }
.cr-letter-lg { width: 4rem; height: 4rem; border-radius: 1rem; font-size: 1.75rem; }

.cr-footer {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  gap: 0.5rem;
  background: var(--cr-bg);
  padding:
    0.75rem
    max(1.25rem, env(safe-area-inset-right))
    max(1rem, env(safe-area-inset-bottom))
    max(1.25rem, env(safe-area-inset-left));
}

.cr-primary, .cr-secondary, .cr-chip, .cr-bar-action, .cr-choice {
  height: auto;
  gap: 0;
  white-space: normal;
  box-shadow: none;
  transform: none;
}
.cr-primary:focus-visible, .cr-secondary:focus-visible, .cr-chip:focus-visible,
.cr-bar-action:focus-visible, .cr-choice:focus-visible {
  outline: 3px solid var(--cr-fg);
  outline-offset: 2px;
}
.cr-primary, .cr-secondary, .cr-chip, .cr-bar-action {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 0;
  text-align: center;
  text-decoration: none;
  cursor: pointer;
  font-family: inherit;
}
.cr-primary {
  min-height: 4rem;
  width: 100%;
  border-radius: 1rem;
  background: var(--cr-strong);
  color: var(--cr-on-strong);
  font-size: 1.125rem;
  font-weight: 800;
}
.cr-primary:disabled, .cr-choice:disabled { opacity: 0.6; }
.cr-secondary {
  min-height: 3.5rem;
  flex: 1 1 0;
  border-radius: 1rem;
  background: var(--cr-block);
  color: var(--cr-fg);
  font-size: 1.125rem;
  font-weight: 700;
  padding: 0 0.75rem;
}
.cr-full { width: 100%; flex: none; }
.cr-chip {
  min-height: 3rem;
  flex: 1 1 0;
  border-radius: 0.75rem;
  background: var(--cr-block);
  color: var(--cr-fg);
  font-size: 0.9375rem;
  font-weight: 700;
}
.cr-chip.is-on { background: var(--cr-strong); color: var(--cr-on-strong); }

.cr-wait {
  display: flex;
  min-height: 4rem;
  align-items: center;
  border-radius: 1rem;
  background: var(--cr-block);
  padding: 0 1rem;
  font-size: 1.125rem;
  font-weight: 500;
}

.cr-choice {
  display: flex;
  min-height: 4rem;
  width: 100%;
  align-items: center;
  justify-content: flex-start;
  border: 0;
  border-radius: 1rem;
  background: var(--cr-block);
  color: var(--cr-fg);
  padding: 0.75rem 1rem;
  text-align: left;
  font-family: inherit;
  font-size: 1.125rem;
  font-weight: 500;
  cursor: pointer;
}

/* O forte, oposto ao tema: o cancelamento passa na frente de tudo. */
.cr-strong { background: var(--cr-strong); color: var(--cr-on-strong); gap: 1rem; }
.cr-strong .cr-badge-strong { background: var(--cr-on-strong); color: var(--cr-strong); }
.cr-primary-inverse { margin-top: 1.5rem; background: var(--cr-bg); color: var(--cr-fg); }

.cr-bar {
  position: absolute;
  right: max(0.75rem, env(safe-area-inset-right));
  bottom: max(0.75rem, env(safe-area-inset-bottom));
  left: max(0.75rem, env(safe-area-inset-left));
  z-index: 2;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  overflow: hidden;
  border-radius: 1rem;
  background: var(--cr-strong);
  color: var(--cr-on-strong);
  padding: 1rem;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
}
.cr-bar-text { flex: 1 1 auto; font-size: 1.125rem; font-weight: 800; }
.cr-bar-action {
  min-height: 3rem;
  border-radius: 0.75rem;
  background: var(--cr-bg);
  color: var(--cr-fg);
  padding: 0 1rem;
  font-size: 1.125rem;
  font-weight: 800;
}
.cr-bar-clock {
  position: absolute;
  bottom: 0;
  left: 0;
  height: 0.25rem;
  background: var(--cr-bg);
  transition: width 0.25s linear;
}

.cr-scrim {
  position: absolute;
  inset: 0;
  z-index: 3;
  display: flex;
  align-items: flex-end;
  background: rgba(0, 0, 0, 0.35);
}
.cr-sheet {
  display: flex;
  max-height: 85%;
  width: 100%;
  flex-direction: column;
  gap: 0.75rem;
  overflow-y: auto;
  border-radius: 1.5rem 1.5rem 0 0;
  background: var(--cr-bg);
  padding:
    1.25rem
    max(1.25rem, env(safe-area-inset-right))
    max(1.25rem, env(safe-area-inset-bottom))
    max(1.25rem, env(safe-area-inset-left));
}

/* Deitado (suporte da moto): o conteúdo à esquerda e os botões à direita, do lado do
   polegar, sem rolar para chegar ao toque. */
@media (orientation: landscape) and (max-height: 32rem) {
  .cr { flex-direction: row; }
  .cr-footer {
    width: 40%;
    justify-content: flex-end;
    padding-top: max(1rem, env(safe-area-inset-top));
  }
  .cr-footer .cr-row { flex-direction: column; }
  .cr-sheet { max-height: 100%; }
}
</style>
