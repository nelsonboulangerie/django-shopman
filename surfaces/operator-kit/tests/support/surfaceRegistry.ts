import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

// Leitura do registro único das superfícies (`surfaces/registry.json`) para as
// varreduras do kit. Cada teste tinha a própria cópia da lista dos apps de
// operador, e superfície nova só entrava na varredura se alguém lembrasse de
// editar nove arquivos. Agora ela entra ao nascer no registro.

interface RegisteredSurface {
  dir: string;
  kind: "customer" | "operator";
}

const registryPath = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "registry.json");
const registry = JSON.parse(readFileSync(registryPath, "utf8")) as { surfaces: Record<string, RegisteredSurface> };

/** Diretórios dos apps de operador (`pos-nuxt`, …), em ordem alfabética. */
export const OPERATOR_SURFACES: readonly string[] = Object.values(registry.surfaces)
  .filter((surface) => surface.kind === "operator")
  .map((surface) => surface.dir)
  .sort();
