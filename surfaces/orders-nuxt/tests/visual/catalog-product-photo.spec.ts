import { expect, test } from "@playwright/test";

// Foto por arquivo no painel de EDIÇÃO do produto (antes só na criação): escolhe,
// padroniza e guarda; a URL entra no rascunho e o Salvar do painel grava.
// Capturas para auditoria, sem baseline.
const CASES = [
  { id: "xl", width: 1440, height: 900 },
  { id: "phone", width: 390, height: 844 },
] as const;

// PNG 1x1 (dourado): o mock devolve a imagem como veio.
const PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGM4sWYGAAQnAgKmyr6/AAAAAElFTkSuQmCC",
  "base64",
);

for (const viewport of CASES) {
  test(`foto no painel do produto · ${viewport.id}`, async ({ page }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.goto("/catalog?sku=TRADI");
    const photo = page.getByTestId("detail-photo-input");
    await expect(photo).toBeAttached();
    await photo.setInputFiles({ name: "foto.png", mimeType: "image/png", buffer: PIXEL });
    const use = page.getByTestId("detail-photo-use");
    await expect(use).toBeEnabled();
    await use.click();
    await expect(use).toHaveText("Foto guardada");
    await expect(page.getByRole("textbox", { name: "URL da imagem" })).toHaveValue(
      "https://media.example.com/produtos/foto-padronizada.jpg",
    );
    await use.scrollIntoViewIfNeeded();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: testInfo.outputPath(`photo-${viewport.id}.png`) });
  });
}
