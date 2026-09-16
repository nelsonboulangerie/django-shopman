import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

// A decisão de cadastro pertence à validação do pedido, não à digitação.
const appDir = resolve(dirname(fileURLToPath(import.meta.url)), "..", "app");

function sourceFiles(dir: string, found: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".nuxt" || entry === ".output") continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) sourceFiles(full, found);
    else if (full.endsWith(".vue")) found.push(full);
  }
  return found;
}

describe("decisão única do documento", () => {
  it("não reintroduz ofertas inline nos campos do documento", () => {
    const mounts = sourceFiles(appDir).filter(file => readFileSync(file, "utf8").includes("<PosReceiptSaveOffer"));
    expect(mounts.map(file => file.slice(appDir.length + 1))).toEqual([]);
  });
});
