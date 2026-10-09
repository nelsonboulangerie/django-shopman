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

// O prompt nativo demora a voltar: o botão diz que está esperando (clique nunca inerte).
const installing = ref(false);
async function install() {
  if (installing.value) return;
  installing.value = true;
  try {
    if (await pwa.install()) pwa.dismissAsDone();
  } finally {
    installing.value = false;
  }
}

// Alvo de toque do `main` só nas páginas que vestem a suíte (ver `suite-page:`).
const TOUCH = "suite-page:min-h-control";
const actions = computed(() => [
  {
    label: "Agora não",
    color: "neutral" as const,
    variant: "outline" as const,
    class: TOUCH,
    onClick: () => pwa.dismiss(),
  },
  // Ninguém sabe daqui se ela seguiu os passos; quem sabe é ela. Dizer "já instalei"
  // encerra o convite de vez em vez de repeti-lo na semana seguinte.
  plan.value.kind === "prompt"
    ? { label: "Instalar", class: TOUCH, loading: installing.value, onClick: install }
    : { label: "Já instalei", class: TOUCH, onClick: () => pwa.dismissAsDone() },
]);
</script>

<template>
  <!-- Convite não é etapa (dono, 17/09/2026): é um aviso no pé da tela, na mesma pilha
       do aviso de versão e do convite de avisos (`OperatorPwaRuntime`), e não bloqueia
       nada. Como Modal (mesmo sem `modal`), ele escondia o login do leitor de tela no
       WebKit, roubava o foco e, sendo um diálogo aberto, calava os atalhos do app
       enquanto não fosse respondido. -->
  <NuxtAlert
    v-if="visible"
    color="info"
    variant="subtle"
    icon="i-lucide-monitor-down"
    :title="title"
    :actions="actions"
    data-operator-pwa-install
  >
    <template #description>
      <div class="flex flex-col gap-3">
        <p>{{ description }}</p>
        <OperatorInstallSteps v-if="plan.kind === 'steps'" :plan="plan" />
      </div>
    </template>
  </NuxtAlert>
</template>
