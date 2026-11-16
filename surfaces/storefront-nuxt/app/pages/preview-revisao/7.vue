<script setup lang="ts">
// Prévia 7 (lacuna L2 da revisão das Entregas). Página só de olhar: dados
// fictícios, sem backend, sem $fetch. Não vai ao ar.

type Tone = 'info' | 'success' | 'warning'
type PhoneAction = { label: string, icon: string, primary: boolean }
type Step = { label: string, time?: string, state: 'completed' | 'current' | 'upcoming' }
type Phone = {
  tone: Tone
  title: string
  message: string
  footnote?: string
  actions: PhoneAction[]
  steps: Step[]
  note?: string
}

const ORDER_PREFIX = 'WEB-1611-'
const ORDER_TAIL = 'A47'

function steps (current: 'ready' | 'dispatched'): Step[] {
  const base: Step[] = [
    { label: 'Recebido', time: '11:52', state: 'completed' },
    { label: 'Pago', time: '11:53', state: 'completed' },
    { label: 'Em preparo', time: '11:58', state: 'completed' },
    { label: 'Pronto', time: '12:14', state: current === 'ready' ? 'current' : 'completed' },
    { label: 'Saiu para entrega', time: current === 'dispatched' ? '12:31' : undefined, state: current === 'dispatched' ? 'current' : 'upcoming' },
    { label: 'Entregue', state: 'upcoming' }
  ]
  return base
}

const TRACK: PhoneAction = { label: 'Acompanhar o entregador', icon: 'lucide:map-pin', primary: false }
const RECEIVED: PhoneAction = { label: 'Recebi meu pedido', icon: 'lucide:package-check', primary: true }

const TODAY_READY: Phone = {
  tone: 'success',
  title: 'Pronto, esperando o entregador',
  message: 'Assim que ele chegar, seu pedido sai para entrega.',
  actions: [],
  steps: steps('ready')
}

// Versão anterior da prévia (para comparação, em letra pequena ao lado).
type Before = { title: string, message: string, footnote?: string }

type DecidedRow = {
  key: string
  caption: string
  detail: string
  today: Phone
  b: Phone
  before?: Before
}

const rows: DecidedRow[] = [
  {
    key: 'ready',
    caption: '0. Pronto para entrega',
    detail: 'A loja ainda não chamou o entregador.',
    today: TODAY_READY,
    b: {
      tone: 'success',
      title: 'Seu pedido está pronto',
      message: 'Logo sai para entrega.',
      actions: [],
      steps: steps('ready')
    },
    before: {
      title: 'Pronto, esperando o entregador',
      message: 'Assim que ele chegar, seu pedido sai para entrega.'
    }
  },
  {
    key: 'called',
    caption: '1. A loja chamou o entregador',
    detail: 'Ninguém aceitou ainda.',
    today: TODAY_READY,
    b: {
      tone: 'success',
      title: 'Seu pedido está pronto',
      message: 'Estamos chamando o entregador.',
      actions: [],
      steps: steps('ready')
    },
    before: {
      title: 'Pronto, chamamos o entregador',
      message: 'Chamamos o entregador. Avisamos quando ele aceitar.'
    }
  },
  {
    key: 'accepted',
    caption: '2. Diego aceitou',
    detail: 'Ele vai até a loja buscar o pedido. Ainda não dá para acompanhar o trajeto.',
    today: TODAY_READY,
    b: {
      tone: 'success',
      title: 'Diego vem buscar seu pedido',
      message: 'Chega à loja por volta de 12h32.',
      actions: [],
      steps: steps('ready')
    },
    before: {
      title: 'Diego está a caminho da loja',
      message: 'Diego está a caminho da loja para buscar seu pedido.',
      footnote: 'Quando ele sair com o pedido, você acompanha por aqui.'
    }
  },
  {
    key: 'searching',
    caption: '3a. Ninguém aceitou',
    detail: 'A loja chama de novo. O pedido continua guardado.',
    today: TODAY_READY,
    b: {
      tone: 'info',
      title: 'Seu pedido está pronto',
      message: 'Está demorando mais que o normal. Seguimos chamando o entregador.',
      actions: [],
      steps: steps('ready')
    },
    before: {
      title: 'Procurando um entregador',
      message: 'Estamos procurando um entregador. Seu pedido está pronto e guardado.'
    }
  },
  {
    key: 'gave-up',
    caption: '3b. Diego desistiu',
    detail: 'O cliente já tinha lido o nome dele. A loja chama outro.',
    today: TODAY_READY,
    b: {
      tone: 'info',
      title: 'Diego não pôde vir',
      message: 'Estamos chamando outro entregador.',
      actions: [],
      steps: steps('ready')
    },
    before: {
      title: 'Procurando um entregador',
      message: 'Estamos procurando um entregador. Seu pedido está pronto e guardado.'
    }
  },
  {
    key: 'dispatched',
    caption: '4. Diego buscou o pedido e saiu',
    detail: 'Só agora aparece o "Acompanhar o entregador".',
    today: {
      tone: 'info',
      title: 'Saiu para entrega',
      message: 'Chega por volta de 12:45. Confirme aqui quando receber.',
      actions: [RECEIVED, TRACK],
      steps: steps('dispatched')
    },
    b: {
      tone: 'info',
      title: 'Saiu para entrega',
      message: 'Diego está a caminho. Deve chegar por volta de 12h45.',
      actions: [RECEIVED, TRACK],
      steps: steps('dispatched')
    },
    before: {
      title: 'Saiu para entrega',
      message: 'Chega por volta de 12:45. Confirme aqui quando receber.'
    }
  }
]

const columns: { key: 'today' | 'b', label: string, change: string }[] = [
  { key: 'today', label: 'Hoje (referência)', change: 'Uma frase só, do pronto até a coleta.' },
  { key: 'b', label: 'Decidido: B', change: 'Cada passo com sua frase. O botão "Acompanhar o entregador" só aparece depois que ele busca o pedido.' }
]

function panelClass (tone: Tone): string {
  if (tone === 'success') return 'border-l-4 border-border border-l-success bg-card text-foreground shadow-sm'
  if (tone === 'warning') return 'border-l-4 border-border border-l-warning bg-card text-foreground shadow-sm'
  return 'border-l-4 border-border border-l-info bg-card text-foreground shadow-sm'
}
function panelIconClass (tone: Tone): string {
  if (tone === 'success') return 'text-success'
  if (tone === 'warning') return 'text-warning'
  return 'text-info'
}
function panelIcon (tone: Tone): string {
  if (tone === 'success') return 'lucide:circle-check'
  if (tone === 'warning') return 'lucide:circle-alert'
  return 'lucide:info'
}
function currentStep (list: Step[]): number {
  return list.findIndex(step => step.state === 'current') + 1
}
</script>

<template>
  <main class="mx-auto w-full max-w-[1440px] space-y-8 px-4 pt-8 pb-32 sm:px-6">
    <header class="space-y-1">
      <p class="shop-kicker">Revisão das Entregas · tela do cliente</p>
      <PreviewNav :current="7" />
      <h1 class="shop-title">Prévia 7 · Acompanhamento do pedido enquanto o entregador não chega</h1>
      <p class="inline-flex items-center gap-2 rounded-md bg-success/15 px-3 py-1 text-lg font-semibold text-foreground">
        <Icon name="lucide:circle-check" class="size-5 text-success" />
        Decidido: B
      </p>
      <p class="shop-body text-muted-foreground">
        O botão "Acompanhar o entregador" só aparece depois que o entregador busca o pedido na loja. Até lá, cada passo tem sua frase, na voz da casa.
      </p>
      <p class="shop-body text-muted-foreground">
        Pedido de entrega {{ ORDER_PREFIX }}{{ ORDER_TAIL }}, Gleba Palhano, Londrina. Entregador Diego.
      </p>
    </header>

    <div class="hidden gap-x-6 gap-y-2 xl:grid xl:grid-cols-[170px_390px_390px_minmax(180px,260px)]">
      <div />
      <div v-for="col in columns" :key="col.key" class="space-y-1">
        <p :class="col.key === 'b' ? 'text-xl font-semibold' : 'text-base font-semibold text-muted-foreground'">{{ col.label }}</p>
        <p class="shop-body text-muted-foreground">{{ col.change }}</p>
      </div>
      <div class="space-y-1 opacity-70">
        <p class="text-sm font-semibold">Versão anterior da prévia</p>
        <p class="text-xs text-muted-foreground">Só para comparar.</p>
      </div>
    </div>

    <section
      v-for="row in rows"
      :key="row.key"
      class="grid grid-cols-1 gap-x-6 gap-y-4 border-t pt-6 xl:grid-cols-[170px_390px_390px_minmax(180px,260px)]"
    >
      <div class="space-y-1">
        <p class="font-semibold">{{ row.caption }}</p>
        <p class="shop-body text-muted-foreground">{{ row.detail }}</p>
      </div>

      <div v-for="col in columns" :key="col.key" :class="['min-w-0 space-y-2', col.key === 'today' ? 'order-2 opacity-50 grayscale xl:order-none' : 'order-1 xl:order-none']">
        <p :class="['xl:hidden', col.key === 'b' ? 'font-semibold' : 'text-sm font-semibold text-muted-foreground']">{{ col.label }}</p>
        <!-- Celular 390 px: o mesmo topo da página /pedido/[ref]. -->
        <div :class="['w-full max-w-[390px] overflow-hidden rounded-[28px] bg-background', col.key === 'b' ? 'border-4 border-foreground/80 shadow-lg ring-4 ring-success/30' : 'border-2 border-foreground/30']">
          <div class="flex items-center justify-between border-b px-4 py-2 text-xs text-muted-foreground">
            <span>12:20</span>
            <Icon name="lucide:shopping-bag" class="size-4" />
          </div>
          <div class="space-y-4 px-4 py-4">
            <p class="text-xs text-muted-foreground">Início › Pedidos › Pedido {{ ORDER_PREFIX }}{{ ORDER_TAIL }}</p>
            <div>
              <p class="shop-kicker">Acompanhamento</p>
              <h2 class="mt-1 shop-title">
                Pedido<br>
                <span class="text-xl font-normal text-muted-foreground">{{ ORDER_PREFIX }}</span>{{ ORDER_TAIL }}
              </h2>
            </div>

            <UiAlert
              variant="default"
              :class="panelClass(row[col.key].tone)"
              :icon="panelIcon(row[col.key].tone)"
              :icon-class="panelIconClass(row[col.key].tone)"
            >
              <template #icon>
                <span class="relative mt-0.5 flex size-4 shrink-0 items-center justify-center">
                  <span class="absolute inline-flex size-full rounded-full bg-current opacity-40 motion-safe:animate-ping" aria-hidden="true" />
                  <Icon :name="panelIcon(row[col.key].tone)" :class="['relative size-4 shrink-0', panelIconClass(row[col.key].tone)]" />
                </span>
              </template>
              <!-- Na B o título quebra linha em vez de cortar: nome comprido ainda cabe no celular. -->
              <UiAlertTitle :class="['text-foreground', col.key === 'b' ? 'line-clamp-none leading-snug' : '']">{{ row[col.key].title }}</UiAlertTitle>
              <UiAlertDescription class="w-full text-muted-foreground">
                <div class="w-full shop-stack-block">
                  <p>{{ row[col.key].message }}</p>
                  <p v-if="row[col.key].footnote" class="shop-body">{{ row[col.key].footnote }}</p>
                  <div v-if="row[col.key].actions.length" class="flex w-full flex-col gap-2 pt-1">
                    <UiButton
                      v-for="action in row[col.key].actions"
                      :key="action.label"
                      :variant="action.primary ? 'default' : 'outline'"
                      :icon="action.icon"
                    >
                      {{ action.label }}
                    </UiButton>
                  </div>
                </div>
              </UiAlertDescription>
            </UiAlert>

            <UiCard class="py-3">
              <UiCardContent class="px-4 py-0">
                <div class="mb-2 flex gap-6 border-b text-sm">
                  <span class="border-b-2 border-foreground pb-2 font-semibold">Histórico</span>
                  <span class="pb-2 text-muted-foreground">Resumo</span>
                  <span class="pb-2 text-muted-foreground">Entrega</span>
                </div>
                <UiTimeline :model-value="currentStep(row[col.key].steps)">
                  <UiTimelineItem
                    v-for="(step, index) in row[col.key].steps"
                    :key="step.label"
                    :step="index + 1"
                    class="group-data-[orientation=vertical]/timeline:ms-10"
                  >
                    <UiTimelineHeader>
                      <UiTimelineSeparator
                        class="group-data-[orientation=vertical]/timeline:-left-7 group-data-[orientation=vertical]/timeline:h-[calc(100%-1.5rem-0.25rem)] group-data-[orientation=vertical]/timeline:translate-y-6.5"
                      />
                      <UiTimelineDate v-if="step.time">{{ step.time }}</UiTimelineDate>
                      <UiTimelineTitle>{{ step.label }}</UiTimelineTitle>
                      <UiTimelineIndicator
                        v-if="step.state === 'current'"
                        class="flex size-6 items-center justify-center border-none bg-primary text-primary-foreground group-data-[orientation=vertical]/timeline:-left-7"
                      >
                        <span class="size-2 rounded-full bg-primary-foreground" />
                      </UiTimelineIndicator>
                      <UiTimelineIndicator
                        v-else
                        class="group-data-completed/timeline-item:bg-primary group-data-completed/timeline-item:text-primary-foreground flex size-6 items-center justify-center group-data-completed/timeline-item:border-none group-data-[orientation=vertical]/timeline:-left-7"
                      >
                        <Icon name="lucide:check" :size="16" class="group-not-data-completed/timeline-item:hidden" />
                      </UiTimelineIndicator>
                    </UiTimelineHeader>
                  </UiTimelineItem>
                </UiTimeline>
              </UiCardContent>
            </UiCard>
          </div>
        </div>
      </div>

      <div v-if="row.before" class="order-3 space-y-1 text-xs text-muted-foreground opacity-70 xl:order-none xl:pt-24">
        <p class="xl:hidden">Versão anterior da prévia, só para comparar:</p>
        <p class="font-semibold">{{ row.before.title }}</p>
        <p>{{ row.before.message }}</p>
        <p v-if="row.before.footnote">{{ row.before.footnote }}</p>
      </div>
    </section>

    <footer class="space-y-1 border-t pt-6 shop-body text-muted-foreground">
      <p>Os passos 0 a 3b saem do mesmo estado da entrega que o Gestor já usa (sem campo novo). A página do cliente já recebe a atualização em tempo real.</p>
      <p>Na B, o título do aviso quebra linha em vez de terminar em reticências: um nome comprido de entregador continua inteiro no celular.</p>
      <p>Ao cliente não se fala em corrida, aceite nem no nome da empresa de entrega: só o entregador, pelo nome, e o que ele está fazendo.</p>
    </footer>
  </main>
</template>
