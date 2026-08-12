<script setup lang="ts">
// "Continuar no seu navegador" — o convite que atravessa o pote de cookie.
//
// ⚠️ Aparece SÓ dentro de navegador embutido (WhatsApp, Instagram, Facebook), e só para quem
// já está identificada. Fora dali não há nada a atravessar, e o convite seria ruído.
//
// O que ele resolve: o webview tem pote de cookie próprio, então tudo o que ela conquista ali
// — sessão, aparelho confiado — não existe no navegador que ela usa no resto do dia. Em vez de
// aceitar essa perda, atravessamos de propósito, agora que já sabemos quem ela é.
//
// A copy não promete tecnologia; promete o resultado ("não pedimos de novo").
const props = defineProps<{
  /** Só oferecemos a quem já está identificada: a travessia carrega identidade, não cria. */
  identified: boolean
}>()

const { crossOver, working, needsManualStep, failed } = useBrowserHandoff()

// Numa página renderizada no servidor o user agent do navegador não existe, então a decisão
// espera o cliente. `v-if` num valor que só o cliente conhece evita o pisca de hidratação.
const inApp = ref(false)
onMounted(() => { inApp.value = isInAppBrowser() })

const show = computed(() => inApp.value && props.identified)
</script>

<template>
  <UiAlert v-if="show" variant="info" icon="lucide:external-link" data-browser-handoff>
    <UiAlertTitle>Continuar no seu navegador</UiAlertTitle>
    <UiAlertDescription>
      <p>
        Você está no navegador de dentro do WhatsApp. Se continuar no seu navegador de sempre,
        não vamos pedir sua identificação de novo nas próximas vezes.
      </p>

      <UiButton
        size="sm"
        icon="lucide:external-link"
        class="mt-2"
        :disabled="working"
        @click="crossOver"
      >
        {{ working ? 'Abrindo…' : 'Abrir no meu navegador' }}
      </UiButton>

      <!-- ⚠️ O truque de sair do webview falha em SILÊNCIO quando o sistema não entende o
           esquema. Este degrau é o que nunca falha, porque é o menu do próprio WhatsApp — e
           só aparece depois de o caminho bom não ter funcionado. -->
      <p v-if="needsManualStep" class="shop-caption mt-2 text-muted-foreground">
        Não abriu? Toque nos três pontinhos aqui em cima e escolha
        <strong>Abrir no navegador</strong>. Sua sacola continua aqui.
      </p>

      <p v-if="failed" class="shop-caption mt-2 text-muted-foreground">
        Não conseguimos preparar o link agora. Você pode seguir por aqui sem problema.
      </p>
    </UiAlertDescription>
  </UiAlert>
</template>
