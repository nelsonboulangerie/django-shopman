import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import os from 'node:os';
import { basename, resolve } from 'node:path';
const root = process.cwd();
assert.equal(basename(root), 'django-shopman-orders-execution-20260910');
const require = createRequire(resolve(root, 'surfaces/orders-nuxt/package.json'));
const { chromium, expect } = require('@playwright/test');
const { ref } = JSON.parse(readFileSync(resolve(root, '.orders-lab/legacy-manifest.json'), 'utf8'));
const audit = () => JSON.parse(execFileSync('/Users/pablovalentini/Dev/Claude/django-shopman/.venv/bin/python', [resolve(root, 'docs/reports/execution/orders-20260910/command_budget/audit_note.py'), ref], { encoding: 'utf8' }));
const baseline = audit();
const samples = [];
let mode = 'normal';
let posts = 0;
let lookups = 0;
let currentKey;
const keys = new Set();
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ baseURL: 'http://127.0.0.1:3007', viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(15000);
  const accessStart = performance.now();
  await page.goto('/');
  await page.getByRole('textbox', { name: 'Usuário', exact: true }).fill('orders-lab');
  await page.getByLabel('Senha', { exact: true }).fill('synthetic-lab-only-20260910');
  await page.getByRole('button', { name: 'Entrar', exact: true }).click();
  await page.getByRole('heading', { name: 'Entre para operar' }).waitFor({ state: 'hidden' });
  await page.goto('/' + ref);
  const advance = page.getByRole('button', { name: 'Iniciar preparo', exact: true });
  await expect(advance).toBeEnabled();
  const accessMs = performance.now() - accessStart;
  const note = page.getByPlaceholder('Instruções de preparo para a cozinha…');
  const save = page.getByRole('button', { name: 'Salvar nota', exact: true });
  await page.route('**/orders/' + ref + '/notes/**', async route => {
    const request = route.request();
    if (request.method() === 'POST') {
      posts += 1;
      currentKey = request.headers()['idempotency-key'] || request.postDataJSON()?.idempotency_key;
      assert.ok(currentKey);
      keys.add(currentKey);
      if (mode === 'lost_response') {
        const response = await route.fetch();
        assert.equal(response.status(), 200);
        assert.equal((await response.json()).outcome, 'applied');
        await route.abort('failed');
      } else { await route.continue(); }
    } else {
      if (request.method() === 'GET') {
        lookups += 1;
        assert.equal(new URL(request.url()).searchParams.get('idempotency_key'), currentKey);
      }
      await route.continue();
    }
  });
  const stamp = Date.now();
  for (mode of ['normal', 'lost_response']) {
    for (let index = 0; index < 20; index += 1) {
      const value = 'Synthetic budget ' + stamp + ' ' + mode + ' ' + index;
      await note.fill(value);
      await expect(save).toBeEnabled();
      const previousPosts = posts;
      const previousLookups = lookups;
      await save.evaluate(element => {
        window.__commandBudget = {};
        element.addEventListener('click', () => {
          const start = performance.now();
          let seenBusy = false;
          const primary = document.querySelector('[data-action="advance"]');
          const observer = new MutationObserver(() => {
            if (element.disabled && window.__commandBudget.feedback_ms === undefined) {
              window.__commandBudget.feedback_ms = performance.now() - start;
              requestAnimationFrame(() => requestAnimationFrame(() => {
                window.__commandBudget.feedback_after_two_frames_ms = performance.now() - start;
              }));
            }
            if (primary.disabled) seenBusy = true;
            if (seenBusy && !primary.disabled) {
              window.__commandBudget.confirmed_ui_ms = performance.now() - start;
              observer.disconnect();
            }
          });
          observer.observe(document.body, { attributes: true, subtree: true, attributeFilter: ['disabled'] });
        }, { once: true, capture: true });
      });
      await save.click();
      await page.waitForFunction(() => window.__commandBudget?.confirmed_ui_ms !== undefined && window.__commandBudget?.feedback_after_two_frames_ms !== undefined);
      const timing = await page.evaluate(() => window.__commandBudget);
      assert.equal(posts - previousPosts, 1);
      assert.equal(lookups - previousLookups, mode === 'lost_response' ? 1 : 0);
      const canonical = await (await page.request.get('/api/v1/backstage/orders/' + ref + '/')).json();
      assert.equal(canonical.order.kitchen_note, value);
      assert.equal(await note.inputValue(), value);
      samples.push({ mode, index, ...timing, posts: 1, receipt_lookups: lookups - previousLookups, retyped_fields: 0, recovery_clicks: 0 });
      writeFileSync(resolve(root, '.orders-lab/command-budget-progress.json'), JSON.stringify(samples, null, 2));
    }
  }
  const after = audit();
  assert.equal(after.kitchen_note_events - baseline.kitchen_note_events, 40);
  assert.equal(keys.size, 40);
  function distribution(values) {
    const sorted = values.toSorted((a, b) => a - b);
    return { n: sorted.length, p50: sorted[Math.ceil(sorted.length * .5) - 1], p95: sorted[Math.ceil(sorted.length * .95) - 1], max: sorted.at(-1) };
  }
  const result = { version: '1d84dcc5b', environment: { platform: os.platform(), arch: os.arch(), cpu: os.cpus()[0].model, logical_cpus: os.cpus().length, memory_bytes: os.totalmem(), node: process.version, chromium: browser.version(), viewport: [1440, 1000], concurrent_sqlite_ci: true },
    automated_login_and_navigation_ms: accessMs, samples,
    feedback_ms: distribution(samples.map(value => value.feedback_ms)),
    feedback_after_two_frames_ms: distribution(samples.map(value => value.feedback_after_two_frames_ms)),
    normal_confirmed_ui_ms: distribution(samples.filter(value => value.mode === 'normal').map(value => value.confirmed_ui_ms)),
    recovered_confirmed_ui_ms: distribution(samples.filter(value => value.mode === 'lost_response').map(value => value.confirmed_ui_ms)),
    canonical_note_events_added: after.kitchen_note_events - baseline.kitchen_note_events,
    unique_intentions: keys.size, posts, receipt_lookups: lookups,
    scope: 'One operator, one synthetic order, after-only technical assay; automation time is not human active time.' };
  writeFileSync(resolve(root, '.orders-lab/command-budget-frames-result.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify({ feedback_ms: result.feedback_ms, feedback_after_two_frames_ms: result.feedback_after_two_frames_ms, normal_confirmed_ui_ms: result.normal_confirmed_ui_ms, recovered_confirmed_ui_ms: result.recovered_confirmed_ui_ms, posts, receipt_lookups: lookups, canonical_note_events_added: 40 }, null, 2));
} finally { await browser.close(); }
