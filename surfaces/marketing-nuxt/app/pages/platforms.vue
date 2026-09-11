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
import { receiptStateLabel } from "~/presentation/marketingResult";

const {
  platforms,
  loading,
  error,
  load: loadPlatforms,
} = usePlatforms();
const waTemplate = useWhatsAppTemplate();

// ⚠️ O detalhe abre em painel, não fica aberto na página. Com o WhatsApp expandido o tempo
// todo a lista já ficava estranha; com as quatro plataformas expandindo, a tela viraria um
// depósito. A lista responde "como está cada uma?" num relance; o painel responde "e o que
// eu faço?".
const opened = ref<Platform | null>(null);
const savingTemplate = ref(false);
const pendingFlow = ref<string | null>(null);
const platformCommandKey = ref("");
const totp = ref("");
const testTargetRef = ref("");
const testSku = ref("");

onMounted(async () => {
  await waTemplate.load();
  if (waTemplate.testTargets.value.length === 1) {
    testTargetRef.value = waTemplate.testTargets.value[0]?.ref || "";
  }
});

function onChooseTemplate(flowNs: string) {
  if (!waTemplate.commandAvailable.value || flowNs === waTemplate.current.value)
    return;
  pendingFlow.value = flowNs;
  platformCommandKey.value = crypto.randomUUID();
  totp.value = "";
}

async function onConfirmTemplate() {
  if (pendingFlow.value === null || totp.value.length !== 6) return;
  savingTemplate.value = true;
  const changed = await waTemplate.choose(
    pendingFlow.value,
    totp.value,
    platformCommandKey.value,
  );
  if (changed) {
    pendingFlow.value = null;
    platformCommandKey.value = "";
    totp.value = "";
    await loadPlatforms();
    opened.value =
      platforms.value.find((item) => item.platform === "whatsapp") ??
      opened.value;
  } else if (waTemplate.lastCommandCode.value === "version_conflict") {
    // Keep the exact selected flow in view, but start a new command against the
    // freshly loaded version.  Reusing a key whose receipt is a conflict would
    // replay that conflict forever.
    platformCommandKey.value = crypto.randomUUID();
    totp.value = "";
  }
  savingTemplate.value = false;
}

async function onVerifyCatalog() {
  await waTemplate.verify();
  await loadPlatforms();
  opened.value =
    platforms.value.find((item) => item.platform === "whatsapp") ??
    opened.value;
}

async function onSendTest() {
  if (!testTargetRef.value) return;
  await waTemplate.sendTest(testTargetRef.value, {
    sku: testSku.value.trim(),
  });
}

/** Uma linha por plataforma: o resumo que responde "como está" sem abrir nada. */
function summaryFor(platform: Platform): string {
  if (platform.state === "unknown") return platform.reason;
  if (platform.state === "blocked") return platform.reason;
  if (platform.limitation) return platform.limitation;
  return kindLabel(platform.kind);
}

/** O que "entregar" quer dizer nesta plataforma — publicar e mandar mensagem não são o mesmo. */
function kindLabel(kind: string): string {
  return kind === "direct_message"
    ? "Uma mensagem por pessoa, com consentimento."
    : "Uma publicação pública na plataforma; não envia mensagem direta.";
}

/** Bloqueio, limitação e saúde não podem parecer iguais. */
function tone(platform: Pick<Platform, "state" | "source_status">) {
  if (platform.source_status === "simulated")
    return {
      chip: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
      icon: "lucide:flask-conical",
      label: "Simulação local",
    };
  if (platform.state === "blocked")
    return {
      chip: "bg-destructive/10 text-destructive",
      icon: "lucide:circle-slash",
      label: "Não publica",
    };
  if (platform.state === "unknown")
    return {
      chip: "bg-slate-500/10 text-slate-700 dark:text-slate-300",
      icon: "lucide:circle-help",
      label: "Não verificada",
    };
  if (platform.state === "degraded")
    return {
      chip: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
      icon: "lucide:triangle-alert",
      label: "Alcance limitado",
    };
  return {
    chip: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
    icon: "lucide:check",
    label: "Pronta",
  };
}

function checkedAt(value: string): string {
  if (!value) return "sem verificação registrada";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

const pendingFlowName = computed(() => {
  if (pendingFlow.value === "") return "Sem fluxo (janela de 24 horas)";
  return (
    waTemplate.available.value.find((item) => item.ns === pendingFlow.value)
      ?.name ?? "Fluxo selecionado"
  );
});

useHead({ title: "Plataformas · Marketing" });
</script>

<template>
  <main class="mx-auto w-full max-w-3xl flex-1 px-4 py-6">
    <h1 class="mb-1 text-xl font-semibold">Plataformas</h1>
    <p class="mb-4 text-sm text-muted-foreground">
      Por onde o anúncio sai. Quem vende é o canal; aqui é quem fala.
    </p>

    <div
      v-if="error && !platforms.length"
      class="rounded-xl border border-destructive/40 bg-destructive/5 px-4 py-5"
      role="alert"
    >
      <div class="flex items-start gap-3">
        <Icon
          name="lucide:cloud-off"
          class="mt-0.5 size-5 shrink-0 text-destructive"
        />
        <div>
          <p class="font-semibold">Não foi possível verificar as plataformas</p>
          <p class="mt-1 text-sm text-muted-foreground">
            Isso é uma indisponibilidade de leitura, não significa que nenhuma
            plataforma esteja configurada. Nenhuma configuração foi alterada.
          </p>
          <button
            type="button"
            class="mt-3 min-h-11 rounded-md border border-border bg-background px-4 text-sm font-semibold hover:bg-muted"
            :disabled="loading"
            @click="loadPlatforms()"
          >
            {{ loading ? "Verificando…" : "Verificar novamente" }}
          </button>
        </div>
      </div>
    </div>

    <div v-else-if="loading && !platforms.length" class="space-y-2" aria-busy="true">
      <div
        v-for="n in 4"
        :key="n"
        class="h-24 animate-pulse rounded-xl bg-muted"
      ></div>
    </div>

    <div
      v-else-if="!platforms.length"
      class="rounded-xl border border-dashed border-border bg-card/50 px-6 py-10 text-center"
    >
      <Icon
        name="lucide:share-2"
        class="mx-auto size-8 text-muted-foreground"
      />
      <p class="mt-2 font-semibold">Nenhuma plataforma disponível</p>
      <p class="mt-1 text-sm text-muted-foreground">
        A verificação respondeu sem opções. Atualize antes de preparar uma
        publicação.
      </p>
      <button
        type="button"
        class="mt-3 min-h-11 font-semibold underline underline-offset-2"
        @click="loadPlatforms()"
      >
        Atualizar verificação
      </button>
    </div>

    <ul
      v-else
      class="divide-y divide-border rounded-xl border border-border bg-card"
    >
      <li v-for="platform in platforms" :key="platform.platform">
        <button
          type="button"
          class="flex w-full items-center gap-3 px-4 py-3 text-left transition hover:bg-muted"
          @click="opened = platform"
        >
          <Icon
            :name="platformIcon(platform.platform)"
            class="size-5 shrink-0 text-muted-foreground"
          />
          <span class="min-w-0 flex-1">
            <span class="flex flex-wrap items-center gap-2">
              <span class="font-semibold">{{ platform.label }}</span>
              <span
                class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
                :class="tone(platform).chip"
              >
                <Icon :name="tone(platform).icon" class="size-3" />
                {{ tone(platform).label }}
              </span>
              <!-- Plataforma que nenhuma campanha ativa usa não é problema: ligar
                   credencial de algo sem uso é trabalho jogado fora. -->
              <span
                v-if="!platform.in_use"
                class="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
              >
                Sem uso
              </span>
            </span>
            <span class="mt-0.5 block truncate text-sm text-muted-foreground">
              {{ summaryFor(platform) }}
            </span>
          </span>
          <Icon
            name="lucide:chevron-right"
            class="size-4 shrink-0 text-muted-foreground"
          />
        </button>
      </li>
    </ul>

    <UiSheet
      :open="opened !== null"
      @update:open="
        (v) => {
          if (!v) opened = null;
        }
      "
    >
      <UiSheetContent side="right" class="w-full gap-0 p-0 sm:max-w-lg">
        <UiSheetHeader class="border-b border-border">
          <UiSheetTitle>{{ opened?.label }}</UiSheetTitle>
          <UiSheetDescription>{{
            opened ? kindLabel(opened.kind) : ""
          }}</UiSheetDescription>
        </UiSheetHeader>

        <div v-if="opened" class="flex-1 overflow-y-auto p-4">
          <div
            class="flex items-start gap-2 rounded-lg px-3 py-2.5 text-sm"
            :class="tone(opened).chip"
          >
            <Icon :name="tone(opened).icon" class="mt-0.5 size-4 shrink-0" />
            <div class="min-w-0">
              <p class="font-semibold">
                {{ tone(opened).label }}
              </p>
              <p class="mt-0.5">
                {{
                  opened.reason || opened.limitation || "Nada impede a entrega."
                }}
              </p>
            </div>
          </div>

          <p v-if="opened.action" class="mt-3 text-sm">
            <span class="font-medium">O que fazer:</span> {{ opened.action }}
          </p>
          <p class="mt-2 text-xs text-muted-foreground">
            Verificado em {{ checkedAt(opened.checked_at) }}.
          </p>

          <!-- Só o WhatsApp se resolve DAQUI. As outras dependem de credencial de
               plataforma, que não se digita numa tela de operação. -->
          <template v-if="opened.platform === 'whatsapp'">
            <section class="mt-5 border-t border-border pt-4">
              <h2 class="text-sm font-semibold">Modelo aprovado</h2>
              <p class="mt-0.5 text-xs text-muted-foreground">
                Com um modelo aprovado, o anúncio alcança quem não conversou nas
                últimas 24 horas. Sem ele, só a janela.
              </p>

              <div
                v-if="waTemplate.loading.value"
                class="mt-3 space-y-2"
                aria-busy="true"
              >
                <div
                  v-for="n in 2"
                  :key="n"
                  class="h-10 animate-pulse rounded-md bg-muted"
                ></div>
              </div>

              <!-- Não conseguir perguntar à plataforma NÃO é "não há modelo". -->
              <div
                v-else-if="!waTemplate.canList.value"
                class="mt-3 rounded-lg border border-border bg-muted/40 px-3 py-2.5 text-sm"
              >
                <p class="font-semibold">
                  Não foi possível consultar os modelos agora
                </p>
                <p class="mt-1 text-muted-foreground">
                  A última lista conhecida não autoriza mudança. Nada foi
                  alterado; atualize a verificação antes de escolher.
                </p>
                <p
                  v-if="waTemplate.catalogAsOf.value"
                  class="mt-1 text-xs text-muted-foreground"
                >
                  Última resposta válida:
                  {{ checkedAt(waTemplate.catalogAsOf.value) }}.
                </p>
                <button
                  type="button"
                  class="mt-3 inline-flex min-h-11 items-center justify-center gap-2 rounded-md border border-border bg-background px-3 text-sm font-semibold"
                  @click="onVerifyCatalog"
                >
                  <Icon name="lucide:refresh-cw" class="size-4" />
                  Verificar novamente
                </button>
              </div>

              <div v-else class="mt-3 space-y-1.5">
                <button
                  type="button"
                  class="flex w-full items-start gap-2 rounded-lg border px-3 py-2.5 text-left transition hover:bg-muted"
                  :class="
                    waTemplate.current.value === ''
                      ? 'border-primary'
                      : 'border-border'
                  "
                  :disabled="
                    savingTemplate ||
                    !waTemplate.commandAvailable.value ||
                    waTemplate.current.value === ''
                  "
                  @click="onChooseTemplate('')"
                >
                  <Icon
                    name="lucide:circle-slash"
                    class="mt-0.5 size-4 shrink-0 text-muted-foreground"
                  />
                  <span>
                    <span class="block text-sm font-medium">Sem modelo</span>
                    <span class="block text-xs text-muted-foreground">
                      Texto livre — alcança só quem conversou nas últimas 24
                      horas.
                    </span>
                  </span>
                </button>

                <button
                  v-for="option in waTemplate.available.value"
                  :key="option.ns"
                  type="button"
                  class="flex w-full items-start gap-2 rounded-lg border px-3 py-2.5 text-left transition hover:bg-muted"
                  :class="
                    waTemplate.current.value === option.ns
                      ? 'border-primary'
                      : 'border-border'
                  "
                  :disabled="
                    savingTemplate ||
                    !waTemplate.commandAvailable.value ||
                    waTemplate.current.value === option.ns
                  "
                  @click="onChooseTemplate(option.ns)"
                >
                  <Icon
                    name="lucide:file-check-2"
                    class="mt-0.5 size-4 shrink-0 text-muted-foreground"
                  />
                  <span class="min-w-0">
                    <span class="block truncate text-sm font-medium">{{
                      option.name
                    }}</span>
                  </span>
                </button>
                <p
                  v-if="waTemplate.available.value.length === 0"
                  class="rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
                >
                  A consulta respondeu, mas não há fluxo ativo disponível. “Sem
                  fluxo” continua sendo a configuração segura.
                </p>
              </div>

              <!-- ⚠️ O que mais confunde, dito onde a decisão acontece: com modelo
                   escolhido, o texto que o cliente lê é o DA META, não o do Modelo. -->
              <p
                v-if="waTemplate.current.value"
                class="mt-3 rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground"
              >
                Com o modelo escolhido, o texto que sai no WhatsApp é o aprovado
                na Meta — o modelo entra só com as variáveis. O texto do modelo
                continua valendo para Instagram, Facebook e para a sua revisão.
              </p>
            </section>

            <!-- A ref verificada evita redigitar/errar número e não leva PII ao browser. -->
            <section class="mt-5 border-t border-border pt-4">
              <h2 class="text-sm font-semibold">Teste seguro do WhatsApp</h2>
              <p class="mt-0.5 text-xs text-muted-foreground">
                Envia uma mensagem a um aparelho verificado. Nunca usa público
                de campanha.
              </p>

              <div
                v-if="!waTemplate.canSendTest.value"
                class="mt-3 rounded-lg border border-border bg-muted/40 px-3 py-2.5 text-sm"
              >
                <p class="font-semibold">
                  Teste não disponível para este papel
                </p>
                <p class="mt-1 text-muted-foreground">
                  Um Editor habilitado ou responsável pelas plataformas pode
                  fazer o teste no ambiente seguro.
                </p>
              </div>

              <div
                v-else-if="!waTemplate.testTargets.value.length"
                class="mt-3 rounded-lg border border-border bg-muted/40 px-3 py-2.5 text-sm"
              >
                <p class="font-semibold">
                  Teste externo bloqueado com segurança
                </p>
                <p class="mt-1 text-muted-foreground">
                  Nenhum aparelho de teste verificado foi configurado. Peça ao
                  responsável pelas plataformas; não é necessário copiar ou
                  informar um telefone aqui.
                </p>
              </div>

              <div v-else class="mt-3 space-y-2">
                <div>
                  <label
                    for="test-target"
                    class="mb-1 block text-xs font-medium"
                  >
                    Aparelho verificado
                  </label>
                  <UiNativeSelect
                    id="test-target"
                    v-model="testTargetRef"
                  >
                    <option value="" disabled>Escolha o aparelho</option>
                    <option
                      v-for="target in waTemplate.testTargets.value"
                      :key="target.ref"
                      :value="target.ref"
                    >
                      {{ target.label }}
                    </option>
                  </UiNativeSelect>
                </div>
                <div>
                  <label for="test-sku" class="mb-1 block text-xs font-medium"
                    >SKU (opcional)</label
                  >
                  <input
                    id="test-sku"
                    v-model="testSku"
                    type="text"
                    placeholder="BAGUETE"
                    class="h-9 w-full rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                  />
                </div>
                <button
                  type="button"
                  :disabled="!testTargetRef || waTemplate.testing.value"
                  class="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-md bg-primary px-3 text-sm font-semibold text-primary-foreground transition disabled:opacity-40"
                  @click="onSendTest"
                >
                  <Icon
                    :name="
                      waTemplate.testing.value
                        ? 'lucide:loader-circle'
                        : 'lucide:send'
                    "
                    class="size-4"
                    :class="waTemplate.testing.value ? 'animate-spin' : ''"
                  />
                  {{ waTemplate.testing.value ? "Enviando…" : "Enviar teste" }}
                </button>
              </div>

              <p
                v-if="waTemplate.testReceipt.value"
                class="mt-3 break-all rounded-lg bg-muted/40 p-3 font-mono text-xs"
              >
                Comprovante {{ waTemplate.testReceipt.value.receipt_ref }} ·
                {{ receiptStateLabel(waTemplate.testReceipt.value.state) }}
              </p>

              <dl
                v-if="Object.keys(waTemplate.testFields.value).length"
                class="mt-3 space-y-1 rounded-lg bg-muted/40 p-3 text-xs"
              >
                <div
                  v-for="(value, key) in waTemplate.testFields.value"
                  :key="key"
                  class="flex gap-2"
                >
                  <dt class="shrink-0 font-mono text-muted-foreground">
                    {{ key }}
                  </dt>
                  <dd class="min-w-0 flex-1 truncate">
                    {{ value || "— vazio, o modelo renderiza sem" }}
                  </dd>
                </div>
              </dl>
            </section>
          </template>
        </div>
      </UiSheetContent>
    </UiSheet>

    <UiDialog
      :open="pendingFlow !== null"
      @update:open="
        (value) => {
          if (!value && !savingTemplate) {
            pendingFlow = null;
            platformCommandKey = '';
            totp = '';
          }
        }
      "
    >
      <UiDialogContent class="gap-3 rounded-2xl p-4 sm:max-w-md sm:p-5">
        <UiDialogHeader class="items-center gap-1.5 text-center sm:text-center">
          <div
            class="grid size-10 place-items-center rounded-full bg-primary/10 text-primary"
            aria-hidden="true"
          >
            <Icon name="lucide:shield-check" class="size-5" />
          </div>
          <UiDialogTitle class="text-xl">
            Confirmar configuração do WhatsApp
          </UiDialogTitle>
          <UiDialogDescription class="sr-only">
            Esta escolha muda o alcance dos próximos anúncios e ficará
            registrada na auditoria.
          </UiDialogDescription>
        </UiDialogHeader>

        <div
          class="flex gap-3 rounded-xl border border-sky-500/30 bg-sky-500/5 p-2.5 text-sm"
        >
          <Icon
            name="lucide:shield-check"
            class="mt-0.5 size-5 shrink-0 text-sky-700 dark:text-sky-300"
            aria-hidden="true"
          />
          <div>
            <p class="font-semibold">Nenhuma mensagem será enviada agora</p>
            <p class="mt-0.5 text-muted-foreground">
              Só a configuração dos próximos anúncios será alterada.
            </p>
          </div>
        </div>

        <dl
          class="grid grid-cols-2 overflow-hidden rounded-xl border border-border bg-muted/40 text-center text-sm"
        >
          <div class="border-r border-border p-3">
            <dt class="text-xs text-muted-foreground">Configuração atual</dt>
            <dd class="mt-1 font-medium">
              {{
                waTemplate.currentName.value ||
                (waTemplate.current.value
                  ? "Fluxo configurado, mas não ativo na lista atual"
                  : "Sem fluxo (janela de 24 horas)")
              }}
            </dd>
          </div>
          <div class="p-3">
            <dt class="text-xs text-muted-foreground">Depois da confirmação</dt>
            <dd class="mt-1 font-medium">{{ pendingFlowName }}</dd>
          </div>
          <div class="col-span-2 border-t border-border p-3">
            <dt class="text-xs text-muted-foreground">Versão revisada</dt>
            <dd class="mt-1 font-semibold tabular-nums">
              {{ waTemplate.version.value }}
            </dd>
          </div>
        </dl>

        <UiVerificationCodeInput
          id="platform-totp"
          v-model="totp"
          :disabled="savingTemplate"
          class="text-center"
          help="Use o código atual do autenticador cadastrado."
        />

        <UiDialogFooter class="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <button
            type="button"
            class="inline-flex min-h-11 w-full items-center justify-center rounded-md border border-border px-4 text-sm font-semibold"
            :disabled="savingTemplate"
            @click="pendingFlow = null"
          >
            Voltar sem alterar
          </button>
          <button
            type="button"
            class="inline-flex min-h-11 w-full items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-semibold text-primary-foreground disabled:opacity-40"
            :disabled="savingTemplate || totp.length !== 6"
            @click="onConfirmTemplate"
          >
            <Icon
              :name="
                savingTemplate ? 'lucide:loader-circle' : 'lucide:shield-check'
              "
              class="size-4"
              :class="savingTemplate ? 'animate-spin' : ''"
            />
            {{ savingTemplate ? "Salvando…" : "Salvar configuração" }}
          </button>
        </UiDialogFooter>
      </UiDialogContent>
    </UiDialog>
  </main>
</template>
