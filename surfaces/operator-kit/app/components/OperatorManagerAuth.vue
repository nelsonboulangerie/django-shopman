<script setup lang="ts">
// Autorização do gerente (spec §1.4/§3): a tela focada que sobe quando a review
// exige `requires_manager_approval`.
//
// ⚠️ A identificação NÃO mora aqui. Crachá, lista e teclado de PIN vêm do
// `OperatorIdentify` do operator-kit — a MESMA peça que a tela de bloqueio usa.
//
// Antes eram dois componentes desenhando o mesmo seletor e o mesmo teclado, e o
// custo não era código repetido: era que só um deles sabia ler crachá. Sangria e
// pedido de troco são a hora em que o gerente mais aparece no balcão, e era
// exatamente ali que o crachá no pescoço dele não servia para nada.
//
// O gerente é ESCOLHIDO NUMA LISTA, não digitado. O nome nunca foi decoração: o
// servidor resolve o usuário por `username`, confere `cashman.adjust_shift` e
// valida contra a credencial daquela pessoa. Nome errado grava a assinatura
// errada em `Entry.approved_by` — justamente a segunda assinatura que a sangria
// existe para ter.
//
// O campo de texto continua vivo como ÚNICA porta quando a lista chega vazia
// (leitura negada, nenhum gerente com PIN provisionado): esconder a única porta
// deixaria o balcão sem saída no meio de uma sangria.
import type { ManagerAction } from "../presentation/managerAuth";
import {
  managerAuthReason,
  managerAuthTitle,
} from "../presentation/managerAuth";
import type { ManagerOption } from "../types/manager";

const props = defineProps<{
  open: boolean;
  /**
   * O operador que CONTINUA depois da assinatura.
   *
   * ⚠️ É a linha que separa autorizar de logar, e é texto — não cor. As duas
   * telas pedem PIN num teclado igual, e o operador pode ler "digite o PIN"
   * como "sua sessão vai trocar". Não vai: `validate_manager_override` resolve o
   * gerente, confere a permissão, recusa autoassinatura e devolve o objeto —
   * nunca chama `login()`. Dizer isso na tela é mais barato que consertar a
   * confusão depois, e vale para qualquer autorização (desconto, sangria,
   * destrave), não só a da gaveta.
   */
  operatorName?: string;
  /** O ato que está sendo autorizado. A copy inteira sai daqui — ver `managerAuth`. */
  action?: ManagerAction;
  thresholdQ?: number;
  /** Códigos vindos da review (`approval_reasons`) — dizem POR QUE o gerente foi chamado. */
  reasons?: string[];
  /** Quem pode assinar (`POSProjection.managers`). Vazio cai no campo livre. */
  managers?: ManagerOption[];
  busy?: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  "update:open": [boolean];
  /** PIN: `(username, pin)`. Crachá: `(  "", "", token)`. Ver `authorizePayload`. */
  authorize: [string, string];
  authorizeBadge: [string];
}>();

const identify = ref<{ reset: (keepPicked?: boolean) => void } | null>(null);

const managers = computed(() => props.managers ?? []);
const reason = computed(() =>
  managerAuthReason({
    action: props.action,
    reasons: props.reasons,
    thresholdQ: props.thresholdQ,
  }),
);
const title = computed(() => managerAuthTitle(props.action));

// Campos limpos a cada abertura. Quando o servidor recusa, some só o PIN: quem
// foi escolhido continua escolhido, senão o gerente reescolheria o próprio nome
// a cada erro de digitação.
watch(
  () => props.open,
  (open) => {
    if (!open) return;
    identify.value?.reset(Boolean(props.error));
  },
);

// A prop oficial `content` do Modal repassa ao DialogContent do reka; o tipo dela só
// lista as props do reka, não atributos `data-*`, que chegam ao elemento como attrs
// (o PDV prova: `sessionIndex.layout.test.ts`, "o PIN do gerente sobe POR CIMA").
const dialogContent = { "data-drawer-manager-auth": "" } as Record<string, string>;

function onPin(payload: { username: string; pin: string }) {
  if (props.busy || !payload.username || !payload.pin) return;
  emit("authorize", payload.username, payload.pin);
}

function onBadge(token: string) {
  if (props.busy) return;
  emit("authorizeBadge", token);
}
</script>

<template>
  <!-- `data-drawer-manager-auth` mora no DialogContent (prop oficial `content`),
       onde está o `data-state`: a trava da gaveta do PDV (`PosDrawerLockDialog`)
       procura `[data-drawer-manager-auth][data-state="open"]` para não roubar o Esc
       desta tela. Numa div interna o seletor nunca casava.
       Camada 3, cromática: a borda de aviso (`class` oficial do Modal, que vai para o
       conteúdo) é a mais fraca das três e nunca anda sozinha. Quem carrega o sentido
       é o texto (camada 1) e o modal com a venda visível atrás (camada 2).
       Largura do diálogo = a do teclado do PIN (`sm:max-w-sm`): o aviso, a lista,
       o campo e as teclas batem borda com borda, sem tecla esticada. -->
  <NuxtModal
    :open="open"
    :title="title"
    :description="reason"
    :content="dialogContent"
    class="border border-warning/50 sm:max-w-sm"
    @update:open="(value: boolean) => emit('update:open', value)"
  >
    <template #body>
      <div class="grid gap-4">
        <NuxtAlert
          v-if="operatorName"
          color="warning"
          variant="subtle"
          icon="i-lucide-shield-check"
          :title="`Você continua como ${operatorName}.`"
        />
        <OperatorIdentify
          ref="identify"
          :people="managers"
          :busy="busy"
          :error="error"
          :badge-enabled="open"
          allow-typed-name
          name-label="Nome do gerente"
          prompt="Quem autoriza?"
          change-label="Trocar gerente"
          @pin="onPin"
          @badge="onBadge"
        />
      </div>
    </template>
  </NuxtModal>
</template>
