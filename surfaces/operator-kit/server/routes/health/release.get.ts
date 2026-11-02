// GET /health/release — qual build este app está servindo (WP-RELEASE-01 R1).
// Na layer: os oito apps de operador respondem na mesma URL. Separado de
// /health/live e /health/ready: não é sonda de plataforma, é diagnóstico para o
// suporte, para a tela ("Versão" no detalhe do serviço) e para a sonda do Watchman
// que confere o commit do `main` contra o vivo.
import { defineEventHandler } from "h3";
import { readReleaseIdentity, respondReleaseIdentity } from "../../utils/releaseIdentity";

export default defineEventHandler((event) => {
  const app = (useRuntimeConfig(event).public?.operatorPwa as { app?: string } | undefined)?.app ?? "";
  return respondReleaseIdentity(event, readReleaseIdentity(process.env, app));
});
