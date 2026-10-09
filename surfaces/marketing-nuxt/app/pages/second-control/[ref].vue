<script setup lang="ts">
// A segunda pessoa, no celular dela (SUITE-UX §15, prévia v4 pino 7): o push "Fulano
// pede a sua confirmação" abre aqui. A tela mostra o MESMO selo (destinos, público,
// quando) e confirma com a digital do dispositivo, ou com o autenticador. Quem pediu
// não confirma o próprio pedido: o servidor recusa, e a tela nem oferece.
import { platformIcon } from "~/presentation/campaign";
import { sealConsequence, sealRows } from "~/presentation/marketingDelivery";
import { scheduleSummary } from "~/utils/marketingSchedule";

interface SecondControl {
  ref: string;
  state: "open" | "approved" | "used" | "expired";
  is_requester: boolean;
  requested_by: string;
  resource_ref: string;
  platforms: string[];
  audience_count: number;
  scheduled_for: string;
  expires_at: string;
}

const route = useRoute();
const confirmationRef = computed(() => String(route.params.ref || ""));
const { data, error, refresh, pending } = await useFetch<{ second_control: SecondControl }>(
  () => `/api/v1/backstage/marketing/security/second-control/${confirmationRef.value}/`,
  { key: () => `second-control-${confirmationRef.value}`, onResponseError: marketingSessionOnError },
);
const control = computed(() => data.value?.second_control ?? null);
/** Pedido que venceu ou não existe (404) não é erro de leitura: é o vazio desta tela. */
const missing = computed(() => {
  const status = (error.value as { statusCode?: number } | null)?.statusCode;
  return status === 404;
});
const { shopTimezone } = useCampaigns();

const rows = computed(() =>
  control.value ? sealRows({ platforms: control.value.platforms, audienceCount: control.value.audience_count }) : [],
);
const consequence = computed(() => (control.value ? sealConsequence(control.value.platforms) : ""));
const when = computed(() =>
  control.value?.scheduled_for ? scheduleSummary(control.value.scheduled_for, shopTimezone.value) : "Agora, assim que quem pediu confirmar",
);

const device = useDeviceSeal();
const usingCode = ref(false);
const code = ref("");
/** O autenticador digita casa a casa (`NuxtPinInput`); a confirmação leva o código inteiro. */
const codeDigits = computed({
  get: () => code.value.split(""),
  set: (digits: string[]) => {
    code.value = digits.join("").replace(/\D/g, "").slice(0, 6);
  },
});
const busy = ref(false);
const failure = ref("");

async function approve() {
  await $fetch(`/api/v1/backstage/marketing/security/second-control/${confirmationRef.value}/`, {
    method: "POST",
    credentials: "same-origin",
  });
  await refresh();
}

async function confirmWithDevice() {
  failure.value = "";
  busy.value = true;
  try {
    let outcome = await device.seal({ confirmationRef: confirmationRef.value });
    if (outcome === "needs_registration") {
      outcome = (await device.register()) ? await device.seal({ confirmationRef: confirmationRef.value }) : "cancelled";
    }
    if (outcome !== "sealed") {
      failure.value = device.error.value;
      return;
    }
    await approve();
  } catch (err) {
    flagMarketingSessionError(err);
    failure.value = httpErrorMessage(err, "Não deu para confirmar. Tente de novo.");
  } finally {
    busy.value = false;
  }
}

async function confirmWithCode() {
  if (!/^\d{6}$/.test(code.value.trim())) return;
  failure.value = "";
  busy.value = true;
  try {
    await $fetch("/api/v1/backstage/marketing/security/step-up/", {
      method: "POST",
      credentials: "same-origin",
      body: { method: "totp", credential: code.value.trim() },
    });
    await approve();
  } catch (err) {
    flagMarketingSessionError(err);
    failure.value = httpErrorMessage(err, "O código não conferiu. Tente de novo.");
  } finally {
    busy.value = false;
  }
}

useHead({ title: "Confirmação" });
</script>

<template>
  <main class="flex min-h-0 flex-1 flex-col" data-second-control>
    <OperatorPageHeader title="Pedido de confirmação">
      <template #lead>
        <NuxtButton
          to="/"
          color="neutral"
          variant="ghost"
          square
          icon="i-lucide-arrow-left"
          aria-label="Voltar às decisões"
          title="Voltar às decisões"
        />
      </template>
    </OperatorPageHeader>

    <section class="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
      <div class="mx-auto flex w-full max-w-lg flex-col gap-3">
        <OperatorScreenState
          v-if="pending && !control"
          state="loading"
          what="o pedido de confirmação"
        />
        <OperatorScreenState
          v-else-if="error && !missing"
          state="error"
          what="o pedido de confirmação"
          @retry="refresh()"
        />
        <OperatorScreenState
          v-else-if="!control"
          state="empty"
          icon="i-lucide-bell-off"
          title="Este pedido não existe mais"
          description="Ele vence em poucos minutos. Quem pediu pode chamar de novo."
        />
        <template v-else>
          <p class="text-base">
            <b class="font-semibold">{{ control.requested_by || "Uma pessoa" }}</b>
            {{ control.is_requester ? "(você) espera outra pessoa confirmar este envio." : "pede a sua confirmação para este envio." }}
          </p>
          <NuxtCard>
            <ul aria-label="Para quem vai" data-seal-rows>
              <li v-for="row in rows" :key="row.platform" class="flex min-h-13 items-center gap-3 py-2 [&+&]:border-t [&+&]:border-border">
                <Icon :name="platformIcon(row.platform)" class="size-5" aria-hidden="true" />
                <span class="min-w-0 flex-1 text-sm leading-tight">{{ row.label }} <span v-if="row.kind" class="block text-xs text-muted-foreground">{{ row.kind }}</span></span>
                <span class="tnum text-sm" :class="row.strong ? 'font-semibold' : ''">{{ row.amount }}</span>
              </li>
            </ul>
          </NuxtCard>
          <p class="text-sm text-muted-foreground">{{ when }}. {{ consequence }}</p>

          <NuxtAlert
            v-if="control.state === 'approved'"
            color="success"
            variant="subtle"
            icon="i-lucide-check"
            title="Confirmado. Quem pediu já pode enviar."
          />
          <NuxtAlert
            v-else-if="control.state !== 'open'"
            color="info"
            variant="subtle"
            :title="control.state === 'used' ? 'Este envio já saiu.' : 'O pedido venceu. Quem pediu pode chamar de novo.'"
          />
          <template v-else-if="!control.is_requester">
            <div v-if="usingCode || !device.supported.value" class="flex flex-col gap-3">
              <NuxtFormField label="Código do aplicativo autenticador">
                <NuxtPinInput
                  id="second-control-code"
                  v-model="codeDigits"
                  :length="6"
                  otp
                  :disabled="busy"
                  @keydown.enter="confirmWithCode"
                />
              </NuxtFormField>
              <NuxtButton
                size="xl"
                block
                label="Confirmar o envio"
                :disabled="busy || !/^\d{6}$/.test(code.trim())"
                @click="confirmWithCode"
              />
            </div>
            <NuxtButton
              v-else
              size="xl"
              block
              icon="i-lucide-fingerprint"
              label="Confirmar com a digital"
              :disabled="busy"
              data-second-control-device
              @click="confirmWithDevice"
            />
            <NuxtButton
              v-if="device.supported.value"
              class="self-center"
              color="neutral"
              variant="ghost"
              :label="usingCode ? 'Usar a digital do dispositivo' : 'Usar o autenticador'"
              @click="usingCode = !usingCode"
            />
          </template>
          <NuxtAlert v-if="failure" color="error" variant="subtle" :title="failure" />
        </template>
      </div>
    </section>
  </main>
</template>
