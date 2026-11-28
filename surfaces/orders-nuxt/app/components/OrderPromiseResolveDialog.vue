<script setup lang="ts">
// "Resolver" a promessa em risco (WP-G08; dono, 19/11/2026: a quebra da promessa pede
// mais que um aviso). Um diálogo só por tela (o painel e o detalhe), aberto com o
// `ref` do pedido. De cima para baixo:
//
//   1. o fato, com as frases do aviso;
//   2. "Avisar o cliente" (WP-G07): o aviso aprovado que abre a conversa. O botão leva
//      ao diálogo do G07 com o aviso e os itens já marcados; ele mostra a mensagem,
//      envia e o recibo do pedido diz o que o provedor respondeu;
//   3. "O que fazer", uma escolha por linha (trocar, remarcar, tirar o item, cancelar);
//      a escolha travada escreve o motivo, e nada vem marcado: quem decide é a pessoa;
//   4. a proposta da escolha marcada, para quando o cliente responder, com "Copiar
//      mensagem" e "Chamar no WhatsApp". O modelo aprovado é fixo: a proposta sob
//      medida segue a conversa, não sai pela API;
//   5. no rodapé, que não rola, "Voltar" e o botão com o nome do que a escolha faz.
//
// Tudo o que se lê vem do servidor (`GET orders/<ref>/promise-resolution/`): as
// escolhas, a guarda de cada uma, a mensagem e o que conclui. Concluir, por tipo:
//   - `link` (trocar, remarcar): abre o PDV, na janela dele;
//   - `edit` (tirar o item): a edição do pedido que já existe; quando pede gerente, a
//     assinatura é o `OperatorManagerAuth` de sempre (escolhido da lista, nunca digitado);
//   - `cancel`: fecha este diálogo e avisa quem o monta, que abre o cancelar que já existe.
import { splitRef } from "~/presentation/board";
import {
  CALL_ON_WHATSAPP_LABEL,
  COPY_FAILED,
  COPY_MESSAGE_LABEL,
  MANAGER_NEXT_STEP,
  MESSAGE_COPIED,
  NOTIFY_LABEL,
  WHAT_TO_DO_LABEL,
  choiceItems,
  concludeButton,
  messageHeading,
  needsManager,
  pickedChoice,
  removedSentence,
  resolutionTitle,
} from "~/presentation/promiseResolution";
import { usePromiseResolution } from "~/composables/usePromiseResolution";
import type { ManagerOption } from "../../../operator-kit/app/types/manager";
import { useOperatorAppLink } from "../../../operator-kit/app/composables/useOperatorAppLink";

const props = withDefaults(
  defineProps<{
    open: boolean;
    orderRef: string;
    /** Quem pode assinar a devolução (a mesma lista de gerentes do PDV). */
    managers?: ManagerOption[];
    /** Quem está operando: o diálogo do gerente diz que a pessoa continua. */
    viewerName?: string;
  }>(),
  { managers: () => [], viewerName: "" },
);

const emit = defineEmits<{
  "update:open": [value: boolean];
  /** O pedido mudou (o item saiu, ou a promessa deixou de estar em risco): reler. */
  changed: [];
  /** "Cancelar o pedido inteiro": quem monta abre o diálogo de cancelar que já existe. */
  cancel: [ref: string];
  /** "Avisar o cliente": quem monta abre o diálogo do G07 com o aviso e os itens marcados. */
  notify: [ref: string, pick: { kind: string; lines: string[] }];
}>();

const { resolution, state, message, busy, read, clear, removeMissing } =
  usePromiseResolution();
const { attrsFor } = useOperatorAppLink();

const picked = ref("");
const failure = ref("");
const copyNote = ref("");
const managerOpen = ref(false);
const managerError = ref("");

function reset() {
  picked.value = "";
  failure.value = "";
  copyNote.value = "";
  managerOpen.value = false;
  managerError.value = "";
}

function load() {
  reset();
  if (props.orderRef) void read(props.orderRef);
}

// Cada abertura lê de novo: as sugestões e o dinheiro são os de agora.
watch(
  () => [props.open, props.orderRef] as const,
  ([open]) => {
    if (open) load();
    else {
      reset();
      clear();
    }
  },
  { immediate: true },
);

// O pedido deixou de estar em risco enquanto a tela estava aberta (o lote voltou,
// alguém já resolveu): o diálogo fecha dizendo a frase do servidor, e a leitura da
// página se refaz.
watch(state, (value) => {
  if (value !== "gone") return;
  useSonner.info(message.value);
  emit("changed");
  emit("update:open", false);
});

const title = computed(() =>
  resolutionTitle(resolution.value?.code || splitRef(props.orderRef).code),
);
const items = computed(() => choiceItems(resolution.value?.choices ?? []));
const choice = computed(() => pickedChoice(resolution.value, picked.value));
const button = computed(() => concludeButton(choice.value, busy.value));
const link = computed(() =>
  button.value.href ? attrsFor(button.value.href) : null,
);
const managerHint = computed(() => needsManager(choice.value));

// A confirmação do copiar e a falha da gravação são da escolha que estava marcada.
watch(picked, () => {
  copyNote.value = "";
  failure.value = "";
});

function copyMessage() {
  const text = choice.value?.message;
  if (!text) return;
  copyNote.value = "";
  // A área de transferência é API do navegador (exceção permitida): sem ela, a
  // mensagem continua escrita na tela e a linha diz o que fazer.
  void Promise.resolve()
    .then(() => navigator.clipboard.writeText(text))
    .then(() => {
      copyNote.value = MESSAGE_COPIED;
    })
    .catch(() => {
      copyNote.value = COPY_FAILED;
    });
}

function close(value: boolean) {
  if (value) return;
  if (busy.value) return;
  emit("update:open", false);
}

function notify() {
  const notice = resolution.value?.notice;
  if (!notice?.enabled || busy.value) return;
  emit("update:open", false);
  emit("notify", props.orderRef, { kind: notice.kind, lines: [...notice.line_ids] });
}

async function send(approval?: Record<string, string>) {
  const current = choice.value;
  if (!current || current.conclude.kind !== "edit") return;
  failure.value = "";
  const outcome = await removeMissing(props.orderRef, current.conclude, approval);
  if (outcome.ok) {
    managerOpen.value = false;
    useSonner.success(removedSentence(current));
    emit("changed");
    emit("update:open", false);
    return;
  }
  if (
    outcome.code === "manager_approval_required" ||
    outcome.code === "manager_approval_invalid"
  ) {
    managerOpen.value = true;
    managerError.value =
      outcome.code === "manager_approval_invalid" ? outcome.message : "";
    return;
  }
  // A recusa fica escrita no diálogo, que continua aberto com a escolha marcada.
  managerOpen.value = false;
  failure.value = outcome.message;
}

function conclude() {
  const current = choice.value;
  if (!current || busy.value) return;
  failure.value = "";
  if (current.conclude.kind === "cancel") {
    emit("update:open", false);
    emit("cancel", props.orderRef);
    return;
  }
  if (current.conclude.kind !== "edit") return;
  if (current.requires_manager_approval) {
    managerError.value = "";
    managerOpen.value = true;
    return;
  }
  void send();
}
</script>

<template>
  <NuxtModal
    :open="open && !managerOpen"
    :title="title"
    data-promise-resolve-dialog
    @update:open="close"
  >
    <template #body>
      <OperatorScreenState
        v-if="state === 'loading' || state === 'idle' || state === 'gone'"
        state="loading"
        what="as escolhas deste pedido"
        in-card
        data-resolve-loading
      />
      <OperatorScreenState
        v-else-if="state === 'error'"
        state="error"
        what="as escolhas deste pedido"
        :description="message"
        in-card
        data-resolve-load-error
        @retry="load"
      />
      <div
        v-else-if="resolution"
        class="flex min-w-0 flex-col gap-4"
        data-resolve-content
      >
        <!-- 1. O fato: as mesmas frases do aviso, uma por item em falta. -->
        <NuxtAlert
          color="error"
          variant="subtle"
          icon="i-lucide-package-x"
          data-resolve-facts
        >
          <template #description>
            <ul class="flex flex-col gap-1">
              <li
                v-for="fact in resolution.facts"
                :key="fact"
                class="font-medium break-words"
                data-resolve-fact
              >
                {{ fact }}
              </li>
            </ul>
          </template>
        </NuxtAlert>

        <!-- 2. O aviso aprovado abre a conversa: um toque leva ao diálogo do G07, com o
             aviso e os itens marcados. Fechado, o motivo e o que fazer no lugar. -->
        <NuxtCard variant="soft" as="section" data-resolve-notice>
          <div class="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div class="flex min-w-0 flex-col gap-1">
              <p class="text-sm break-words" data-resolve-notice-note>
                {{ resolution.notice.note }}
              </p>
              <p
                v-if="!resolution.notice.enabled && resolution.notice.reason"
                class="text-sm text-muted break-words"
                data-resolve-notice-reason
              >
                {{ resolution.notice.reason }}
              </p>
            </div>
            <NuxtButton
              v-if="resolution.notice.enabled"
              type="button"
              color="neutral"
              icon="i-lucide-send"
              :label="NOTIFY_LABEL"
              :disabled="busy"
              class="shrink-0 justify-center max-sm:w-full"
              data-resolve-notify
              @click="notify"
            />
          </div>
        </NuxtCard>

        <!-- 3. O que fazer: uma escolha por linha. A travada escreve o motivo. -->
        <NuxtRadioGroup
          v-model="picked"
          :items="items"
          variant="card"
          :legend="WHAT_TO_DO_LABEL"
          :disabled="busy"
          data-resolve-choices
        />

        <!-- 4. A proposta da escolha marcada, para quando o cliente responder. O lugar
             existe desde o início: escolher não empurra o resto para baixo do dedo. -->
        <NuxtCard variant="soft" as="section" data-resolve-message-block>
          <div class="flex min-w-0 flex-col gap-3">
            <h3 class="text-sm font-medium text-highlighted">
              {{ messageHeading(resolution.customer_name) }}
            </h3>
            <p
              v-if="choice"
              class="text-sm break-words whitespace-pre-line"
              data-resolve-message
            >
              {{ choice.message }}
            </p>
            <p v-else class="text-sm text-muted" data-resolve-message-pending>
              Escolha o que fazer para ver a mensagem.
            </p>
            <div v-if="choice" class="flex flex-wrap gap-2">
              <NuxtButton
                type="button"
                color="neutral"
                variant="outline"
                icon="i-lucide-copy"
                :label="COPY_MESSAGE_LABEL"
                class="max-sm:flex-1"
                data-resolve-copy
                @click="copyMessage"
              />
              <NuxtButton
                v-if="choice.whatsapp_url"
                :to="choice.whatsapp_url"
                target="_blank"
                rel="noopener"
                external
                color="neutral"
                variant="outline"
                icon="i-lucide-message-circle"
                :label="CALL_ON_WHATSAPP_LABEL"
                class="max-sm:flex-1"
                data-resolve-whatsapp
              />
              <NuxtButton
                v-else
                type="button"
                disabled
                color="neutral"
                variant="outline"
                icon="i-lucide-lock"
                :label="CALL_ON_WHATSAPP_LABEL"
                class="max-sm:flex-1"
                data-resolve-whatsapp
              />
            </div>
            <p
              v-if="copyNote"
              class="text-sm text-highlighted"
              role="status"
              data-resolve-copied
            >
              {{ copyNote }}
            </p>
            <!-- Sem WhatsApp no pedido: o motivo, escrito. -->
            <p
              v-if="!resolution.contact.enabled && resolution.contact.reason"
              class="text-xs text-muted"
              data-resolve-contact-reason
            >
              {{ resolution.contact.reason }}
            </p>
          </div>
        </NuxtCard>
      </div>
    </template>

    <!-- O rodapé não rola: a recusa, o aviso do gerente e os dois botões ficam à vista
         em qualquer altura de tela. -->
    <template #footer>
      <div class="grid w-full gap-3" data-resolve-footer>
        <NuxtAlert
          v-if="failure"
          color="error"
          variant="subtle"
          icon="i-lucide-triangle-alert"
          :description="failure"
          data-resolve-error
        />
        <p
          v-if="managerHint"
          class="text-end text-sm text-muted"
          data-resolve-manager-hint
        >
          {{ MANAGER_NEXT_STEP }}
        </p>
        <div class="flex justify-end gap-2">
          <NuxtButton
            type="button"
            color="neutral"
            variant="outline"
            label="Voltar"
            :disabled="busy"
            data-resolve-back
            @click="close(false)"
          />
          <template v-if="state === 'ready'">
            <!-- Trocar e remarcar moram no PDV, que abre na janela dele. -->
            <NuxtButton
              v-if="button.href && link"
              :to="button.href"
              :target="link.target"
              :rel="link.rel"
              external
              :color="button.color"
              :icon="button.icon"
              :label="button.label"
              data-resolve-conclude
              @click="close(false)"
            />
            <NuxtButton
              v-else
              type="button"
              :color="button.color"
              :icon="button.icon"
              :label="button.label"
              :disabled="button.disabled"
              :loading="busy"
              data-resolve-conclude
              @click="conclude"
            />
          </template>
        </div>
      </div>
    </template>
  </NuxtModal>

  <!-- Tirar o item devolve dinheiro: o gerente assina no diálogo de sempre, lendo a
       frase do dinheiro que o servidor escreveu. -->
  <OperatorManagerAuth
    :open="open && managerOpen"
    action="order_edit_refund"
    :operator-name="viewerName || undefined"
    :managers="managers"
    :busy="busy"
    :error="managerError"
    @update:open="
      (value: boolean) => {
        if (!value && !busy) managerOpen = false;
      }
    "
    @authorize="(username: string, pin: string) => send({ username, pin })"
    @authorize-badge="(badge: string) => send({ badge })"
  >
    <template v-if="choice?.detail" #context>
      <p class="text-sm font-medium" data-resolve-manager-detail>
        {{ choice.detail }}
      </p>
    </template>
  </OperatorManagerAuth>
</template>
