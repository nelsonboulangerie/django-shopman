import { expect, test } from "@playwright/test";

test.describe("Central — Web Push", () => {
  test("o clique da notificação abre a action_url assinada pelo servidor", async ({ page }) => {
    await page.goto("/");

    const opened = await page.evaluate(async () => {
      const source = await fetch("/operator-push-sw.js").then(response => response.text());
      const handlers: Record<string, (event: unknown) => void> = {};
      const targets: string[] = [];
      const worker = {
        location: { origin: window.location.origin },
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
      return targets;
    });

    expect(opened).toEqual(["https://marketing.example.test/review/7"]);
  });
});
