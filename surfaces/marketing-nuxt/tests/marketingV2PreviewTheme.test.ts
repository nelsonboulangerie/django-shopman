import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

function read(path: string): string {
  return readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
}

function lightTheme(css: string): string {
  const root = css.indexOf(":root {");
  const end = css.indexOf("}", root);
  if (root < 0 || end < 0) throw new Error("bloco :root ausente");
  return css.slice(root, end + 1);
}

function tokenValue(css: string, token: string): string | null {
  const match = css.match(new RegExp(`${token}\\s*:\\s*([^;]+);`));
  return match ? match[1].trim() : null;
}

const canonicalTokens = [
  "--radius",
  "--background",
  "--foreground",
  "--card",
  "--card-foreground",
  "--primary",
  "--primary-foreground",
  "--secondary",
  "--secondary-foreground",
  "--muted",
  "--muted-foreground",
  "--accent",
  "--accent-foreground",
  "--destructive",
  "--destructive-foreground",
  "--success",
  "--success-foreground",
  "--warning",
  "--warning-foreground",
  "--info",
  "--info-foreground",
  "--border",
  "--input",
  "--ring",
  "--rail",
  "--rail-foreground",
  "--sidebar",
  "--sidebar-foreground",
] as const;

describe("prévia navegável do Marketing V2", () => {
  const preview = read("../public/marketing-v2-preview/styles.css");
  const operatorTheme = read(
    "../../operator-kit/app/assets/css/operator-theme.css",
  );

  it("replica literalmente o tema claro canônico do operator-kit", () => {
    const previewLight = lightTheme(preview);
    const canonicalLight = lightTheme(operatorTheme);

    for (const token of canonicalTokens) {
      expect(
        tokenValue(previewLight, token),
        `${token} divergiu do operator-kit`,
      ).toBe(tokenValue(canonicalLight, token));
    }
  });

  it("usa a fonte incorporada do app e não recria o tema coral da maquete", () => {
    expect(preview).toContain('font-family: "Instrument Sans"');
    expect(preview).toContain("/fonts/instrument-sans-latin-6219bc4b.woff2");
    expect(preview).not.toMatch(/\b(?:Georgia|Inter)\b/);
    expect(preview).not.toMatch(
      /--(?:ink|paper|surface|warm|coral|green|amber|line|soft-line|shadow)\s*:/,
    );
    expect(preview).not.toContain("color: var(--muted);");
  });
});
