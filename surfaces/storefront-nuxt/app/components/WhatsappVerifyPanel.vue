<script setup lang="ts">
import { phoneDisplay } from '~/utils/authPhone'
import type { WhatsappStartStatus } from '~/composables/useWhatsappVerify'

// Painel APRESENTACIONAL do login por WhatsApp (fluxo access-link), em uma tela só: o
// start leve vive no pai (entrar.vue) e pré-aquece o deep link. Dois blocos: (1) abrir e
// enviar num toque; "OU"; (2) envio manual da mensagem, caso o WhatsApp não abra sozinho.
// O login em si acontece pelo access link que o ManyChat devolve — a aba só instrui.
// Copy vem por props (configurável no Admin via OMOTENASHI_DEFAULTS).
const props = withDefaults(defineProps<{
  deepLink?: string
  code?: string
  message?: string
  waNumber?: string
  status?: WhatsappStartStatus
  glimpse?: string
  noPasswordNote?: string
  manualTitle?: string
  manualIntro?: string
  ctaLabel?: string
}>(), {
  deepLink: '',
  code: '',
  message: '',
  waNumber: '',
  status: 'idle',
  glimpse: '',
  noPasswordNote: '',
  manualTitle: 'Quer fazer você mesmo?',
  manualIntro: 'Envie esta mensagem diretamente para o nosso WhatsApp',
  ctaLabel: 'Entrar pelo WhatsApp'
})

const emit = defineEmits<{ regenerate: [] }>()

const codeCopied = ref(false)
const isStarting = computed(() => props.status === 'idle' || props.status === 'loading')
const canOpenWhatsApp = computed(() => !!props.deepLink)
const ctaText = computed(() => canOpenWhatsApp.value ? props.ctaLabel : 'Preparando WhatsApp')
const manualMessage = computed(() => props.message || (props.code ? `#menu ${props.code}` : ''))
// 554333231997 → "(43) 3323-1997"; chat "cru" (sem mensagem) para o envio manual.
const waNumberDisplay = computed(() => props.waNumber ? phoneDisplay(`+${props.waNumber}`) : '')
const chatLink = computed(() => props.waNumber ? `https://wa.me/${props.waNumber}` : '')

async function copyMessage () {
  if (!import.meta.client || !manualMessage.value) return
  try {
    await navigator.clipboard.writeText(manualMessage.value)
    codeCopied.value = true
    useSonner.success('Mensagem copiada. Envie no nosso WhatsApp.')
    setTimeout(() => { codeCopied.value = false }, 2500)
  } catch {
    // Clipboard indisponível: a mensagem continua visível para digitar.
  }
}
</script>

<template>
  <section class="shop-stack-block" data-login-whatsapp aria-live="polite">
    <template v-if="status === 'error'">
      <div class="rounded-lg border bg-bottomnav p-4 shop-stack-block">
        <UiAlert variant="destructive">
          <UiAlertTitle>Não deu para iniciar pelo WhatsApp</UiAlertTitle>
          <UiAlertDescription>Tente de novo ou receba um código por SMS.</UiAlertDescription>
        </UiAlert>
        <UiButton type="button" size="lg" icon="lucide:rotate-cw" class="w-full justify-center" @click="emit('regenerate')">
          Tentar de novo
        </UiButton>
      </div>
    </template>

    <template v-else>
      <!-- Bloco 1 — a ação: abrir o WhatsApp com a mensagem pronta e enviar. O lampejo
           lidera (o que vai acontecer); o rodapé reassegura (prático, seguro, sem senha). -->
      <div
        class="rounded-lg border bg-bottomnav p-4 shop-stack-block"
        data-login-whatsapp-open
        :aria-busy="isStarting && !canOpenWhatsApp"
      >
        <p v-if="glimpse" class="shop-item-title text-center text-balance" data-login-whatsapp-glimpse>{{ glimpse }}</p>
        <UiButton
          :href="deepLink || undefined"
          target="_blank"
          rel="noopener"
          size="lg"
          icon="lucide:message-circle"
          class="w-full justify-center"
          :loading="isStarting && !canOpenWhatsApp"
          :disabled="!canOpenWhatsApp"
        >
          {{ ctaText }}
        </UiButton>
        <p v-if="noPasswordNote" class="shop-meta text-center" data-login-whatsapp-note>{{ noPasswordNote }}</p>
      </div>

      <!-- Divisor: a alternativa manual, para quando o app não abre sozinho. -->
      <div v-if="manualMessage" class="flex items-center gap-3" aria-hidden="true" data-login-whatsapp-or>
        <span class="h-px flex-1 bg-border" />
        <span class="shop-meta uppercase tracking-widest">ou</span>
        <span class="h-px flex-1 bg-border" />
      </div>

      <!-- Bloco 2 — envio manual (alternativa): título com peso de seção + subtítulo,
           mensagem discreta + copiar + abrir chat cru. -->
      <div v-if="manualMessage" class="rounded-lg border bg-card p-4 shop-stack-block" data-login-whatsapp-manual>
        <div class="shop-stack-micro text-center">
          <p v-if="manualTitle" class="shop-item-title" data-login-whatsapp-manual-title>{{ manualTitle }}</p>
          <p class="shop-meta">
            {{ manualIntro }}
            <span v-if="waNumberDisplay" class="whitespace-nowrap font-semibold text-foreground">{{ waNumberDisplay }}</span>.
          </p>
        </div>
        <div class="rounded-md bg-background py-2 text-center font-mono text-base tracking-wider text-muted-foreground">
          {{ manualMessage }}
        </div>
        <UiButton
          type="button"
          variant="default"
          class="w-full justify-center bg-cta text-cta-foreground hover:bg-cta/90 hover:text-cta-foreground"
          :icon="codeCopied ? 'lucide:check' : 'lucide:copy'"
          @click="copyMessage"
        >
          {{ codeCopied ? 'Mensagem copiada' : 'Copiar mensagem' }}
        </UiButton>
        <UiButton
          :href="chatLink || undefined"
          target="_blank"
          rel="noopener"
          variant="default"
          icon="lucide:message-circle"
          class="w-full justify-center bg-cta text-cta-foreground hover:bg-cta/90 hover:text-cta-foreground"
          :disabled="!chatLink"
        >
          Abrir WhatsApp
        </UiButton>
      </div>
    </template>
  </section>
</template>
