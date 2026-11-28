// Versão do serviço → a linha discreta no detalhe "Capacidade do serviço" do rail.
// Puro, sem Vue.
//
// A versão é o Release ID da imagem que está no ar (`/health/release`, contrato em
// docs/reference/release-contract.md): `AAAAMMDD-HHMM-<commit curto>`. É o que o
// suporte pede ao operador para saber qual build ele está usando. Sem identidade
// (build local, imagem antiga) a linha não aparece: escrever "versão desconhecida"
// para o operador seria nota de rodapé do engenheiro, e quem cobra a ausência é a
// sonda do Watchman.

export interface ReleaseIdentityResponse {
  release_id?: unknown;
}

const RELEASE_ID = /^\d{8}-\d{4}-[0-9a-f]{7}$/;

export function releaseLabel(identity: ReleaseIdentityResponse | null | undefined): string {
  const id = typeof identity?.release_id === "string" ? identity.release_id.trim() : "";
  return RELEASE_ID.test(id) ? `Versão do serviço: ${id}` : "";
}
