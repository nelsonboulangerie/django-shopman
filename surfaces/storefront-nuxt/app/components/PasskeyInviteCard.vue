<script setup lang="ts">
// "Entrar com o rosto na próxima vez?" — o convite, oferecido uma vez.
//
// ⚠️ Quando ele aparece é a parte que importa. Só quando TODAS as condições valem:
//
// - o aparelho tem autenticador próprio (Face ID, Touch ID, Windows Hello). Prometer "entre
//   com o rosto" num computador sem leitor seria prometer o que a tela não entrega;
// - a pessoa está identificada com identidade FORTE (o servidor recusa cadastro de sessão que
//   só conhece o número — aqui só evitamos oferecer o que vai ser negado);
// - ela ainda não tem passkey neste aparelho;
// - e ela não recusou antes. Convite que volta toda visita é propaganda.
//
// A recusa fica no `localStorage` de propósito: é preferência de tela, não fato do negócio, e
// gravá-la no servidor criaria um dono novo para uma informação que só interessa a este
// navegador.
const props = defineProps<{
  /** Só oferecemos a quem já está reconhecida. */
  identified: boolean
}>()

const DISMISSED_KEY = 'shopman.passkey.invite.dismissed'

const { enroll, busy, error, needsConfirmation } = usePasskey()
const { confirm: confirmByWhatsApp, starting: confirming } = useWhatsAppConfirm()
const route = useRoute()

const eligible = ref(false)
const dismissed = ref(true)
const activated = ref(false)

onMounted(async () => {
  dismissed.value = localStorage.getItem(DISMISSED_KEY) === '1'
  if (dismissed.value || !props.identified) return

  const { passkeyIsQuick } = usePasskey()
  if (!await passkeyIsQuick()) return

  // Já tem? Então não há o que oferecer. 403 aqui significa identidade fraca — e nesse caso o
  // convite também não aparece, porque o cadastro seria negado.
  try {
    const data = await $fetch<{ passkeys: unknown[] }>(
      useShopmanApiPath()('/api/v1/account/passkeys/'),
      { credentials: 'include' }
    )
    eligible.value = (data.passkeys?.length ?? 0) === 0
  } catch {
    eligible.value = false
  }
})

const show = computed(() => props.identified && eligible.value && !dismissed.value && !activated.value)

async function activate() {
  activated.value = await enroll()
}

function dismiss() {
  localStorage.setItem(DISMISSED_KEY, '1')
  dismissed.value = true
}
</script>

<template>
  <UiAlert v-if="show" variant="info" icon="lucide:scan-face" data-passkey-invite>
    <UiAlertTitle>Entrar com o rosto na próxima vez?</UiAlertTitle>
    <UiAlertDescription>
      <p>
        Você ativa uma vez e pronto: nas próximas visitas entra com o rosto ou a digital do seu
        aparelho, sem código e sem esperar mensagem.
      </p>

      <div class="mt-2 flex flex-wrap gap-2">
        <UiButton size="sm" icon="lucide:scan-face" :disabled="busy" @click="activate">
          {{ busy ? 'Ativando…' : 'Ativar' }}
        </UiButton>
        <UiButton size="sm" variant="ghost" :disabled="busy" @click="dismiss">
          Agora não
        </UiButton>
      </div>

      <!-- A API recusa cadastro de sessão que só conhece o número: cadastrar credencial
           vale para sempre, e mensagem se encaminha. O caminho é o mesmo toque de sempre. -->
      <template v-if="needsConfirmation">
        <p class="shop-caption mt-2 text-muted-foreground">
          Antes de ativar, confirme que é você.
        </p>
        <UiButton
          size="sm"
          variant="secondary"
          icon="lucide:message-circle"
          class="mt-1"
          :disabled="confirming"
          @click="confirmByWhatsApp(route.fullPath)"
        >
          {{ confirming ? 'Abrindo o WhatsApp…' : 'Confirmar pelo WhatsApp' }}
        </UiButton>
      </template>

      <p v-if="error" class="shop-caption mt-2 text-muted-foreground">{{ error }}</p>
    </UiAlertDescription>
  </UiAlert>
</template>
