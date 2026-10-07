<script setup lang="ts">
// O convite de instalação tem DUAS camadas, e elas estavam trocadas.
//
// O QUÊ é de cada app: o que ele passa a fazer da tela inicial. Sai da identidade
// canônica (`app-identity.json`), pelo `runtimeConfig` — a mesma fonte do manifesto, do
// ícone e da barra de título.
//
// O COMO NÃO é comum, e era aí que estava o erro. O convite dizia "No Safari, toque em
// Compartilhar" para qualquer pessoa em iOS — no Chrome, no Firefox, dentro do navegador
// do WhatsApp, onde barra do Safari não existe. Fora do iOS, ou o navegador oferecia o
// prompt nativo, ou o convite não dizia nada. Agora o caminho sai de `installPlan()`
// (`utils/installGuide.ts`), que responde por sistema + navegador e devolve `none`
// quando não existe caminho honesto — a regra do dono é informação correta, ou nada.
interface OperatorInstallIdentity {
  label: string;
  article: string;
  install: string;
}

const props = defineProps<{
  app: string;
  /** Sobrescreve a identidade canônica — existe para o harness de teste. */
  identity?: OperatorInstallIdentity;
}>();

const runtimeIdentity = (
  useRuntimeConfig().public?.operatorPwa as
    { identity?: OperatorInstallIdentity } | undefined
)?.identity;
const identity = computed<OperatorInstallIdentity | null>(
  () => props.identity || runtimeIdentity || null,
);

const pwa = usePwaInstall({ app: props.app });
const plan = computed(() => pwa.plan.value);
const visible = computed(() => pwa.canInvite.value);

// Um toque resolve, ou a pessoa vai seguir passos — o título diz qual dos dois é, antes
// de ela decidir se tem tempo agora.
const title = computed(() => {
  const named = identity.value
    ? `${identity.value.article} ${identity.value.label}`
    : "este aplicativo";
  return plan.value.kind === "prompt"
    ? `Instale ${named}`
    : `Coloque ${named} na tela inicial`;
});
const description = computed(
  () =>
    identity.value?.install ||
    "Abra este aplicativo direto da tela inicial, sem procurar o endereço no navegador.",
);

async function install() {
  if (await pwa.install()) pwa.dismissAsDone();
}
</script>

<template>
  <NuxtModal
    :open="visible"
    :dismissible="false"
    :close="false"
    :title="title"
    data-operator-pwa-install
  >
    <template #body>
      <div class="flex flex-col gap-4">
        <p class="text-sm text-muted-foreground">
          {{ description }}
        </p>
        <OperatorInstallSteps v-if="plan.kind === 'steps'" :plan="plan" />
      </div>
    </template>

    <template #footer>
      <div class="grid w-full grid-cols-2 gap-2">
        <NuxtButton
          block
          color="neutral"
          variant="outline"
          label="Agora não"
          @click="pwa.dismiss()"
        />
        <NuxtButton
          v-if="plan.kind === 'prompt'"
          block
          label="Instalar"
          @click="install"
        />
        <!-- Ninguém sabe daqui se ela seguiu os passos; quem sabe é ela. Dizer "já
             instalei" encerra o convite de vez em vez de repeti-lo na semana seguinte. -->
        <NuxtButton
          v-else
          block
          label="Já instalei"
          @click="pwa.dismissAsDone()"
        />
      </div>
    </template>
  </NuxtModal>
</template>
