import { defineEventHandler } from "h3";
import {
  applyOperatorBaselineSecurityHeaders,
  type OperatorCspAllow,
} from "../utils/operatorSecurity";

// Instalado pelo layer e ativado por app para permitir migração serializada da CSP.
// Mantém documentos e APIs same-origin privados; assets compilados preservam cache.
// `operatorCspAllow` é a exceção declarada pelo app, por diretiva (ver operatorSecurity).
export default defineEventHandler((event) => {
  const config = useRuntimeConfig(event);
  if (config.operatorSecurityHeaders !== true) return;
  applyOperatorBaselineSecurityHeaders(event, config.operatorCspAllow as OperatorCspAllow | undefined);
});
