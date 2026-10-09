<script setup lang="ts">
// O SELO (v4, `marketing-decisoes4.html`, pinos 6 a 8): o que vai sair, onde, para
// quantos e quando, numa folha só; a frase do que volta e do que não volta; e a
// confirmação.
//
// Decisão do dono (SUITE-UX §15, 03/10/2026): confirma com a DIGITAL DO DISPOSITIVO,
// e o código de hoje (a frase "ENVIAR 86", a senha, o autenticador) fica como
// alternativa ("Usar o meu código"). Acima do limiar, outra pessoa confirma no
// celular dela: o selo chama essa pessoa por push e espera a confirmação dela aqui
// mesmo, em vez de só dizer "peça a alguém".
//
// O servidor continua mandando: a digital vale só para ESTA confirmação, e a segunda
// pessoa precisa ser outra, com a capacidade de aprovar e publicar.
import type { PendingMarketingDecision } from "~/composables/useMarketingDecisionCommand";
import type { PendingCampaignFireCommand } from "~/composables/useCampaignFireCommand";
import { platformIcon } from "~/presentation/campaign";
import {
  deliveryActionLabel,
  includesDirectMessage,
  includesPublicPost,
  sealConsequence,
  sealRows,
} from "~/presentation/marketingDelivery";
import { clientCount, formatCount } from "~/presentation/decisions";
import { platformResultLabel } from "~/presentation/marketingResult";
import { scenesFromFrozenCommand } from "~/presentation/simulatedPreview";
import { scheduleSummary } from "~/utils/marketingSchedule";

const props = defineProps<{
  command: PendingMarketingDecision | PendingCampaignFireCommand | null;
  busy?: boolean;
  error?: string;
  shopTimezone: string;
  /** A imagem do anúncio que está sendo decidido, quando existe. O texto vem do
   *  próprio comando; a imagem não, porque o servidor congela o artefato por hash. */
  imageUrl?: string;
  /** O conteúdo por plataforma do anúncio decidido (o formato público da prévia). */
  platformContent?: Record<string, Record<string, unknown>>;
}>();

const emit = defineEmits<{
  confirm: [
    value: {
      credential: string;
      typedConfirmation: string;
      deviceSealed?: boolean;
      secondApproved?: boolean;
    },
  ];
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

const device = useDeviceSeal();
/** A pessoa escolheu o código no lugar da digital (ou o dispositivo não tem digital). */
const usingCode = ref(false);
const sealError = ref("");

// A segunda pessoa (duplo controle): chamada por push, e o selo espera por ela.
const secondState = ref<"idle" | "calling" | "waiting" | "approved" | "expired">("idle");
const secondCalled = ref(0);
let secondTimer: ReturnType<typeof setInterval> | null = null;

function stopWaiting() {
  if (secondTimer) clearInterval(secondTimer);
  secondTimer = null;
}

watch(
  () => props.command?.challenge.ref,
  () => {
    credential.value = "";
    typedConfirmation.value = "";
    usingCode.value = false;
    sealError.value = "";
    secondState.value = "idle";
    secondCalled.value = 0;
    stopWaiting();
  },
);
onBeforeUnmount(stopWaiting);

const challenge = computed(() => props.command?.challenge ?? null);
const isFire = computed(() => props.command?.action === "fire");
const sealed = computed(() => props.command?.action === "approve");
const challengePlatforms = computed(() => challenge.value?.platforms ?? []);
const includesDirectMessages = computed(() =>
  includesDirectMessage(challengePlatforms.value),
);
const hasPublicPost = computed(() =>
  includesPublicPost(challengePlatforms.value),
);
const needsCode = computed(() => {
  const current = challenge.value;
  return Boolean(current && (current.step_up !== "none" || current.typed_phrase));
});
/** A digital é o caminho principal quando o selo pede algum código e o dispositivo
 *  sabe reconhecer a pessoa. Senão, os campos de sempre. */
const deviceFirst = computed(() => needsCode.value && device.supported.value && !usingCode.value);
const dualControl = computed(() => Boolean(challenge.value?.dual_control));
const secondApproved = computed(() => secondState.value === "approved");

const codeReady = computed(() => {
  const current = challenge.value;
  if (!current) return false;
  if (current.step_up === "totp" && !/^\d{6}$/.test(credential.value.trim())) return false;
  if (current.step_up === "password" && !credential.value) return false;
  if (current.typed_phrase && typedConfirmation.value.trim() !== current.typed_phrase) return false;
  return true;
});
const ready = computed(() => {
  if (!challenge.value || props.busy || device.busy.value) return false;
  if (dualControl.value && !secondApproved.value) return false;
  return deviceFirst.value || codeReady.value;
});

/** "Publicar para 3 destinos" (v4 pino 6): o ato e quantos lugares, numa linha. */
const title = computed(() => {
  if (!props.command) return "Confirmar decisão";
  if (isFire.value) return "Criar para revisão?";
  if (props.command.action === "reject") return "Recusar este anúncio?";
  const count = challengePlatforms.value.length;
  const places = `${count} ${count === 1 ? "destino" : "destinos"}`;
  if (props.command.body.publish_mode === "scheduled") return `Agendar para ${places}`;
  if (includesDirectMessages.value && hasPublicPost.value) return `Publicar e enviar para ${places}`;
  return includesDirectMessages.value ? `Enviar para ${places}` : `Publicar em ${places}`;
});

/** A linha sob o título: o que acontece, ou quando e para quantos. */
const description = computed(() => {
  if (isFire.value) return "Nada é disparado agora. O anúncio vai para revisão.";
  if (props.command?.action === "reject") return "Não vai para lugar nenhum e não volta para a fila.";
  return whenLine.value || "Depois de confirmar, não tem desfazer.";
});

/** O autenticador digita casa a casa (`NuxtPinInput`); o comando leva o código inteiro. */
const credentialDigits = computed({
  get: () => credential.value.split(""),
  set: (digits: string[]) => {
    credential.value = digits.join("").replace(/\D/g, "").slice(0, 6);
  },
});

/** "Agora, às 10:04 · 86 clientes no WhatsApp". */
const whenLine = computed(() => {
  const current = challenge.value;
  if (!current || !sealed.value) return "";
  const when = current.scheduled_for
    ? scheduleSummary(current.scheduled_for, props.shopTimezone)
    : `Agora, às ${new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: props.shopTimezone || undefined }).format(new Date())}`;
  return includesDirectMessages.value ? `${when} · ${clientCount(current.audience_count)} no WhatsApp` : when;
});

/** O último botão do caminho: o ato pelo nome ("Publicar e enviar"). */
const confirmLabel = computed(() => {
  if (props.busy) return "Registrando…";
  if (isFire.value) return "Criar para revisão";
  if (props.command?.action === "reject") return "Recusar";
  return deliveryActionLabel({
    platforms: challengePlatforms.value,
    scheduled: Boolean(challenge.value?.scheduled_for),
  });
});

/** O que vai sair, do corpo CONGELADO do comando (o que o servidor vai publicar). */
const outgoing = computed(() => {
  const body = props.command?.body as Record<string, unknown> | undefined;
  const text = typeof body?.body === "string" ? body.body.trim() : "";
  const tags = Array.isArray(body?.hashtags)
    ? (body.hashtags as unknown[])
        .filter((tag): tag is string => typeof tag === "string" && tag.length > 0)
        .map((tag) => (tag.startsWith("#") ? tag : `#${tag}`))
    : [];
  return text || tags.length || props.imageUrl ? { text, tags } : null;
});

/** A mesma prévia em tamanho real, também do corpo congelado (zero chamada ao servidor). */
const simulatedScenes = computed(() =>
  props.command?.action !== "approve" || !outgoing.value
    ? []
    : scenesFromFrozenCommand({
        frozenBody: props.command?.body as Record<string, unknown> | undefined,
        platforms: challengePlatforms.value,
        platformLabels: Object.fromEntries(
          challengePlatforms.value.map((platform) => [platform, platformResultLabel(platform)]),
        ),
        platformContent: props.platformContent,
        imageUrl: props.imageUrl,
      }),
);

const reach = computed(() =>
  sealRows({
    platforms: challengePlatforms.value,
    audienceCount: challenge.value?.audience_count ?? 0,
  }),
);
const consequence = computed(() =>
  sealed.value ? sealConsequence(challengePlatforms.value) : "",
);
const missingImageForPost = computed(() => hasPublicPost.value && !props.imageUrl);

/** Acima do limiar, outra pessoa confirma (v4 pino 7). Abaixo, o selo diz que basta você. */
const dualLine = computed(() => {
  const current = challenge.value;
  if (!current || !sealed.value) return null;
  const threshold = current.dual_control_threshold ?? 0;
  const people = formatCount(current.audience_count);
  if (current.dual_control && !threshold) {
    // O servidor exigiu duas pessoas sem dizer o limiar: diz o gesto mesmo assim.
    return { head: "Este disparo precisa de duas pessoas.", rest: " Outra pessoa com acesso ao Marketing confirma no celular dela (recebe o pedido por push)." };
  }
  if (!threshold || !includesDirectMessages.value) return null;
  const head = `Acima de ${formatCount(threshold)} clientes, outra pessoa confirma`;
  if (current.dual_control) {
    return { head, rest: ` no celular dela (recebe o pedido por push). Este envio tem ${people}: chame a segunda pessoa.` };
  }
  return { head, rest: ` no celular dela (recebe o pedido por push). Este envio tem ${people}: basta você.` };
});

const scheduledOutcomeNote = computed(() => {
  const subject =
    includesDirectMessages.value && hasPublicPost.value
      ? "o anúncio é disparado"
      : includesDirectMessages.value
        ? "a mensagem é enviada"
        : "a postagem é publicada";
  return `Depois de confirmar, ${subject} na hora marcada. Você não precisa voltar aqui.`;
});

async function callSecondPerson() {
  const current = challenge.value;
  if (!current) return;
  secondState.value = "calling";
  sealError.value = "";
  try {
    const response = await $fetch<{ called: number }>(
      "/api/v1/backstage/marketing/security/second-control/request/",
      { method: "POST", credentials: "same-origin", body: { confirmation_token: current.token } },
    );
    secondCalled.value = response.called;
    secondState.value = "waiting";
    stopWaiting();
    secondTimer = setInterval(checkSecondPerson, 3000);
  } catch (err) {
    flagMarketingSessionError(err);
    secondState.value = "idle";
    sealError.value = httpErrorMessage(err, "Não deu para chamar a segunda pessoa. Tente de novo.");
  }
}

async function checkSecondPerson() {
  const current = challenge.value;
  if (!current) return stopWaiting();
  try {
    const response = await $fetch<{ second_control: { state: string } }>(
      `/api/v1/backstage/marketing/security/second-control/${current.ref}/`,
      { credentials: "same-origin" },
    );
    const state = response.second_control.state;
    if (state === "approved") {
      secondState.value = "approved";
      stopWaiting();
    } else if (state === "expired" || state === "used") {
      secondState.value = "expired";
      stopWaiting();
    }
  } catch (err) {
    flagMarketingSessionError(err);
  }
}

async function submit() {
  if (!ready.value) return;
  const current = challenge.value;
  if (!current) return;
  if (deviceFirst.value) {
    sealError.value = "";
    let outcome = await device.seal({ confirmationToken: current.token });
    if (outcome === "needs_registration") {
      // Primeira vez neste dispositivo: cadastra a digital e assina em seguida.
      const registered = await device.register();
      outcome = registered ? await device.seal({ confirmationToken: current.token }) : "cancelled";
    }
    if (outcome !== "sealed") {
      sealError.value = device.error.value;
      return;
    }
    emit("confirm", { credential: "", typedConfirmation: "", deviceSealed: true, secondApproved: secondApproved.value });
    return;
  }
  emit("confirm", {
    credential: credential.value,
    typedConfirmation: typedConfirmation.value,
    secondApproved: secondApproved.value,
  });
}

// Celular: folha presa ao pé, largura inteira, cantos de cima arredondados e entrada
// de baixo para cima (as keyframes `slide-*-bottom` do próprio Nuxt UI, as mesmas do
// Slideover de baixo). Do `sm` para cima vale o modal centrado do tema.
const SEAL_SHEET_CLASS =
  "max-sm:inset-x-0 max-sm:top-auto max-sm:bottom-0 max-sm:left-0 max-sm:w-full max-sm:max-w-none max-sm:translate-x-0 max-sm:translate-y-0 max-sm:rounded-t-2xl max-sm:rounded-b-none max-sm:pb-[env(safe-area-inset-bottom)] max-sm:data-[state=open]:animate-[slide-in-from-bottom_200ms_var(--ease-out)] max-sm:data-[state=closed]:animate-[slide-out-to-bottom_200ms_var(--ease-out)]";
</script>

<template>
  <!-- O selo no NuxtModal do conjunto mínimo: título com o ato e quantos lugares, a
       linha do quando como descrição, o que sai, para quem, e a confirmação no rodapé.
       No celular a caixa sobe do pé como folha (v4, "a revisão aberta, com o selo"), ao
       alcance do polegar; do tablet para cima segue centrada. A troca é só de CSS
       (`SEAL_SHEET_CLASS`), sem ler a largura no script: o servidor já entrega certo. -->
  <NuxtModal
    :open="command !== null"
    :title="title"
    :description="description"
    :dismissible="!busy"
    :class="SEAL_SHEET_CLASS"
    @update:open="
      (open) => {
        if (!open && !busy) emit('cancel');
      }
    "
  >
    <!-- O carimbo redondo de quem aprova: o `actions` do cabeçalho vem depois do título
         no DOM, e o `order-first` o põe à esquerda dele, como no selo do v4. -->
    <template v-if="sealed" #actions>
      <span
        class="order-first me-1.5 grid size-10 shrink-0 place-items-center rounded-full bg-primary/15 text-primary"
        aria-hidden="true"
        data-seal-stamp
      >
        <Icon name="lucide:stamp" class="size-5" />
      </span>
    </template>
    <template #body>
      <div class="space-y-3" data-marketing-seal>
        <template v-if="challenge">
          <!-- O QUÊ antes do PARA QUEM. Do tablet para cima a caixa cobre a tela, então o
               resumo do que sai vem junto; no celular a revisão já mostra foto e texto. -->
          <NuxtCard v-if="outgoing" variant="soft" class="max-sm:hidden">
            <div class="flex gap-3">
              <img v-if="imageUrl" :src="imageUrl" alt="Imagem do anúncio" class="size-16 shrink-0 rounded object-cover">
              <div
                v-else-if="missingImageForPost"
                class="flex size-16 shrink-0 flex-col items-center justify-center gap-0.5 rounded border border-dashed border-warning/60 text-warning"
              >
                <Icon name="lucide:image-off" class="size-5" />
                <span class="text-xs font-medium leading-none">Sem foto</span>
              </div>
              <div class="min-w-0 flex-1 text-sm">
                <p v-if="outgoing.text" class="max-h-28 overflow-y-auto whitespace-pre-line">{{ outgoing.text }}</p>
                <p v-if="outgoing.tags.length" class="mt-1 text-xs text-muted-foreground">{{ outgoing.tags.join(" ") }}</p>
              </div>
              <AnnouncementSimulatedPreview :scenes="simulatedScenes" trigger-class="-my-1 shrink-0 self-start" />
            </div>
          </NuxtCard>

          <ul class="rounded-lg border border-border px-3.5" aria-label="Para quem vai" data-seal-rows>
            <li
              v-for="row in reach"
              :key="row.platform"
              class="flex min-h-13 items-center gap-3 py-2 [&+&]:border-t [&+&]:border-border"
              :data-seal-row="row.platform"
            >
              <Icon :name="platformIcon(row.platform)" class="size-5" aria-hidden="true" />
              <span class="min-w-0 flex-1 text-sm leading-tight">{{ row.label }} <span v-if="row.kind" class="block text-xs text-muted-foreground">{{ row.kind }}</span></span>
              <span class="tnum text-sm" :class="row.strong ? 'font-semibold' : ''">{{ row.amount }}</span>
            </li>
            <li v-if="!reach.length" class="flex min-h-13 items-center text-sm text-muted-foreground">Nenhuma plataforma</li>
          </ul>
          <p v-if="consequence" class="text-sm leading-snug text-muted-foreground" data-seal-consequence>{{ consequence }}</p>

          <p v-if="challenge.scheduled_for && !whenLine" class="text-sm font-medium">
            {{ scheduleSummary(challenge.scheduled_for, shopTimezone) }}
          </p>
          <p v-if="challenge.scheduled_for" class="text-sm text-muted-foreground">{{ scheduledOutcomeNote }}</p>

          <p v-if="isFire && command && 'productLabel' in command && command.productLabel" class="text-sm">
            {{ command.productLabel }}
          </p>

          <!-- Segunda pessoa (v4 pino 7): aviso que pede gesto quando o servidor exige
               duas pessoas; informação quando basta você. -->
          <NuxtAlert
            v-if="dualLine"
            :color="dualControl ? 'warning' : 'info'"
            variant="subtle"
            icon="i-lucide-users"
            :role="dualControl ? 'alert' : 'status'"
            data-seal-dual
          >
            <template #description>
              <p><b class="font-semibold">{{ dualLine.head }}</b>{{ dualLine.rest }}</p>
              <template v-if="dualControl">
                <p v-if="secondState === 'calling'" class="mt-2" role="status">Chamando…</p>
                <p v-else-if="secondState === 'waiting'" class="mt-2 flex items-center gap-1.5" role="status" data-seal-waiting>
                  <Icon name="lucide:loader-circle" class="size-4 animate-spin" aria-hidden="true" />
                  {{ secondCalled ? `Pedido enviado a ${secondCalled} ${secondCalled === 1 ? "pessoa" : "pessoas"}.` : "Pedido enviado." }}
                  Esperando a confirmação no celular.
                </p>
                <p v-else-if="secondState === 'approved'" class="mt-2 flex items-center gap-1.5 font-semibold text-success" role="status" data-seal-second-approved>
                  <Icon name="lucide:check" class="size-4" aria-hidden="true" />
                  A segunda pessoa confirmou.
                </p>
              </template>
            </template>
            <template v-if="dualControl && (secondState === 'idle' || secondState === 'expired')" #actions>
              <NuxtButton
                color="warning"
                variant="outline"
                icon="i-lucide-bell-ring"
                :label="secondState === 'expired' ? 'O pedido venceu. Chamar de novo' : 'Pedir a confirmação de outra pessoa'"
                :disabled="device.busy.value"
                data-seal-call-second
                @click="callSecondPerson"
              />
            </template>
          </NuxtAlert>

          <!-- O código de sempre: alternativa à digital, ou o caminho quando o dispositivo
               não reconhece a pessoa. -->
          <template v-if="!deviceFirst">
            <NuxtFormField v-if="challenge.typed_phrase" label="Digite exatamente esta frase">
              <p id="decision-typed-phrase" class="mb-1.5">
                <code class="rounded bg-muted px-1.5 py-0.5 text-sm">{{ challenge.typed_phrase }}</code>
              </p>
              <NuxtTextarea
                id="decision-typed-confirmation"
                v-model="typedConfirmation"
                aria-describedby="decision-typed-phrase"
                name="typed_confirmation"
                :rows="1"
                autocomplete="off"
                spellcheck="false"
                class="w-full font-mono"
              />
            </NuxtFormField>

            <template v-if="challenge.step_up !== 'none'">
              <NuxtFormField v-if="challenge.step_up === 'password'" label="Usuário">
                <NuxtInput
                  id="decision-username"
                  name="username"
                  :model-value="operatorUsername"
                  type="text"
                  autocomplete="username"
                  readonly
                  class="w-full"
                />
              </NuxtFormField>
              <NuxtFormField v-if="challenge.step_up === 'totp'" label="Código de 6 dígitos do autenticador">
                <NuxtPinInput
                  id="decision-credential"
                  v-model="credentialDigits"
                  :length="6"
                  otp
                  :disabled="busy"
                  @keydown.enter="submit"
                />
              </NuxtFormField>
              <NuxtFormField v-else-if="challenge.step_up === 'password'" label="Sua senha">
                <NuxtInput
                  id="decision-credential"
                  v-model="credential"
                  name="current_password"
                  type="password"
                  autocomplete="current-password"
                  :maxlength="200"
                  class="w-full"
                  @keyup.enter="submit"
                />
              </NuxtFormField>
            </template>
          </template>
        </template>

        <NuxtAlert
          v-if="error || sealError"
          color="error"
          variant="subtle"
          :title="error || sealError"
        />
      </div>
    </template>

    <template #footer>
      <div class="flex w-full flex-col gap-2">
        <div class="flex w-full justify-end gap-2">
          <NuxtButton
            color="neutral"
            variant="outline"
            label="Voltar"
            :disabled="busy"
            @click="emit('cancel')"
          />
          <NuxtButton
            :icon="deviceFirst ? 'i-lucide-fingerprint' : undefined"
            :label="confirmLabel"
            :disabled="!ready"
            class="max-sm:flex-1 max-sm:justify-center"
            data-seal-confirm
            @click="submit"
          />
        </div>
        <p v-if="needsCode && device.supported.value" class="flex flex-wrap items-center justify-end gap-x-1 text-sm text-muted-foreground" data-seal-method>
          <template v-if="!usingCode">
            Confirma com a digital do dispositivo ·
            <NuxtButton color="neutral" variant="ghost" label="Usar o meu código" data-seal-use-code @click="usingCode = true" />
          </template>
          <template v-else>
            Confirma com o seu código ·
            <NuxtButton color="neutral" variant="ghost" label="Usar a digital" @click="usingCode = false" />
          </template>
        </p>
      </div>
    </template>
  </NuxtModal>
</template>
