import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { basename, resolve } from 'node:path';
const root = process.cwd();
assert.equal(basename(root), 'django-shopman-orders-execution-20260910');
const require = createRequire(resolve(root, 'surfaces/orders-nuxt/package.json'));
const { chromium } = require('@playwright/test');
const { ref } = JSON.parse(readFileSync(resolve(root, '.orders-lab/legacy-manifest.json'), 'utf8'));
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ baseURL: 'http://127.0.0.1:3006', viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(15000);
  await page.goto('/');
  await page.getByRole('textbox', { name: 'Usuário', exact: true }).fill('orders-lab');
  await page.getByLabel('Senha', { exact: true }).fill('synthetic-lab-only-20260910');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await page.getByRole('heading', { name: 'Entre para operar' }).waitFor({ state: 'hidden' });
  await page.goto('/' + ref);
  const advance = page.getByRole('button', { name: 'Iniciar preparo', exact: true });
  await advance.waitFor();
  const path = '/api/v1/backstage/orders/' + ref + '/';
  const before = await (await page.request.get(path)).json();
  assert.equal(before.order.status, 'accepted');
  assert.ok(Array.isArray(before.order.timeline));
  const snapshot = () => JSON.parse(execFileSync('/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python', [resolve(root, 'docs/reports/execution/orders-20260910/legacy_browser/business_snapshot.py')], { encoding: 'utf8' }));
  const booksBefore = snapshot();
  const pending = page.waitForResponse(response => response.url().endsWith('/orders/' + ref + '/advance/') && response.request().method() === 'POST');
  await advance.click();
  const response = await pending;
  const result = await response.json();
  assert.equal(response.status(), 400);
  assert.equal(result.code, 'intention_required');
  const after = await (await page.request.get(path)).json();
  assert.equal(after.order.status, 'accepted');
  assert.deepEqual(after.order.timeline, before.order.timeline);
  assert.deepEqual(snapshot(), booksBefore);
  await page.screenshot({ animations: 'disabled', path: resolve(root, '.orders-lab/legacy-browser-blocked.png'), fullPage: true });
  writeFileSync(resolve(root, '.orders-lab/legacy-browser-result.json'), JSON.stringify({
    browser_source: '5a3383c9', backend_source: 'c935459be', authenticated_read: true,
    legacy_post_status: response.status(), refusal_code: result.code,
    order_status_before: before.order.status, order_status_after: after.order.status, timeline_unchanged: true, business_tables_unchanged: booksBefore,
  }, null, 2));
  console.log('Old browser read succeeded; incompatible POST refused; status and timeline unchanged.');
} finally { await browser.close(); }
