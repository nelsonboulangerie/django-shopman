import { expect, test } from "@playwright/test";

// O worker de push é o que o build serve (`/operator-push-sw.js`), mas roda aqui, no
// processo do teste: a página tem CSP fechada (sem `unsafe-eval`), e o `new Function`
// dentro dela seria bloqueado pela própria trava que protege a Central.
test.describe("Central — Web Push", () => {
  test("o clique da notificação abre a action_url assinada pelo servidor", async ({ page, baseURL }) => {
    const response = await page.request.get("/operator-push-sw.js");
    expect(response.ok()).toBe(true);
    const source = await response.text();

    const handlers: Record<string, (event: unknown) => void> = {};
    const targets: string[] = [];
    const worker = {
      location: { origin: new URL(baseURL!).origin },
      addEventListener(name: string, handler: (event: unknown) => void) {
        handlers[name] = handler;
      },
    };
    const workerClients = {
      async matchAll() { return []; },
      async openWindow(url: string) {
        targets.push(url);
        return null;
      },
    };
    new Function("self", "clients", source)(worker, workerClients);

    let completion: Promise<unknown> = Promise.resolve();
    handlers.notificationclick?.({
      notification: {
        data: { action_url: "https://marketing.example.test/review/7" },
        close() {},
      },
      waitUntil(promise: Promise<unknown>) { completion = promise; },
    });
    await completion;

    expect(targets).toEqual(["https://marketing.example.test/review/7"]);
  });
});
