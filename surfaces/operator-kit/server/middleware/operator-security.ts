import { defineEventHandler } from "h3";
import {
  applyOperatorBaselineSecurityHeaders,
  type OperatorCspAllow,
  type OperatorPermissionsAllow,
} from "../utils/operatorSecurity";

// Instalado pelo layer e ativado por app para permitir migração serializada da CSP.
// Mantém documentos e APIs same-origin privados; assets compilados preservam cache.
// `operatorCspAllow` e `operatorPermissionsAllow` são as exceções declaradas pelo app,
// por diretiva e por recurso (ver operatorSecurity).
export default defineEventHandler((event) => {
  const config = useRuntimeConfig(event);
  if (config.operatorSecurityHeaders !== true) return;
  const cspAllow = config.operatorCspAllow as OperatorCspAllow | undefined;
  const permissionsAllow = config.operatorPermissionsAllow as OperatorPermissionsAllow | undefined;
  applyOperatorBaselineSecurityHeaders(event, cspAllow, permissionsAllow);
});
