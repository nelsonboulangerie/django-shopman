import type {
  MarketingTestReceipt,
  WhatsAppTemplateResponse,
} from "~/types/campaign";

type CommandReceiptResponse = {
  ok: true;
  replayed: boolean;
  receipt: { ref: string; resulting_version: number };
};

type ConfirmationChallenge = {
  code: "confirmation_required";
  confirmation: {
    token: string;
    step_up: "none" | "password" | "totp";
    typed_phrase: string;
  };
};

type Fetcher = typeof $fetch;

/** Execute the exact server-issued consequence with one key across both attempts. */
export async function configureFlowCommand(
  fetcher: Fetcher,
  options: {
    flowNs: string;
    baseVersion: number;
    totp: string;
    idempotencyKey: string;
  },
): Promise<CommandReceiptResponse> {
  const headers = { "Idempotency-Key": options.idempotencyKey };
  const body = {
    flow_ns: options.flowNs,
    base_version: options.baseVersion,
  };
  try {
    return await fetcher<CommandReceiptResponse>(
      "/api/v1/backstage/marketing/whatsapp-template/",
      { method: "POST", headers, body },
    );
  } catch (error) {
    const challenge = errorPayload(error) as Partial<ConfirmationChallenge>;
    if (
      challenge.code !== "confirmation_required" ||
      !challenge.confirmation?.token
    ) {
      throw error;
    }
    if (challenge.confirmation.step_up !== "totp") {
      throw new Error("unexpected_platform_confirmation", { cause: error });
    }
    await fetcher("/api/v1/backstage/marketing/security/step-up/", {
      method: "POST",
      body: { method: "totp", credential: options.totp },
    });
    return await fetcher<CommandReceiptResponse>(
      "/api/v1/backstage/marketing/whatsapp-template/",
      {
        method: "POST",
        headers,
        body: {
          ...body,
          confirmation_token: challenge.confirmation.token,
          typed_confirmation: challenge.confirmation.typed_phrase,
        },
      },
    );
  }
}

function errorPayload(error: unknown): unknown {
  if (typeof error !== "object" || error === null || !("data" in error)) {
    return {};
  }
  return (error as { data?: unknown }).data ?? {};
}

export function useWhatsAppTemplate() {
  const { data, refresh, pending } = useFetch<WhatsAppTemplateResponse>(
    "/api/v1/backstage/marketing/whatsapp-template/",
    {
      key: "marketing-wa-template",
      server: false,
      immediate: false,
      onResponseError: operatorSessionOnError,
    },
  );

  const current = computed(() => data.value?.current ?? "");
  const currentName = computed(() => data.value?.current_name ?? "");
  const version = computed(() => data.value?.version ?? 1);
  const available = computed(() => data.value?.available ?? []);
  const testTargets = computed(() => data.value?.test_targets ?? []);
  const canSendTest = computed(() => data.value?.can_send_test ?? false);
  const canList = computed(() => data.value?.can_list ?? false);
  const commandAvailable = computed(
    () => data.value?.command_available ?? false,
  );
  const catalogState = computed(
    () => data.value?.catalog_state ?? "unavailable",
  );
  const catalogCheckedAt = computed(() => data.value?.catalog_checked_at ?? "");
  const catalogAsOf = computed(() => data.value?.catalog_as_of ?? null);
  const lastCommandCode = ref("");

  async function verify(): Promise<boolean> {
    try {
      data.value = await $fetch<WhatsAppTemplateResponse>(
        "/api/v1/backstage/marketing/whatsapp-template/?refresh=1",
      );
      return true;
    } catch (error) {
      flagMarketingSessionError(error);
      useSonner.error(
        httpErrorMessage(error, "Não foi possível atualizar a verificação."),
      );
      return false;
    }
  }

  async function choose(
    flowNs: string,
    totp: string,
    idempotencyKey: string,
  ): Promise<boolean> {
    lastCommandCode.value = "";
    try {
      await configureFlowCommand($fetch, {
        flowNs,
        baseVersion: version.value,
        totp,
        idempotencyKey,
      });
      useSonner.success(
        flowNs
          ? "Flow escolhido e auditado. O alcance ampliado está pronto para nova verificação."
          : "Flow removido e auditado. O WhatsApp fica limitado à janela de 24 horas.",
      );
      await verify();
      return true;
    } catch (error) {
      flagMarketingSessionError(error);
      const code = String(
        (errorPayload(error) as { code?: string }).code ?? "",
      );
      lastCommandCode.value = code;
      if (code === "version_conflict") await verify();
      useSonner.error(
        httpErrorMessage(error, "Não foi possível alterar o flow."),
      );
      return false;
    }
  }

  const testFields = ref<Record<string, string>>({});
  const testReceipt = ref<MarketingTestReceipt | null>(null);
  const testing = ref(false);

  async function sendTest(
    targetRef: string,
    options: { sku?: string; body?: string } = {},
  ) {
    testing.value = true;
    try {
      const response = await $fetch<MarketingTestReceipt>(
        "/api/v1/backstage/marketing/whatsapp-template/test/",
        {
          method: "POST",
          headers: { "Idempotency-Key": crypto.randomUUID() },
          body: {
            target_ref: targetRef,
            sku: options.sku || "",
            body: options.body || "",
          },
        },
      );
      testFields.value = response.fields || {};
      testReceipt.value = response;
      if (response.ok) {
        useSonner.success(
          "Sandbox aceitou. Confira o aparelho; aceite ainda não é entrega.",
        );
      } else {
        useSonner.error(
          "O sandbox não confirmou aceite. O receipt ficou guardado.",
        );
      }
      return response.ok;
    } catch (error) {
      flagMarketingSessionError(error);
      useSonner.error(
        httpErrorMessage(error, "Não foi possível enviar o teste."),
      );
      return false;
    } finally {
      testing.value = false;
    }
  }

  return {
    current,
    currentName,
    version,
    available,
    testTargets,
    canSendTest,
    canList,
    commandAvailable,
    catalogState,
    catalogCheckedAt,
    catalogAsOf,
    lastCommandCode,
    loading: pending,
    load: refresh,
    verify,
    choose,
    sendTest,
    testing,
    testFields,
    testReceipt,
  };
}
