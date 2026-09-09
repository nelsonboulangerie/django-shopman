<script setup lang="ts">
import type { PendingMarketingDecision } from "~/composables/useMarketingDecisionCommand";
import { platformResultLabel } from "~/presentation/marketingResult";
import { scheduleSummary } from "~/utils/marketingSchedule";

const props = defineProps<{
  command: PendingMarketingDecision | null;
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
  if (props.command.action === "reject") return "Recusar este anúncio?";
  return props.command.body.publish_mode === "scheduled"
    ? "Confirmar este agendamento?"
    : "Confirmar publicação agora?";
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
        <UiDialogDescription>
          O servidor congelou esta versão e calculou a consequência abaixo. Nada
          é publicado até a confirmação final.
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
          <div>
            <dt class="text-xs text-muted-foreground">Público elegível</dt>
            <dd class="font-semibold">
              {{ challenge.audience_count }} destinos
            </dd>
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
          <div v-if="challenge.scheduled_for" class="sm:col-span-2">
            <dt class="text-xs text-muted-foreground">Instante absoluto</dt>
            <dd class="font-semibold">
              {{ scheduleSummary(challenge.scheduled_for, shopTimezone) }}
              ({{ shopTimezone }})
            </dd>
          </div>
        </dl>

        <div
          v-if="challenge.dual_control"
          class="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm"
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
            class="block text-sm font-medium"
          >
            Digite exatamente
            <code class="rounded bg-muted px-1.5 py-0.5">{{
              challenge.typed_phrase
            }}</code>
          </label>
          <input
            id="decision-typed-confirmation"
            v-model="typedConfirmation"
            type="text"
            autocomplete="off"
            spellcheck="false"
            class="mt-1 h-11 w-full rounded-md border border-border bg-background px-3 font-mono text-sm outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        <div v-if="challenge.step_up !== 'none'">
          <label for="decision-credential" class="block text-sm font-medium">
            {{
              challenge.step_up === "totp" ? "Código de 6 dígitos" : "Sua senha"
            }}
          </label>
          <input
            id="decision-credential"
            v-model="credential"
            :type="challenge.step_up === 'password' ? 'password' : 'text'"
            :inputmode="challenge.step_up === 'totp' ? 'numeric' : 'text'"
            :autocomplete="
              challenge.step_up === 'totp'
                ? 'one-time-code'
                : 'current-password'
            "
            :maxlength="challenge.step_up === 'totp' ? 6 : 200"
            class="mt-1 h-11 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
            @keyup.enter="submit"
          />
        </div>
      </div>

      <p v-if="error" class="text-sm text-destructive" role="alert">
        {{ error }}
      </p>

      <UiDialogFooter>
        <button
          type="button"
          class="min-h-11 rounded-md border border-border px-3 text-sm font-medium transition hover:bg-muted"
          :disabled="busy"
          @click="emit('cancel')"
        >
          Voltar sem publicar
        </button>
        <button
          type="button"
          class="min-h-11 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground transition hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="!ready"
          @click="submit"
        >
          {{ busy ? "Registrando…" : "Confirmar consequência" }}
        </button>
      </UiDialogFooter>
    </UiDialogContent>
  </UiDialog>
</template>
