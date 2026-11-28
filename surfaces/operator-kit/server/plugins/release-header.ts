// Toda resposta do BFF de operador diz qual release a serviu (`X-Shopman-Release`),
// para o suporte identificar o artefato pela aba de rede do navegador, sem abrir o
// painel da nuvem (WP-RELEASE-01 R1). Lido uma vez: o valor vem da imagem e não
// muda enquanto o processo vive. Build sem identidade não carimba nada.
import { setResponseHeader } from "h3";
import { readReleaseIdentity, RELEASE_HEADER } from "../utils/releaseIdentity";

export default defineNitroPlugin((nitroApp) => {
  const releaseId = readReleaseIdentity(process.env, "").release_id;
  if (!releaseId) return;
  nitroApp.hooks.hook("request", (event) => {
    setResponseHeader(event, RELEASE_HEADER, releaseId);
  });
});
