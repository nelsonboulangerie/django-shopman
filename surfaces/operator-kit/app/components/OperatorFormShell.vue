<script setup lang="ts">
// O casco canônico de um cadastro da suíte. O mesmo em Compras, Produção e Gestor:
// a entidade e a condução mudam, o casco não.
//
// Ele reúne o que todo cadastro precisa e que o kit já tinha solto:
//   - a gaveta lateral com título e descrição;
//   - as seções (`OperatorFormSection`, com `data-focus-target`);
//   - o aviso do que ainda não foi salvo (`dirty`);
//   - a barra de ação na base (`OperatorActionBar`) com salvar e descartar,
//     e a mesma linha na mesa (`lg`) no rodapé;
//   - a pergunta antes de descartar (`useConfirm`);
//   - o próximo foco por seção (`useNextFocus`).
//
// Quem chama é dono do formulário e do salvamento: este casco só conduz. A ação
// principal é declarada por rótulo, ícone e motivo de bloqueio; o secundário
// descarta. Contrato na seção "Casco de cadastro" do README do kit.
import { computed } from "vue";

import OperatorActionBar from "./OperatorActionBar.vue";
import OperatorButton from "./OperatorButton.vue";

import { useConfirm } from "../composables/useConfirm";
import { useNextFocus } from "../composables/useNextFocus";
import type { OperatorActionBarAction } from "../presentation/actionBar";
import { FORM_DISCARD_COPY, dirtyCountLabel, type FormDiscardCopy } from "../presentation/formShell";

const props = withDefaults(
  defineProps<{
    open: boolean;
    title: string;
    description?: string;
    /** O operador mexeu no que ainda não foi salvo. */
    dirty?: boolean;
    /** Quantos campos mudaram, para o aviso ("2 alterações não salvas"). */
    dirtyCount?: number;
    busy?: boolean;
    /** O verbo e o alvo do salvamento ("Criar produto", "Salvar fornecedor"). */
    saveLabel: string;
    saveIcon?: string;
    saveDisabled?: boolean;
    /** Por que não pode salvar agora: aparece escrito perto da ação. */
    saveDisabledReason?: string;
    /** `data-*` da ação de salvar (os testes e as telas acham o botão). */
    saveAttrs?: Record<string, string>;
    discardLabel?: string;
    discardAttrs?: Record<string, string>;
    /** A chave da seção que deve estar na linha de foco agora. */
    activeSection?: string | null;
    /** Troca a pergunta do descarte, quando o cadastro tem nome próprio. */
    confirmDiscard?: Partial<FormDiscardCopy>;
    actionLabel?: string;
  }>(),
  {
    description: "",
    dirty: false,
    dirtyCount: 0,
    busy: false,
    saveIcon: undefined,
    saveDisabled: false,
    saveDisabledReason: "",
    saveAttrs: () => ({}),
    discardLabel: "Descartar",
    discardAttrs: () => ({}),
    activeSection: null,
    confirmDiscard: undefined,
    actionLabel: "Ação do cadastro",
  },
);

const emit = defineEmits<{
  "update:open": [value: boolean];
  save: [];
  discard: [];
}>();

const { reveal } = useNextFocus(() => props.activeSection ?? null);

const saveAction = computed<OperatorActionBarAction>(() => ({
  label: props.saveLabel,
  icon: props.saveIcon,
  loading: props.busy,
  disabled: props.saveDisabled,
  reason: props.saveDisabledReason || undefined,
  onSelect: () => emit("save"),
  ...props.saveAttrs,
}));

const notice = computed(() => (props.dirty ? dirtyCountLabel(props.dirtyCount) : ""));
const statusLine = computed(() =>
  props.saveDisabled && props.saveDisabledReason ? props.saveDisabledReason : notice.value,
);

const confirm = useConfirm();

async function requestClose() {
  if (props.busy) return;
  if (props.dirty) {
    const ok = await confirm({ ...FORM_DISCARD_COPY, ...props.confirmDiscard });
    if (!ok) return;
    emit("discard");
  }
  emit("update:open", false);
}

function discardAction(): OperatorActionBarAction {
  return {
    label: props.discardLabel,
    onSelect: () => void requestClose(),
    ...props.discardAttrs,
  };
}

function onOpenChange(value: boolean) {
  if (value) {
    emit("update:open", true);
    return;
  }
  void requestClose();
}

defineExpose({ reveal });
</script>

<template>
  <NuxtSlideover
    :open="open"
    :title="title"
    :description="description"
    side="right"
    @update:open="onOpenChange"
  >
    <template #body>
      <div class="flex flex-col gap-4" data-form-shell :data-form-dirty="dirty ? 'true' : 'false'">
        <slot />
      </div>
    </template>
    <template #footer>
      <div class="flex w-full flex-col gap-2">
        <div v-if="$slots.lead" class="lg:hidden">
          <slot name="lead" />
        </div>
        <OperatorActionBar
          :label="actionLabel"
          :action="saveAction"
          :secondary="discardAction()"
          :context-label="notice"
        />
        <div class="hidden w-full items-center gap-2 lg:flex">
          <slot name="lead" />
          <p
            v-if="statusLine"
            class="me-auto min-w-0 text-xs text-muted-foreground"
            data-form-shell-notice
          >
            {{ statusLine }}
          </p>
          <span v-else class="me-auto" />
          <OperatorButton
            :label="discardLabel"
            color="neutral"
            variant="ghost"
            v-bind="discardAttrs"
            @click="requestClose"
          />
          <OperatorButton
            :label="saveLabel"
            :icon="saveIcon"
            :loading="busy"
            :disabled="saveDisabled || busy"
            v-bind="saveAttrs"
            @click="emit('save')"
          />
        </div>
      </div>
    </template>
  </NuxtSlideover>
</template>
