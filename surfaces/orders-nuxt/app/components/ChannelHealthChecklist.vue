<script setup lang="ts">
// O checklist vivo do canal: o que falta para ele funcionar, cada item com o gesto
// que resolve. Canal com pendência nasce ABERTO; canal pronto mostra só "Tudo certo",
// recolhido. Mora num componente próprio para entrar no card com uma linha só.
import {
  itemAction,
  orderedItems,
  pairUrl,
  previewHref,
  type HealthAction,
} from "~/presentation/channelHealth";
import type { ChannelHealthProjection } from "~/types/channelHealth";

const props = defineProps<{ health: ChannelHealthProjection | null }>();
const emit = defineEmits<{ "choose-collections": [] }>();

const runtimeConfig = useRuntimeConfig();
const bases = {
  djangoBase: String(runtimeConfig.public.djangoBaseUrl ?? ""),
  adminBase: String(runtimeConfig.public.adminBaseUrl ?? ""),
};

const expanded = ref(false);
const open = computed(() =>
  Boolean(props.health && (!props.health.ready || expanded.value)),
);
const items = computed(() => (props.health ? orderedItems(props.health) : []));
const actionOf = (key: string): HealthAction | null => {
  const item = props.health?.items.find((i) => i.key === key);
  return item ? itemAction(item, bases) : null;
};

// Parear uma TV: o endereço que ela abre + o QR do mesmo endereço.
const pairing = ref(false);
const address = computed(() =>
  props.health ? pairUrl(props.health, bases) : "",
);
const qr = ref<HTMLCanvasElement | null>(null);
const copied = ref(false);
watch(
  [pairing, qr, address],
  async ([show, canvas, text]) => {
    if (!show || !canvas || !text) return;
    try {
      const { toCanvas } = await import("qrcode");
      await toCanvas(canvas, text, { width: 160, margin: 1 });
    } catch {
      // Sem QR, o endereço escrito continua servindo.
    }
  },
  { flush: "post" },
);
async function copyAddress() {
  try {
    await navigator.clipboard.writeText(address.value);
    copied.value = true;
    setTimeout(() => {
      copied.value = false;
    }, 2000);
  } catch {
    copied.value = false;
  }
}

function run(action: HealthAction) {
  if (action.kind === "pair") pairing.value = !pairing.value;
  else if (action.kind === "collections") emit("choose-collections");
}
</script>

<template>
  <section
    v-if="health"
    class="space-y-2"
    :data-channel-health="health.ref"
    aria-label="O que falta para este canal funcionar"
  >
    <NuxtSeparator />
    <div class="flex items-center gap-2">
      <Icon
        :name="health.ready ? 'lucide:circle-check' : 'lucide:list-checks'"
        class="size-4"
        :class="health.ready ? 'text-success' : 'text-warning'"
      />
      <p class="flex-1 text-sm font-medium" data-health-summary>
        {{ health.summary }}
      </p>
      <NuxtButton
        v-if="health.ready"
        type="button"
        color="neutral"
        variant="ghost"
        :label="expanded ? 'Recolher' : 'Ver o que foi conferido'"
        :trailing-icon="
          expanded ? 'i-lucide-chevron-up' : 'i-lucide-chevron-down'
        "
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      />
    </div>

    <ul v-if="open" class="space-y-1.5" data-health-items>
      <li
        v-for="item in items"
        :key="item.key"
        class="flex items-start gap-2 text-sm"
        :data-health-item="item.key"
        :data-state="item.state"
      >
        <Icon
          :name="item.state === 'ok' ? 'lucide:check' : 'lucide:circle-alert'"
          class="mt-0.5 size-4 shrink-0"
          :class="item.state === 'ok' ? 'text-success' : 'text-warning'"
        />
        <div class="min-w-0 flex-1">
          <p
            :class="
              item.state === 'ok' ? 'text-muted-foreground' : 'text-foreground'
            "
          >
            {{ item.label }}
          </p>
          <p
            v-if="item.hint && item.state !== 'ok'"
            class="text-xs text-muted-foreground"
          >
            {{ item.hint }}
          </p>
        </div>
        <template v-if="item.state !== 'ok' && actionOf(item.key)">
          <NuxtButton
            v-if="actionOf(item.key)!.kind === 'route'"
            :to="(actionOf(item.key) as { to: string }).to"
            :label="actionOf(item.key)!.label"
            color="neutral"
            variant="outline"
            size="xs"
            data-health-action
          />
          <NuxtButton
            v-else-if="actionOf(item.key)!.kind === 'external'"
            :to="(actionOf(item.key) as { href: string }).href"
            target="_blank"
            :label="actionOf(item.key)!.label"
            trailing-icon="i-lucide-external-link"
            color="neutral"
            variant="outline"
            size="xs"
            data-health-action
          />
          <NuxtButton
            v-else
            type="button"
            :label="actionOf(item.key)!.label"
            color="neutral"
            variant="outline"
            size="xs"
            data-health-action
            @click="run(actionOf(item.key)!)"
          />
        </template>
      </li>
    </ul>

    <NuxtAlert
      v-if="pairing && address"
      color="info"
      variant="subtle"
      orientation="vertical"
      icon="i-lucide-qr-code"
      title="Parear uma TV"
      data-health-pairing
    >
      <template #description>
        <ol class="list-decimal space-y-1 ps-5 text-xs text-muted-foreground">
          <li>
            Na TV, ou no dispositivo ligado a ela, abra o endereço abaixo (ou
            leia o QR com a câmera dele).
          </li>
          <li>
            Entre uma vez com um operador. A TV fica autorizada e não pede mais
            nada.
          </li>
        </ol>
        <div class="mt-3 flex flex-wrap items-center gap-3">
          <canvas
            ref="qr"
            class="rounded bg-white"
            width="160"
            height="160"
            aria-label="QR do endereço da TV"
          />
          <code
            class="min-w-0 flex-1 break-all rounded bg-background px-2 py-1 text-xs"
            data-health-address
            >{{ address }}</code
          >
        </div>
      </template>
      <template #actions>
        <NuxtButton
          type="button"
          :icon="copied ? 'i-lucide-check' : 'i-lucide-copy'"
          :label="copied ? 'Endereço copiado' : 'Copiar endereço'"
          color="info"
          variant="outline"
          @click="copyAddress"
        />
      </template>
    </NuxtAlert>

    <div v-if="health.preview.length" class="flex flex-wrap gap-1.5">
      <NuxtButton
        v-for="link in health.preview"
        :key="link.path"
        :to="previewHref(link, bases)"
        target="_blank"
        icon="i-lucide-eye"
        :label="link.label"
        color="neutral"
        variant="link"
        size="xs"
        data-health-preview
      />
    </div>
  </section>
</template>
