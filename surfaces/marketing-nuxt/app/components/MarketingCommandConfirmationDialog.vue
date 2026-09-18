<script setup lang="ts">
import type { PendingMarketingDecision } from "~/composables/useMarketingDecisionCommand";
import type { PendingCampaignFireCommand } from "~/composables/useCampaignFireCommand";
import { formatCount } from "~/presentation/campaign";
import {
  deliveryActionLabel,
  includesDirectMessage,
  includesPublicPost,
} from "~/presentation/marketingDelivery";
import { platformResultLabel } from "~/presentation/marketingResult";
import { scheduleSummary } from "~/utils/marketingSchedule";

const props = defineProps<{
  command: PendingMarketingDecision | PendingCampaignFireCommand | null;
  busy?: boolean;
  error?: string;
  shopTimezone: string;
  /** A imagem do anúncio que está sendo decidido, quando existe. O texto vem do
   *  próprio comando; a imagem não, porque o servidor congela o artefato por hash. */
  imageUrl?: string;
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
  if (props.command.action === "fire") return "Criar para revisão?";
  if (props.command.action === "reject") return "Recusar este anúncio?";
  if (props.command.body.publish_mode === "scheduled") return "Agendar?";
  if (includesDirectMessages.value && hasPublicPost.value)
    return "Disparar agora?";
  return includesDirectMessages.value ? "Enviar agora?" : "Publicar agora?";
});

const isFire = computed(() => props.command?.action === "fire");
const challengePlatforms = computed(() => challenge.value?.platforms ?? []);
const publicPlatforms = computed(() =>
  challengePlatforms.value.filter((platform) => platform !== "whatsapp"),
);
const includesDirectMessages = computed(() =>
  includesDirectMessage(challengePlatforms.value),
);
const hasPublicPost = computed(() =>
  includesPublicPost(challengePlatforms.value),
);

/** Este é o último botão do caminho e o único que faz alguma coisa sair. Os anteriores
 *  levam a algum lugar e dizem o lugar ("Revisar anúncio", "Visualizar consequência");
 *  este diz o ato, e o ato tem verbo próprio por destino — enviar, publicar, ou o
 *  genérico disparar quando o anúncio faz os dois. */
const confirmLabel = computed(() => {
  if (props.busy) return "Registrando…";
  if (isFire.value) return "Criar para revisão";
  if (props.command?.action === "reject") return "Recusar";
  return deliveryActionLabel({
    platforms: challengePlatforms.value,
    scheduled: Boolean(challenge.value?.scheduled_for),
  });
});

/** O que vai sair. Estava faltando: a caixa contava PARA QUEM e ONDE, e não mostrava
 *  O QUÊ — pedia a confirmação irreversível de um texto que o gestor não estava vendo.
 *  Sai do corpo congelado do próprio comando, que é exatamente o que o servidor vai
 *  publicar; ler do anúncio na tela mostraria uma edição posterior que não foi selada. */
const outgoing = computed(() => {
  const body = props.command?.body as Record<string, unknown> | undefined;
  const text = typeof body?.body === "string" ? body.body.trim() : "";
  // Com a cerquilha, como o gestor escreveu e como vai sair: o array guarda a palavra
  // crua, e mostrar "padaria" onde sai "#padaria" não é a prévia do que sai.
  const tags = Array.isArray(body?.hashtags)
    ? (body.hashtags as unknown[])
        .filter(
          (tag): tag is string => typeof tag === "string" && tag.length > 0,
        )
        .map((tag) => (tag.startsWith("#") ? tag : `#${tag}`))
    : [];
  return text || tags.length || props.imageUrl ? { text, tags } : null;
});

/** Uma linha por destino, e cada linha diz a grandeza daquele destino: mensagem conta
 *  PESSOAS, postagem conta a si mesma.
 *
 *  ⚠️ As plataformas de mural não se juntam numa linha só. "Instagram, Facebook · 1
 *  postagem em cada" obriga o leitor a distribuir o "1" entre as duas, e com uma
 *  plataforma sozinha o "em cada" fica sem complemento e não quer dizer nada. Uma
 *  linha por plataforma diz o mesmo sem pedir interpretação. */
const reachLines = computed(() => {
  const lines: string[] = [];
  if (includesDirectMessages.value) {
    const count = challenge.value?.audience_count ?? 0;
    lines.push(
      `WhatsApp · ${formatCount(count)} ${count === 1 ? "pessoa" : "pessoas"}`,
    );
  }
  for (const platform of publicPlatforms.value) {
    lines.push(`${platformResultLabel(platform)} · 1 postagem`);
  }
  return lines;
});

/** Postagem sem foto é um fato que só aparece depois de publicada, quando já não tem
 *  conserto. Se o disparo tem mural e não tem imagem, a caixa diz isso ANTES. */
const missingImageForPost = computed(
  () => hasPublicPost.value && !props.imageUrl,
);

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
        <!-- Uma linha. A descrição diz o que acontece DEPOIS do botão, e nada mais:
             quem está aqui já decidiu, só quer conferir antes de não poder voltar. -->
        <UiDialogDescription>
          <template v-if="isFire">Nada sai agora; vai para revisão.</template>
          <template v-else-if="command?.action === 'reject'">
            Não vai para lugar nenhum e não volta para a fila.
          </template>
          <template v-else-if="challenge?.scheduled_for">
            Depois de confirmar, sai sozinho na hora marcada.
          </template>
          <template v-else>Depois de confirmar, não tem desfazer.</template>
        </UiDialogDescription>
      </UiDialogHeader>

      <div v-if="challenge" class="space-y-3">
        <!-- ⚠️ O QUÊ vem antes do PARA QUEM: a caixa pedia uma confirmação sem volta
             de um texto que o gestor não estava vendo em lugar nenhum da tela. -->
        <div
          v-if="outgoing"
          class="flex gap-3 rounded-lg border border-border bg-muted/40 p-3"
        >
          <img
            v-if="imageUrl"
            :src="imageUrl"
            alt="Imagem do anúncio"
            class="size-16 shrink-0 rounded object-cover"
          />
          <div
            v-else-if="missingImageForPost"
            class="flex size-16 shrink-0 flex-col items-center justify-center gap-0.5 rounded border border-dashed border-warning/60 text-warning"
          >
            <Icon name="lucide:image-off" class="size-5" />
            <span class="text-[10px] font-medium leading-none">Sem foto</span>
          </div>
          <div class="min-w-0 text-sm">
            <p v-if="outgoing.text" class="max-h-28 overflow-y-auto whitespace-pre-line">
              {{ outgoing.text }}
            </p>
            <p v-if="outgoing.tags.length" class="mt-1 text-xs text-muted-foreground">
              {{ outgoing.tags.join(" ") }}
            </p>
          </div>
        </div>

        <ul class="space-y-0.5 text-sm font-medium" aria-label="Para quem vai">
          <li v-for="line in reachLines" :key="line">{{ line }}</li>
          <li v-if="!reachLines.length" class="text-muted-foreground">
            Nenhuma plataforma
          </li>
        </ul>

        <p v-if="challenge.scheduled_for" class="text-sm font-medium">
          {{ scheduleSummary(challenge.scheduled_for, shopTimezone) }}
        </p>

        <p
          v-if="isFire && command && 'productLabel' in command && command.productLabel"
          class="text-sm"
        >
          {{ command.productLabel }}
        </p>

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
