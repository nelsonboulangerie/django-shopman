
const { chromium } = require("@playwright/test");
async function look(viewport, hasTouch) {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport, hasTouch });
  const page = await ctx.newPage();
  await page.goto("http://127.0.0.1:3004/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3000);
  const data = await page.evaluate(() => {
    const q = (s) => document.querySelector(s);
    const txt = document.body.innerText.slice(0, 120).replace(/\n/g, ' | ');
    return {
      oldRail: !!q('[data-suite-rail]'),
      newSidebar: !!q('[id$="-sidebar"]') || !!q('[data-slot="root"][style*="--width"]'),
      bottomTab: !!q('nav[aria-label]'),
      railBg: q('[style*="--width"]')?.getAttribute('class')?.slice(0,80),
      body: txt,
    };
  });
  await browser.close();
  return data;
}
(async () => {
  console.log("desktop:", JSON.stringify(await look({ width: 1440, height: 900 }, false)));
  console.log("mobile:", JSON.stringify(await look({ width: 390, height: 844 }, true)));
})();
