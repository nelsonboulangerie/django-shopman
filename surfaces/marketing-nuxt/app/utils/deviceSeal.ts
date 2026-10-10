// A digital do dispositivo no selo do Marketing (SUITE-UX §15, prévia v4 pino 8).
//
// Tradução pura entre o JSON do servidor (base64url) e o `navigator.credentials`
// (ArrayBuffer), sem rede. A rede mora em `useDeviceSeal`. Mesma conversão do
// `usePasskey` da loja; os dois mundos não compartilham credencial (a do operador é do
// usuário do Django, a da loja é do cliente).

export type WebAuthnServerOptions = Record<string, unknown> & {
  challenge: string;
  user?: { id: string; name: string; displayName: string };
  excludeCredentials?: { id: string; type: string; transports?: string[] }[];
  allowCredentials?: { id: string; type: string; transports?: string[] }[];
};

export function fromB64url(value: string): Uint8Array {
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

export function toB64url(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** As opções do servidor com os campos binários convertidos. */
export function nativeOptions(options: WebAuthnServerOptions): Record<string, unknown> {
  const native: Record<string, unknown> = { ...options, challenge: fromB64url(options.challenge) };
  if (options.user) native.user = { ...options.user, id: fromB64url(options.user.id) };
  for (const key of ["excludeCredentials", "allowCredentials"] as const) {
    const list = options[key];
    if (list?.length) native[key] = list.map((credential) => ({ ...credential, id: fromB64url(credential.id) }));
  }
  return native;
}

/** A credencial criada ou assinada, no JSON que o servidor lê. */
export function credentialJson(credential: PublicKeyCredential): Record<string, unknown> {
  const response = credential.response as AuthenticatorAttestationResponse & AuthenticatorAssertionResponse;
  const inner: Record<string, unknown> = { clientDataJSON: toB64url(response.clientDataJSON) };
  if (response.attestationObject) inner.attestationObject = toB64url(response.attestationObject);
  if (response.authenticatorData) inner.authenticatorData = toB64url(response.authenticatorData);
  if (response.signature) inner.signature = toB64url(response.signature);
  if (response.userHandle) inner.userHandle = toB64url(response.userHandle);
  return { id: credential.id, rawId: toB64url(credential.rawId), type: credential.type, response: inner };
}

/** O nome que a pessoa reconhece na lista ("Celular Android", "iPhone"). */
export function deviceLabel(userAgent: string): string {
  if (/iphone/i.test(userAgent)) return "iPhone";
  if (/ipad/i.test(userAgent)) return "iPad";
  if (/android/i.test(userAgent)) return "Celular Android";
  if (/mac/i.test(userAgent)) return "Mac";
  if (/windows/i.test(userAgent)) return "Windows";
  return /mobi|phone/i.test(userAgent) ? "Celular" : "Computador";
}

/** O navegador tem a API e um autenticador do próprio dispositivo que reconhece a pessoa? */
export async function deviceSealSupported(): Promise<boolean> {
  if (typeof window === "undefined" || typeof window.PublicKeyCredential !== "function") return false;
  const api = window.PublicKeyCredential as unknown as {
    isUserVerifyingPlatformAuthenticatorAvailable?: () => Promise<boolean>;
  };
  if (typeof api.isUserVerifyingPlatformAuthenticatorAvailable !== "function") return false;
  try {
    return await api.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}
