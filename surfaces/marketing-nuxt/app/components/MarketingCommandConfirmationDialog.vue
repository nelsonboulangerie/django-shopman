<script setup lang="ts">
import type { PendingMarketingDecision } from "~/composables/useMarketingDecisionCommand";
import type { PendingCampaignFireCommand } from "~/composables/useCampaignFireCommand";
import { formatCount } from "~/presentation/campaign";
import {
  deliveryActionLabel,
  includesDirectMessage,
  includesPublicPublication,
} from "~/presentation/marketingDelivery";
import { platformResultLabel } from "~/presentation/marketingResult";
import { scheduleSummary } from "~/utils/marketingSchedule";

const props = defineProps<{
  command: PendingMarketingDecision | PendingCampaignFireCommand | null;
  busy?: boolean;
  error?: string;
  shopTimezone: string;
}>();

const emit = defineEmits<{
  confirm: [value: { credential: string; typedConfirmation: string }];
  cancel: [];
}>();

const credential = ref("");
const typedConfirmation = ref("");
const { data: operatorSession } = useNuxtData<{
  operator: { username?: string; name?: string } | null;
}>("operator-session");
const operatorUsername = computed(
  () => operatorSession.value?.operator?.username?.trim() || "",
);

watch(
  () => props.command?.challenge.ref,
  () => {
    credential.value = "";
    typedConfirmation.value = "";
  },
);

const challenge = computed(() => props.command?.challenge ?? null);
const ready = computed(() => {
  const current = challenge.value;
  if (!current || current.dual_control || props.busy) return false;
  if (current.step_up === "totp" && !/^\d{6}$/.test(credential.value.trim()))
    return false;
  if (current.step_up === "password" && !credential.value) return false;
  if (
    current.typed_phrase &&
    typedConfirmation.value.trim() !== current.typed_phrase
  )
    return false;
  return true;
});

const title = computed(() => {
  if (!props.command) return "Confirmar decisão";
  if (props.command.action === "fire") return "Confirmar este disparo?";
  if (props.command.action === "reject") return "Recusar este anúncio?";
  if (props.command.body.publish_mode === "scheduled")
    return "Confirmar este agendamento?";
  if (includesDirectMessages.value && hasPublicPublication.value)
    return "Confirmar esta entrega agora?";
  return includesDirectMessages.value
    ? "Confirmar envio agora?"
    : "Confirmar publicação agora?";
});

const isFire = computed(() => props.command?.action === "fire");
const challengePlatforms = computed(() => challenge.value?.platforms ?? []);
const publicPlatforms = computed(() =>
  challengePlatforms.value.filter((platform) => platform !== "whatsapp"),
);
const includesDirectMessages = computed(() =>
  includesDirectMessage(challengePlatforms.value),
);
const hasPublicPublication = computed(() =>
  includesPublicPublication(challengePlatforms.value),
);

/** O botão diz o efeito, não a categoria dele. "Confirmar consequência" obrigava o
 *  gestor a traduzir jargão no exato momento em que precisava decidir. */
const confirmLabel = computed(() => {
  if (props.busy) return "Registrando…";
  if (isFire.value) return "Criar para revisão";
  if (props.command?.action === "reject") return "Recusar";
  return deliveryActionLabel({
    platforms: challengePlatforms.value,
    scheduled: Boolean(challenge.value?.scheduled_for),
  });
});

function submit() {
  if (!ready.value) return;
  emit("confirm", {
    credential: credential.value,
    typedConfirmation: typedConfirmation.value,
  });
}
</script>

<template>
  <UiDialog
    :open="command !== null"
    @update:open="
      (open) => {
        if (!open && !busy) emit('cancel');
      }
    "
  >
    <UiDialogContent class="sm:max-w-lg">
      <UiDialogHeader>
        <UiDialogTitle>{{ title }}</UiDialogTitle>
        <!-- A descrição diz o que acontece DEPOIS deste botão. Dizer "nada sai até a
             confirmação final" quando este botão É a confirmação final ensinava o
             gestor a não acreditar na própria tela. -->
        <UiDialogDescription>
          <template v-if="isFire">
            Isto cria um anúncio para revisão. Nada é publicado nem enviado
            agora.
          </template>
          <template v-else-if="command?.action === 'reject'">
            O anúncio não vai para nenhuma plataforma e não volta para a fila.
          </template>
          <template v-else-if="challenge?.scheduled_for">
            Confira o que foi congelado. Depois de confirmar, a entrega acontece
            sozinha no instante abaixo.
          </template>
          <template v-else>
            Confira o que foi congelado. Depois de confirmar, isto sai — e não
            tem desfazer.
          </template>
        </UiDialogDescription>
      </UiDialogHeader>

      <div v-if="challenge" class="space-y-4">
        <dl
          class="grid gap-2 rounded-lg border border-border bg-muted/50 p-3 text-sm sm:grid-cols-2"
        >
          <div>
            <dt class="text-xs text-muted-foreground">Versão</dt>
            <dd class="font-semibold">{{ challenge.base_version }}</dd>
          </div>
          <div v-if="includesDirectMessages">
            <dt class="text-xs text-muted-foreground">
              Pessoas para mensagem direta
            </dt>
            <dd class="font-semibold">
              {{ formatCount(challenge.audience_count) }}
              {{ challenge.audience_count === 1 ? "pessoa" : "pessoas" }}
            </dd>
          </div>
          <div v-else>
            <dt class="text-xs text-muted-foreground">Público da publicação</dt>
            <dd class="font-semibold">Público geral da plataforma</dd>
          </div>
          <div class="sm:col-span-2">
            <dt class="text-xs text-muted-foreground">Plataformas</dt>
            <dd class="font-semibold">
              {{
                challenge.platforms.map(platformResultLabel).join(", ") ||
                "Nenhuma"
              }}
            </dd>
          </div>
          <div
            v-if="
              isFire &&
              command &&
              'productLabel' in command &&
              command.productLabel
            "
            class="sm:col-span-2"
          >
            <dt class="text-xs text-muted-foreground">Produto</dt>
            <dd class="font-semibold">{{ command.productLabel }}</dd>
          </div>
          <div v-if="challenge.scheduled_for" class="sm:col-span-2">
            <dt class="text-xs text-muted-foreground">Instante absoluto</dt>
            <dd class="font-semibold">
              {{ scheduleSummary(challenge.scheduled_for, shopTimezone) }}
              ({{ shopTimezone }})
            </dd>
          </div>
        </dl>

        <ul
          class="space-y-1 rounded-lg border border-sky-500/30 bg-sky-500/5 p-3 text-sm"
          aria-label="Forma de entrega por plataforma"
        >
          <li v-if="publicPlatforms.length">
            <strong
              >{{
                publicPlatforms.map(platformResultLabel).join(", ")
              }}:</strong
            >
            uma postagem pública por plataforma; não envia mensagem direta por
            pessoa.
          </li>
          <li v-if="includesDirectMessages">
            <strong>WhatsApp:</strong>
            mensagem direta para as pessoas elegíveis, com consentimento
            revalidado no envio.
          </li>
        </ul>

        <div
          v-if="challenge.dual_control"
          class="rounded-lg border border-warning/40 bg-warning/5 p-3 text-sm"
          role="alert"
        >
          <p class="font-semibold">Este volume exige duas pessoas.</p>
          <p class="mt-1 text-muted-foreground">
            A confirmação independente continua obrigatória; esta sessão não
            substitui o segundo controle.
          </p>
        </div>

        <div v-if="challenge.typed_phrase">
          <label
            for="decision-typed-confirmation"
            class="block text-xs font-medium text-muted-foreground"
          >
            Digite exatamente
            <code class="rounded bg-muted px-1.5 py-0.5">{{
              challenge.typed_phrase
            }}</code>
          </label>
          <UiTextarea
            id="decision-typed-confirmation"
            v-model="typedConfirmation"
            name="typed_confirmation"
            :rows="1"
            autocomplete="off"
            spellcheck="false"
            class="mt-1 min-h-11 resize-none font-mono"
          />
        </div>

        <div v-if="challenge.step_up !== 'none'">
          <div v-if="challenge.step_up === 'password'" class="mb-3">
            <label
              for="decision-username"
              class="block text-xs font-medium text-muted-foreground"
            >
              Usuário
            </label>
            <UiInput
              id="decision-username"
              name="username"
              :model-value="operatorUsername"
              type="text"
              autocomplete="username"
              readonly
              class="mt-1 bg-muted text-muted-foreground"
            />
          </div>
          <UiVerificationCodeInput
            v-if="challenge.step_up === 'totp'"
            id="decision-credential"
            v-model="credential"
            :disabled="busy"
            @keydown.enter="submit"
          />
          <template v-else>
            <label
              for="decision-credential"
              class="block text-xs font-medium text-muted-foreground"
            >
              Sua senha
            </label>
            <UiInput
              id="decision-credential"
              v-model="credential"
              name="current_password"
              type="password"
              autocomplete="current-password"
              :maxlength="200"
              class="mt-1"
              @keyup.enter="submit"
            />
          </template>
        </div>
      </div>

      <p v-if="error" class="text-sm text-destructive" role="alert">
        {{ error }}
      </p>

      <UiDialogFooter>
        <UiButton
          type="button"
          variant="outline"
          :disabled="busy"
          @click="emit('cancel')"
        >
          {{ isFire ? "Voltar sem criar" : "Voltar sem confirmar" }}
        </UiButton>
        <UiButton type="button" :disabled="!ready" @click="submit">
          {{ confirmLabel }}
        </UiButton>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
