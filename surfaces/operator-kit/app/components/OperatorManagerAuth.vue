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
import { managerAuthReason, managerAuthTitle } from "../presentation/managerAuth";
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
watch(() => props.open, (open) => {
  if (!open) return;
  identify.value?.reset(Boolean(props.error));
});

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
  <!-- ⚠️ `value` ANOTADO de propósito. `UiDialog` é do app hospedeiro (o kit é
       module-free por desenho), então nos apps que não têm um — central, B.I.,
       compras — o tipo do evento não resolve e o parâmetro cai em `any`
       implícito. O typecheck da layer roda em TODOS eles, não só em quem usa o
       componente. Ver o gate de superfícies. -->
  <UiDialog :open="open" @update:open="(value: boolean) => emit('update:open', value)">
    <!-- `data-drawer-manager-auth` deixa a trava da gaveta saber que o PIN está
         por cima: o Esc dela não pode roubar a tecla de volta desta tela. -->
    <!-- Camada 3, cromática: uma borda de acento que a tela de login não tem.
         É a MAIS FRACA das três de propósito, e nunca anda sozinha — some no
         reflexo de sol sobre o vidro do balcão e não existe para quem não
         distingue a cor. Quem carrega o sentido é o texto (camada 1) e o fato
         de isto ser um modal com a venda visível atrás (camada 2). -->
    <UiDialogContent class="border-warning/50 sm:max-w-sm" data-drawer-manager-auth>
      <UiDialogHeader class="items-center text-center">
        <div class="mx-auto grid size-12 place-items-center rounded-md border border-warning/40 bg-warning/10 text-amber-600 dark:text-amber-400">
          <Icon name="lucide:shield-check" class="size-6" />
        </div>
        <UiDialogTitle class="text-lg">{{ title }}</UiDialogTitle>
        <UiDialogDescription>{{ reason }}</UiDialogDescription>
        <!-- ⚠️ O par semântico do destrave de sessão, que diz "Você assume o
             balcão". Aqui é o contrário, e é isso que o operador precisa
             entender num teclado de PIN idêntico ao do destrave: a sessão NÃO
             troca, o gerente assina uma coisa e vai embora. -->
        <p v-if="operatorName" class="text-sm font-medium text-foreground">
          Você continua como {{ operatorName }}.
        </p>
      </UiDialogHeader>

      <div class="flex flex-col items-center gap-4 pb-1">
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
    </UiDialogContent>
  </UiDialog>
</template>
