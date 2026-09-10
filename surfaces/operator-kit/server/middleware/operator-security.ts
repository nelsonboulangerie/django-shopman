import { defineEventHandler } from "h3";
import { applyOperatorBaselineSecurityHeaders } from "../utils/operatorSecurity";

// Instalado pelo layer e ativado por app para permitir migração serializada da CSP.
// Mantém documentos e APIs same-origin privados; assets compilados preservam cache.
export default defineEventHandler((event) => {
  const config = useRuntimeConfig(event);
  if (config.operatorSecurityHeaders === true) applyOperatorBaselineSecurityHeaders(event);
});
