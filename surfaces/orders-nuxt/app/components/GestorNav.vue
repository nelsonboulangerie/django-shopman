<script setup lang="ts">
// Navegação de seções do Gestor (UX-KIT-V1). As seções moram no rail da suíte
// (`OperatorSuiteRail`, do tablet para cima) e na barra do polegar
// (`OperatorSectionBar`, no celular), como nas prévias v3/v4: o topo do conteúdo fica
// com o cabeçalho de uma linha de cada tela. O desenho é do kit; aqui fica só o que é
// do Gestor: quais são as seções, e o que vai no pé do rail (alertas e avisos).
// `place` diz qual das duas peças este ponto do shell monta.
import { gestorSections } from "~/presentation/gestorSections";

defineProps<{
  place: "rail" | "bar";
  /** Rail: URL da Central e operador ativo (o menu e o Bloquear). */
  hubUrl?: string;
  operatorName?: string;
}>();
const emit = defineEmits<{ lock: [] }>();
// No celular o rail não aparece e o sino vai para o cabeçalho de cada tela: aqui ele
// só é montado do tablet para cima (um sino por tela, não dois no DOM).
const isPhone = useMediaQuery("(max-width: 767.98px)");

// Canal ou feed desligado, pausado ou divergente: um ponto âmbar + "1 desligado" no
// item Canais. Estado normal não mostra nada.
const { attention } = useChannelAttention();

// Clientes só aparece para quem pode usar a seção (`shop.manage_customers`, decisão do
// dono em 24/09/2026). A pergunta é a mesma da antessala, sobre quem está operando: o
// servidor responde sim/não, sem listar permissões. Troca de operador relê.
const { data: session } = useNuxtData<{ operator?: { id: number } }>("operator-session");
const operatorId = computed(() => session.value?.operator?.id ?? null);
const { data: customersAccess } = useFetch<{ authorized?: boolean }>("/api/v1/backstage/operator/session/", {
  key: useOperatorResourceKey("customers-access"),
  query: { perm: "shop.manage_customers" },
  server: true,
  watch: [operatorId],
});

const { expeditesOnly } = useGestorAccess();

// Postos só para quem gere operadores (vincula dispositivos e cadastra postos).
const { data: workstationsAccess } = useFetch<{ authorized?: boolean }>("/api/v1/backstage/operator/session/", {
  key: useOperatorResourceKey("workstations-access"),
  query: { perm: "cashman.manage_operators" },
  server: true,
  watch: [operatorId],
});

const sections = computed(() =>
  gestorSections({
    channelsAttention: attention.value?.label || "",
    canManageCustomers: customersAccess.value?.authorized === true,
    canManageWorkstations: workstationsAccess.value?.authorized === true,
    expeditesOnly: expeditesOnly.value,
  }),
);
</script>

<template>
  <OperatorSuiteRail
    v-if="place === 'rail'"
    :sections="sections"
    label="Seções do Gestor"
    :hub-url="hubUrl"
    :operator-name="operatorName"
    @lock="emit('lock')"
  >
    <template v-if="!isPhone" #foot>
      <AlertsBell placement="rail" />
      <NotificationBell placement="rail" />
    </template>
  </OperatorSuiteRail>
  <OperatorSectionBar v-else :sections="sections" label="Seções do Gestor" />
</template>
