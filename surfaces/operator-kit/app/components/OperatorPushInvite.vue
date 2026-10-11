<script setup lang="ts">
// "os avisos DESTA ÁREA" era a mesma frase nos seis apps que montam o convite, e
// "esta área" nunca aparecia escrita em lugar nenhum — o operador tinha que adivinhar
// se estava ligando os avisos da Cozinha, do PDV ou de tudo. O nome do app já é dado
// canônico (`app-identity.json`, via `runtimeConfig.public.operatorPwa.identity`), o
// mesmo que nomeia o convite de instalação e a barra de título; aqui ele entra na
// frase, com o artigo contraído pela gramática da identidade.
interface OperatorPushIdentity {
  label: string;
  article: string;
}

const props = defineProps<{
  /** Sobrescreve a identidade canônica — existe para o harness de teste. */
  identity?: OperatorPushIdentity;
}>();

const push = useWebPush();

const runtimeIdentity = (useRuntimeConfig().public?.operatorPwa as { identity?: OperatorPushIdentity } | undefined)
  ?.identity;
const identity = computed<OperatorPushIdentity | null>(() => props.identity || runtimeIdentity || null);

/** "o PDV" → "do PDV"; "a Cozinha" → "da Cozinha"; "as Compras" → "das Compras". */
const CONTRACTION: Record<string, string> = { o: "do", a: "da", os: "dos", as: "das" };
const scope = computed(() => {
  const value = identity.value;
  if (!value) return "deste aplicativo";
  const contraction = CONTRACTION[value.article.toLowerCase()];
  return contraction ? `${contraction} ${value.label}` : `de ${value.article} ${value.label}`;
});
</script>

<template>
  <NuxtAlert
    v-if="push.supported.value && !push.active.value && push.permission.value !== 'denied'"
    data-operator-push-invite
    class="fixed right-4 bottom-[calc(1rem+env(safe-area-inset-bottom))] z-40 max-w-xs"
    color="info"
    icon="i-lucide-bell-ring"
    title="Avisos mesmo com o app fechado"
    :description="`Ative neste dispositivo para receber só os avisos ${scope}.`"
  >
    <template #actions><NuxtButton :loading="push.loading.value" :label="push.loading.value ? 'Ativando…' : 'Ativar avisos'" @click="push.activate" /></template>
  </NuxtAlert>
</template>
