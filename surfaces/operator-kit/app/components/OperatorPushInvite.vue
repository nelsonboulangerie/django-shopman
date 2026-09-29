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
  <div
    v-if="push.supported.value && !push.active.value && push.permission.value !== 'denied'"
    data-operator-push-invite
    class="fixed bottom-[calc(1rem+env(safe-area-inset-bottom))] right-4 z-40 max-w-xs rounded-xl border bg-card p-3 shadow-lg"
  >
    <p class="text-sm font-semibold">Avisos mesmo com o app fechado</p>
    <p class="mt-1 text-xs text-muted-foreground">Ative neste dispositivo para receber só os avisos {{ scope }}.</p>
    <button
      type="button"
      class="mt-2 inline-flex h-11 items-center rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground disabled:opacity-60"
      :disabled="push.loading.value"
      @click="push.activate"
    >
      {{ push.loading.value ? 'Ativando…' : 'Ativar avisos' }}
    </button>
  </div>
</template>
