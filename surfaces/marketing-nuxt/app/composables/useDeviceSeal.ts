// A digital do dispositivo no selo: cadastrar uma vez, e depois assinar a confirmação
// exata que o selo mostra (o servidor prende o desafio à `ref` dela). Cancelar a
// digital não é erro: a pessoa usa o código (a frase ou a senha) no mesmo selo.
import {
  credentialJson,
  deviceLabel,
  deviceSealSupported,
  nativeOptions,
  type WebAuthnServerOptions,
} from "~/utils/deviceSeal";

export type DeviceSealOutcome = "sealed" | "cancelled" | "needs_registration";

export function useDeviceSeal() {
  const supported = ref(false);
  const busy = ref(false);
  const error = ref("");

  onMounted(async () => {
    supported.value = await deviceSealSupported();
  });

  function cancelled(exc: unknown): boolean {
    return (exc as DOMException)?.name === "NotAllowedError" || (exc as DOMException)?.name === "AbortError";
  }

  /** Cadastrar a digital deste dispositivo. `true` quando ficou cadastrada. */
  async function register(): Promise<boolean> {
    busy.value = true;
    error.value = "";
    try {
      const { options } = await $fetch<{ options: WebAuthnServerOptions }>(
        "/api/v1/backstage/marketing/security/device/register/options/",
        { method: "POST", credentials: "same-origin" },
      );
      const created = (await navigator.credentials.create({
        publicKey: nativeOptions(options) as unknown as PublicKeyCredentialCreationOptions,
      })) as PublicKeyCredential | null;
      if (!created) return false;
      await $fetch("/api/v1/backstage/marketing/security/device/register/", {
        method: "POST",
        credentials: "same-origin",
        body: { credential: credentialJson(created), label: deviceLabel(navigator.userAgent) },
      });
      return true;
    } catch (exc) {
      if (cancelled(exc)) return false;
      flagMarketingSessionError(exc);
      error.value = httpErrorMessage(exc, "Não deu para cadastrar a digital deste dispositivo. Use o seu código.");
      return false;
    } finally {
      busy.value = false;
    }
  }

  /**
   * Assinar com a digital. `confirmationToken` (quem pediu) ou `confirmationRef` (a
   * segunda pessoa, que chegou pelo push). Depois disto o servidor tem a digital
   * registrada para ESTA confirmação, e só para ela.
   */
  async function seal(target: { confirmationToken?: string; confirmationRef?: string }): Promise<DeviceSealOutcome> {
    busy.value = true;
    error.value = "";
    try {
      const { options } = await $fetch<{ options: WebAuthnServerOptions }>(
        "/api/v1/backstage/marketing/security/device/options/",
        {
          method: "POST",
          credentials: "same-origin",
          body: target.confirmationToken
            ? { confirmation_token: target.confirmationToken }
            : { confirmation_ref: target.confirmationRef },
        },
      );
      const signed = (await navigator.credentials.get({
        publicKey: nativeOptions(options) as unknown as PublicKeyCredentialRequestOptions,
      })) as PublicKeyCredential | null;
      if (!signed) return "cancelled";
      await $fetch("/api/v1/backstage/marketing/security/device/", {
        method: "POST",
        credentials: "same-origin",
        body: { credential: credentialJson(signed) },
      });
      return "sealed";
    } catch (exc) {
      if (cancelled(exc)) return "cancelled";
      const data = (exc as { data?: { code?: string } })?.data;
      if (data?.code === "no_device_passkey") return "needs_registration";
      flagMarketingSessionError(exc);
      error.value = httpErrorMessage(exc, "A digital não conferiu. Use o seu código.");
      return "cancelled";
    } finally {
      busy.value = false;
    }
  }

  return { supported, busy, error, register, seal };
}
