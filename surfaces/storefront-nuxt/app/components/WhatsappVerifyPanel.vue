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

// `used`: o código do deep link é de USO ÚNICO. Quem toca o botão gasta o que
// está no `href`, então a tela precisa saber para preparar o próximo — senão o
// segundo toque manda um código já consumido e a sacola fica para trás.
const emit = defineEmits<{ regenerate: [], used: [] }>()

const codeCopied = ref(false)
const isStarting = computed(() => props.status === 'idle' || props.status === 'loading')
const canOpenWhatsApp = computed(() => !!props.deepLink)
const ctaText = computed(() => canOpenWhatsApp.value ? props.ctaLabel : 'Gerando link')
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
          <UiAlertTitle>Não consegui gerar seu link agora</UiAlertTitle>
          <UiAlertDescription>Tente novamente ou use o SMS.</UiAlertDescription>
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
          @click="emit('used')"
          size="lg"
          icon="lucide:message-circle"
          class="w-full justify-center"
          :loading="isStarting && !canOpenWhatsApp"
          :disabled="!canOpenWhatsApp"
        >
          {{ ctaText }}
        </UiButton>
        <p v-if="noPasswordNote" class="shop-meta text-center" data-login-whatsapp-note>{{ noPasswordNote }}</p>

        <!-- RODAPÉ MANUAL — para quem desconfia de link e prefere mandar a
             mensagem com as próprias mãos.

             Ele morava num CARTÃO IRMÃO, depois de um divisor "ou", com dois
             botões sólidos na mesma cor do CTA principal. Somados, ocupavam mais
             área sólida que o próprio CTA — três sólidos na tela, e o olho sem
             saber onde pousar. O erro era de modelagem, não de estilo: este não
             é um caminho irmão, é o MESMO caminho feito à mão. Por isso agora é
             rodapé deste cartão, atrás de uma linha fina. O irmão do WhatsApp é
             o SMS, e é lá que o "ou" foi morar.

             E os dois botões não eram duas escolhas: "Abrir WhatsApp" leva ao
             chat SEM texto nenhum, então é o segundo passo de uma sequência —
             copie, depois abra e cole. Apresentar sequência como escolha é o que
             mais pesava aqui. Copiar vira ÍCONE sobre o próprio código (é uma
             micro-ação sobre um texto que está ali, não um destino) e abrir vira
             link.

             A mensagem continua VISÍVEL, e não escondida atrás de um "mostrar
             mais": quem desconfia de botão precisa ver o que vai enviar na hora
             de decidir. O peso cai pela cor e pelo tamanho, nunca pela ausência. -->
        <div v-if="manualMessage" class="-mx-4 border-t px-4 pt-4 shop-stack-micro" data-login-whatsapp-manual>
          <p v-if="manualTitle" class="shop-body font-semibold" data-login-whatsapp-manual-title>{{ manualTitle }}</p>
          <p class="shop-meta">
            {{ manualIntro }}
            <span v-if="waNumberDisplay" class="whitespace-nowrap font-semibold text-foreground">{{ waNumberDisplay }}</span>.
          </p>
          <div class="flex items-center gap-2 rounded-md bg-background py-1 pr-1 pl-3">
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
          <UiButton
            :href="chatLink || undefined"
            target="_blank"
            rel="noopener"
            variant="link"
            size="sm"
            icon="lucide:external-link"
            :disabled="!chatLink"
          >
            Abrir WhatsApp
          </UiButton>
        </div>
      </div>
    </template>
  </section>
</template>
