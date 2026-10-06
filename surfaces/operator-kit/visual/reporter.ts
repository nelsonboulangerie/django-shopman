import { copyFileSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";

import type { FullConfig, Reporter, TestCase, TestResult } from "@playwright/test/reporter";
import sharp from "sharp";

interface EvidenceRecord {
  app: string;
  surface: string;
  route: string;
  scenario: string;
  state: string;
  theme: string;
  viewport: { id: string; label: string; width: number; height: number };
  findings: unknown[];
  status: string;
  path: string;
  test: string;
}

function safe(value: string): string {
  return value.replace(/[^a-zA-Z0-9._-]+/g, "-").replace(/^-|-$/g, "") || "item";
}

function xml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" })[char]!);
}

export default class OperatorVisualReporter implements Reporter {
  private root = "";
  private records: EvidenceRecord[] = [];

  onBegin(config: FullConfig) {
    this.root = process.env.OPERATOR_VISUAL_EVIDENCE_ROOT || join(dirname(config.configFile), "test-results", "operator-evidence");
    rmSync(this.root, { recursive: true, force: true });
    mkdirSync(this.root, { recursive: true });
  }

  onTestEnd(test: TestCase, result: TestResult) {
    const annotation = test.annotations.find((item) => item.type === "operator-evidence")?.description;
    const attachment = result.attachments.find((item) => item.name.startsWith("operator-evidence:") && item.path);
    if (!annotation || !attachment?.path || !existsSync(attachment.path)) return;
    const identity = JSON.parse(annotation) as Omit<EvidenceRecord, "status" | "path" | "test" | "theme"> & { theme?: string };
    const destination = join(
      this.root,
      safe(identity.app),
      safe(identity.surface),
      safe(identity.scenario),
      safe(identity.state),
      safe(identity.viewport.id),
      `${safe(identity.theme ?? "light")}.png`,
    );
    mkdirSync(dirname(destination), { recursive: true });
    copyFileSync(attachment.path, destination);
    this.records.push({
      ...identity,
      theme: identity.theme ?? "light",
      status: result.status,
      path: relative(this.root, destination),
      test: test.titlePath().join(" > "),
    });
  }

  async onEnd() {
    const manifest = {
      version: 1,
      generated_at: new Date().toISOString(),
      browser_lock: "surfaces/operator-kit/visual/browser-lock.json",
      evidence: this.records.sort((a, b) => a.path.localeCompare(b.path)),
    };
    writeFileSync(join(this.root, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
    writeFileSync(join(this.root, "contact-sheet.html"), this.html());
    await this.pngSheets();
  }

  private html(): string {
    const cards = this.records.map((item) => `
      <figure>
        <img src="${xml(item.path)}" alt="${xml(`${item.app}, ${item.surface}, ${item.scenario}, ${item.viewport.label}`)}">
        <figcaption><strong>${xml(item.surface)} · ${xml(item.scenario)}</strong><br>${xml(item.viewport.label)} · ${xml(item.state)} · ${xml(item.theme)}</figcaption>
      </figure>`).join("");
    return `<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Evidências visuais do operador</title><style>body{font:14px system-ui;margin:24px;background:#fcf6f1;color:#3b2a1e}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}figure{margin:0;background:white;border:1px solid #dec9bb;border-radius:10px;overflow:hidden}img{display:block;width:100%;height:220px;object-fit:contain;background:#eee}figcaption{padding:12px;line-height:1.45}</style><h1>Evidências visuais do operador</h1><main>${cards}</main></html>\n`;
  }

  private async pngSheets() {
    const groups = Map.groupBy(this.records, (record) => record.app);
    for (const [app, records] of groups) {
      if (!records.length) continue;
      const width = 320;
      const imageHeight = 220;
      const labelHeight = 52;
      const columns = Math.min(4, records.length);
      const rows = Math.ceil(records.length / columns);
      const canvas = sharp({
        create: { width: columns * width, height: rows * (imageHeight + labelHeight), channels: 4, background: "#fcf6f1" },
      });
      const composites: sharp.OverlayOptions[] = [];
      for (let index = 0; index < records.length; index += 1) {
        const record = records[index]!;
        const left = (index % columns) * width;
        const top = Math.floor(index / columns) * (imageHeight + labelHeight);
        const image = await sharp(join(this.root, record.path)).resize(width, imageHeight, { fit: "contain", background: "#ffffff" }).png().toBuffer();
        const label = await sharp(Buffer.from(`<svg width="${width}" height="${labelHeight}"><rect width="100%" height="100%" fill="#fff"/><text x="10" y="20" font-family="sans-serif" font-size="13" fill="#3b2a1e">${xml(`${record.surface} · ${record.scenario}`)}</text><text x="10" y="40" font-family="sans-serif" font-size="12" fill="#6e5a48">${xml(`${record.viewport.label} · ${record.state}`)}</text></svg>`)).png().toBuffer();
        composites.push({ input: image, left, top }, { input: label, left, top: top + imageHeight });
      }
      await canvas.composite(composites).png().toFile(join(this.root, `contact-sheet-${safe(app)}.png`));
    }
  }
}
