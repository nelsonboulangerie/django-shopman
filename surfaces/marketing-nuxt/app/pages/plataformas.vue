<script setup lang="ts">
// Plataformas — por onde a padaria consegue falar, e o que falta.
//
// ⚠️ Esta tela existe porque o estado das plataformas não tinha casa. O seletor do template
// aprovado do WhatsApp e o teste de envio moravam DENTRO de um painel de configuração
// DENTRO da tela de revisão, e o botão que os abria vivia no cabeçalho do painel — remendo
// que o dono apontou. Ver `docs/plans/MARKETING-UX-PLAN.md`.
//
// Plataforma ≠ canal: canal é por onde se VENDE, plataforma é por onde o anúncio SAI.
import { platformIcon } from "~/presentation/campaign";

const { platforms, loading } = usePlatforms();
const waTemplate = useWhatsAppTemplate();

const savingTemplate = ref(false);
const testRecipient = ref("");
const testSku = ref("");
const testName = ref("");

onMounted(() => { waTemplate.load(); });

async function onChooseTemplate(flowNs: string) {
  savingTemplate.value = true;
  await waTemplate.choose(flowNs);
  savingTemplate.value = false;
}

async function onSendTest() {
  if (!testRecipient.value.trim()) return;
  await waTemplate.sendTest(testRecipient.value.trim(), {
    sku: testSku.value.trim(),
    name: testName.value.trim(),
  });
}

/** Bloqueio, limitação e saúde não podem parecer iguais. */
function tone(ready: boolean, limitation: string) {
  if (!ready) return { chip: "bg-destructive/10 text-destructive", icon: "lucide:circle-slash", label: "não publica" };
  if (limitation) return { chip: "bg-amber-500/10 text-amber-700 dark:text-amber-400", icon: "lucide:triangle-alert", label: "alcance limitado" };
  return { chip: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400", icon: "lucide:check", label: "pronta" };
}

useHead({ title: "Plataformas · Marketing" });
</script>

<template>
  <main class="mx-auto w-full max-w-3xl flex-1 px-4 py-6">
    <h1 class="mb-1 text-xl font-semibold">Plataformas</h1>
    <p class="mb-4 text-sm text-muted-foreground">
      Por onde o anúncio sai. Quem vende é o canal; aqui é quem fala.
    </p>

    <div v-if="loading && !platforms.length" class="space-y-2" aria-busy="true">
      <div v-for="n in 4" :key="n" class="h-24 animate-pulse rounded-xl bg-muted"></div>
    </div>

    <ul v-else class="space-y-3">
      <li
        v-for="platform in platforms"
        :key="platform.platform"
        class="rounded-xl border border-border bg-card p-4"
      >
        <div class="flex items-start gap-3">
          <Icon :name="platformIcon(platform.platform)" class="mt-0.5 size-5 shrink-0 text-muted-foreground" />
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <p class="font-semibold">{{ platform.label }}</p>
              <span
                class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
                :class="tone(platform.ready, platform.limitation).chip"
              >
                <Icon :name="tone(platform.ready, platform.limitation).icon" class="size-3" />
                {{ tone(platform.ready, platform.limitation).label }}
              </span>
              <!-- Plataforma que nenhuma campanha ativa usa não é problema: ligar
                   credencial de algo sem uso é trabalho jogado fora. -->
              <span
                v-if="!platform.in_use"
                class="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                title="Nenhuma campanha ativa publica aqui"
              >
                sem uso
              </span>
            </div>

            <p class="mt-1 text-sm text-muted-foreground">
              {{ platform.reason || platform.limitation || (platform.kind === "direct_message"
                ? "Uma mensagem por pessoa, com consentimento."
                : "Uma peça publicada na plataforma.") }}
            </p>
            <p v-if="platform.action && !platform.ready" class="mt-1 text-xs font-medium">
              {{ platform.action }}
            </p>
          </div>
        </div>

        <!-- O WhatsApp é a única que se resolve DAQUI: escolher o template e testar. As
             outras dependem de credencial de plataforma, que não se digita numa tela. -->
        <section v-if="platform.platform === 'whatsapp'" class="mt-4 border-t border-border pt-4">
          <h2 class="text-sm font-semibold">Template aprovado</h2>
          <p class="mt-0.5 text-xs text-muted-foreground">
            Com um template aprovado, o anúncio alcança quem não conversou nas últimas 24
            horas. Sem ele, só a janela.
          </p>

          <div v-if="waTemplate.loading.value" class="mt-3 space-y-2" aria-busy="true">
            <div v-for="n in 2" :key="n" class="h-10 animate-pulse rounded-md bg-muted"></div>
          </div>

          <!-- Não conseguir perguntar à plataforma NÃO é "não há template". -->
          <div
            v-else-if="!waTemplate.canList.value"
            class="mt-3 rounded-lg border border-border bg-muted/40 px-3 py-2.5 text-sm"
          >
            <p class="font-semibold">Não foi possível consultar os templates agora</p>
            <p class="mt-1 text-muted-foreground">
              A plataforma não respondeu. Tente de novo em instantes; nada foi alterado.
            </p>
          </div>

          <div v-else class="mt-3 space-y-1.5">
            <button
              type="button"
              class="flex w-full items-start gap-2 rounded-lg border px-3 py-2.5 text-left transition hover:bg-muted"
              :class="waTemplate.current.value === '' ? 'border-primary' : 'border-border'"
              :disabled="savingTemplate"
              @click="onChooseTemplate('')"
            >
              <Icon name="lucide:circle-slash" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <span>
                <span class="block text-sm font-medium">Sem template</span>
                <span class="block text-xs text-muted-foreground">
                  Texto livre — alcança só quem conversou nas últimas 24 horas.
                </span>
              </span>
            </button>

            <button
              v-for="option in waTemplate.available.value"
              :key="option.ns"
              type="button"
              class="flex w-full items-start gap-2 rounded-lg border px-3 py-2.5 text-left transition hover:bg-muted"
              :class="waTemplate.current.value === option.ns ? 'border-primary' : 'border-border'"
              :disabled="savingTemplate"
              @click="onChooseTemplate(option.ns)"
            >
              <Icon name="lucide:file-check-2" class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <span class="min-w-0">
                <span class="block truncate text-sm font-medium">{{ option.name }}</span>
                <span class="block truncate font-mono text-xs text-muted-foreground">
                  {{ option.ns }}
                </span>
              </span>
            </button>
          </div>

          <!-- Conferir vale mais que supor: aceito pelo provedor não é o mesmo que vibrou
               no aparelho. Um número por vez, digitado, sem lista de cliente por perto. -->
          <div class="mt-4 border-t border-border pt-4">
            <h2 class="text-sm font-semibold">Testar no meu WhatsApp</h2>
            <p class="mt-0.5 text-xs text-muted-foreground">
              Manda uma mensagem só para você, com as variáveis preenchidas de verdade.
            </p>

            <div class="mt-3 space-y-2">
              <div>
                <label for="test-recipient" class="mb-1 block text-xs font-medium">
                  WhatsApp ou subscriber
                </label>
                <input
                  id="test-recipient"
                  v-model="testRecipient"
                  type="text"
                  placeholder="4605528796186498"
                  class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                >
              </div>
              <div class="grid grid-cols-2 gap-2">
                <div>
                  <label for="test-sku" class="mb-1 block text-xs font-medium">SKU (opcional)</label>
                  <input
                    id="test-sku"
                    v-model="testSku"
                    type="text"
                    placeholder="BAGUETE"
                    class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                  >
                </div>
                <div>
                  <label for="test-name" class="mb-1 block text-xs font-medium">Nome (opcional)</label>
                  <input
                    id="test-name"
                    v-model="testName"
                    type="text"
                    placeholder="Pablo"
                    class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                  >
                </div>
              </div>
              <button
                type="button"
                :disabled="!testRecipient.trim() || waTemplate.testing.value"
                class="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground transition disabled:opacity-40"
                @click="onSendTest"
              >
                <Icon
                  :name="waTemplate.testing.value ? 'lucide:loader-circle' : 'lucide:send'"
                  class="size-4"
                  :class="waTemplate.testing.value ? 'animate-spin' : ''"
                />
                {{ waTemplate.testing.value ? "Enviando…" : "Enviar teste" }}
              </button>
            </div>

            <!-- O que o template REALMENTE recebeu: campo vazio aqui explica variável
                 vazia no aparelho, sem o gestor adivinhar. -->
            <dl
              v-if="Object.keys(waTemplate.testFields.value).length"
              class="mt-3 space-y-1 rounded-lg bg-muted/40 p-3 text-xs"
            >
              <div
                v-for="(value, key) in waTemplate.testFields.value"
                :key="key"
                class="flex gap-2"
              >
                <dt class="shrink-0 font-mono text-muted-foreground">{{ key }}</dt>
                <dd class="min-w-0 flex-1 truncate">
                  {{ value || "— vazio, o template renderiza sem" }}
                </dd>
              </div>
            </dl>
          </div>
        </section>
      </li>
    </ul>
  </main>
</template>
