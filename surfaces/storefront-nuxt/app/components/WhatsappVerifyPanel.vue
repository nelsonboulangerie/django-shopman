<script setup lang="ts">
import { phoneDisplay } from '~/utils/authPhone'
import type { WhatsappStartStatus } from '~/composables/useWhatsappVerify'

// Painel APRESENTACIONAL do login pelo WhatsApp. Duas fases, e cada uma responde a
// uma queixa dos testadores:
//
// 1. ANTES do toque — "pra que eu tenho que fazer isso?" e "o que eu tenho que
//    fazer?". O porquê vem primeiro (é por lá que a casa avisa do pedido), depois os
//    três passos, depois UM botão. Não há nada competindo com ele.
// 2. DEPOIS do toque — a tela espera a mensagem. Quando ela chega, a aba entra sozinha
//    (useWhatsappReturn), então o terceiro passo é só voltar. O envio manual mora aqui,
//    como plano B de quem viu o WhatsApp não abrir — não na primeira tela, onde era
//    uma segunda coisa a entender antes da primeira.
//
// Copy vem por props (configurável no Admin via OMOTENASHI_DEFAULTS).
const props = withDefaults(defineProps<{
  deepLink?: string
  code?: string
  message?: string
  waNumber?: string
  status?: WhatsappStartStatus
  waiting?: boolean
  why?: string
  steps?: string[]
  ctaLabel?: string
  waitingTitle?: string
  waitingMessage?: string
  manualTitle?: string
  manualIntro?: string
}>(), {
  deepLink: '',
  code: '',
  message: '',
  waNumber: '',
  status: 'idle',
  waiting: false,
  why: '',
  steps: () => [],
  ctaLabel: 'Abrir o WhatsApp',
  waitingTitle: 'Enviou a mensagem?',
  waitingMessage: 'Assim que ela chegar, você entra por aqui, sem fazer mais nada.',
  manualTitle: 'O WhatsApp não abriu?',
  manualIntro: 'Mande a mensagem abaixo para {phone} no WhatsApp.'
})

// `used`: o código do deep link é de USO ÚNICO. Quem toca o botão gasta o que está no
// `href`, então a tela precisa saber — para esperar a mensagem e preparar o próximo.
const emit = defineEmits<{ regenerate: [], used: [] }>()

const codeCopied = ref(false)
const isStarting = computed(() => props.status === 'idle' || props.status === 'loading')
const canOpenWhatsApp = computed(() => !!props.deepLink)
const ctaText = computed(() => canOpenWhatsApp.value ? props.ctaLabel : 'Gerando link')
const manualMessage = computed(() => props.message || (props.code ? `#menu ${props.code}` : ''))
// 554333231997 → "(43) 3323-1997"; chat "cru" (sem mensagem) para o envio manual.
const waNumberDisplay = computed(() => props.waNumber ? phoneDisplay(`+${props.waNumber}`) : '')
const chatLink = computed(() => props.waNumber ? `https://wa.me/${props.waNumber}` : '')
// `{phone}` marca onde o número entra na frase (a copy é editável no Admin).
// Sem o marcador, o número vai para o fim — nunca some da instrução.
const manualIntroParts = computed(() => {
  const [before = '', ...rest] = props.manualIntro.split('{phone}')
  if (rest.length) return { before, after: rest.join('') }
  return { before: `${before.trimEnd()} `, after: '.' }
})

async function copyMessage () {
  if (!import.meta.client || !manualMessage.value) return
  try {
    await navigator.clipboard.writeText(manualMessage.value)
    codeCopied.value = true
    useSonner.success('Mensagem copiada. Envie no nosso WhatsApp.')
    setTimeout(() => { codeCopied.value = false }, 2500)
  } catch {
    // Clipboard indisponível: a mensagem continua visível para digitar — mas quem tocou
    // em "Copiar" e não viu nada acontecer conclui que o botão está quebrado.
    useSonner.info('Seu navegador não deixou copiar. A mensagem está aí em cima para você digitar.')
  }
}
</script>

<template>
  <section class="shop-stack-block" data-login-whatsapp aria-live="polite">
    <template v-if="status === 'error'">
      <div class="rounded-lg border bg-card p-4 shop-stack-block">
        <UiAlert variant="destructive">
          <UiAlertTitle>Não consegui gerar seu link agora</UiAlertTitle>
          <UiAlertDescription>Tente novamente ou use o SMS.</UiAlertDescription>
        </UiAlert>
        <UiButton type="button" size="lg" icon="lucide:rotate-cw" class="w-full justify-center" @click="emit('regenerate')">
          Tentar de novo
        </UiButton>
      </div>
    </template>

    <!-- Fase 1: o porquê, os passos, um botão. -->
    <div
      v-else-if="!waiting"
      class="rounded-lg border bg-card p-4 shop-stack-block"
      data-login-whatsapp-open
      :aria-busy="isStarting && !canOpenWhatsApp"
    >
      <p v-if="why" class="shop-body text-balance" data-login-whatsapp-why>{{ why }}</p>
      <ol v-if="steps.length" class="shop-stack-micro" data-login-whatsapp-steps>
        <li v-for="(step, index) in steps" :key="index" class="flex items-start gap-3">
          <span
            class="flex size-6 shrink-0 items-center justify-center rounded-full bg-foreground text-xs font-semibold text-background tabular-nums"
            aria-hidden="true"
          >{{ index + 1 }}</span>
          <span class="shop-body pt-0.5">{{ step }}</span>
        </li>
      </ol>
      <UiButton
        :href="deepLink || undefined"
        target="_blank"
        rel="noopener"
        size="lg"
        icon="lucide:message-circle"
        class="w-full justify-center"
        :loading="isStarting && !canOpenWhatsApp"
        :disabled="!canOpenWhatsApp"
        @click="emit('used')"
      >
        {{ ctaText }}
      </UiButton>
    </div>

    <!-- Fase 2: esperando a mensagem. O plano B aparece só aqui. -->
    <div v-else class="rounded-lg border bg-card p-4 shop-stack-block" data-login-whatsapp-waiting>
      <div class="flex items-start gap-3">
        <Icon name="lucide:loader-circle" :size="22" class="mt-0.5 shrink-0 animate-spin text-muted-foreground" aria-hidden="true" />
        <div class="min-w-0">
          <p class="shop-item-title font-semibold">{{ waitingTitle }}</p>
          <p class="mt-1 shop-muted">{{ waitingMessage }}</p>
        </div>
      </div>

      <div v-if="manualMessage" class="shop-surface-faubourg rounded-md border p-4 shop-stack-micro" data-login-whatsapp-manual>
        <p v-if="manualTitle" class="shop-body font-semibold" data-login-whatsapp-manual-title>{{ manualTitle }}</p>
        <p class="shop-meta" data-login-whatsapp-manual-intro>
          {{ manualIntroParts.before }}<span v-if="waNumberDisplay" class="whitespace-nowrap font-semibold text-foreground">{{ waNumberDisplay }}</span>{{ manualIntroParts.after }}
        </p>
        <!-- `bg-card`, não `bg-background`: sobre o Faubourg o canvas creme some. -->
        <div class="flex items-center gap-2 rounded-md border bg-card py-1 pr-1 pl-3">
          <span class="min-w-0 flex-1 truncate font-mono text-base tracking-wider text-muted-foreground">{{ manualMessage }}</span>
          <UiButton
            type="button"
            variant="ghost"
            size="icon-lg"
            :icon="codeCopied ? 'lucide:check' : 'lucide:copy'"
            :aria-label="codeCopied ? 'Mensagem copiada' : 'Copiar mensagem'"
            @click="copyMessage"
          />
        </div>
        <div class="flex flex-wrap items-center gap-x-4">
          <UiButton
            :href="deepLink || undefined"
            target="_blank"
            rel="noopener"
            variant="link"
            size="sm"
            icon="lucide:message-circle"
            class="justify-start px-0"
            :disabled="!canOpenWhatsApp"
            data-login-whatsapp-reopen
            @click="emit('used')"
          >
            Abrir de novo
          </UiButton>
          <UiButton
            :href="chatLink || undefined"
            target="_blank"
            rel="noopener"
            variant="link"
            size="sm"
            icon="lucide:external-link"
            class="justify-start px-0"
            :disabled="!chatLink"
          >
            Abrir a conversa vazia
          </UiButton>
        </div>
      </div>
    </div>
  </section>
</template>
