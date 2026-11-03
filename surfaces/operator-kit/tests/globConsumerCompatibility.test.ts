import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

// Os overrides de segurança atravessam faixas antigas. Exercitar os consumidores
// reais evita tratar a presença da API exportada como prova de compatibilidade.
const load = createRequire(import.meta.url);
let fixture: string;

beforeEach(() => {
  fixture = mkdtempSync(join(tmpdir(), "shopman-glob-compat-"));
  mkdirSync(join(fixture, "nested"));
  for (const name of ["bread.txt", "cake.md", ".hidden.txt", "nested/bread.txt"]) {
    writeFileSync(join(fixture, name), "fixture");
  }
});
afterEach(() => rmSync(fixture, { recursive: true, force: true }));

describe("contratos dos consumidores de glob e minimatch", () => {
  it("preserva glob.sync e exclusões do archiver-utils", () => {
    const { file } = load("archiver-utils");
    expect(file.expand({ cwd: fixture, filter: "isFile" }, ["**/*.txt", "!nested/**"]))
      .toEqual(["bread.txt"]);
  });

  it("preserva inclusão e exclusão do FileList com minimatch.match", () => {
    const { FileList } = load("filelist");
    const files = new FileList();
    files.include(join(fixture, "**/*.txt"));
    files.exclude(join(fixture, "nested/**"));
    expect(files.toArray()).toEqual([join(fixture, "bread.txt")]);
  });

  it("preserva o filtro assíncrono do readdir-glob com Minimatch", async () => {
    const readdirGlob = load("readdir-glob");
    const matches = await new Promise<string[]>((resolve, reject) => {
      const paths: string[] = [];
      readdirGlob(fixture, { pattern: "**/*.txt", ignore: "nested/**" })
        .on("match", (entry: { relative: string }) => paths.push(entry.relative))
        .on("error", reject)
        .on("end", () => resolve(paths.sort()));
    });
    expect(matches).toEqual(["bread.txt"]);
  });
});
