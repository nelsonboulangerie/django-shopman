# PROMPT — P1-E: aplicar env NUXT_PUBLIC_DJANGO_BASE_URL no App Platform (alpha) + rebuild

Você é o Claude Code com acesso ao repo Django Shopman (/Users/pablovalentini/Dev/Claude/django-shopman) e ao contexto DO (doctl --context shopman-alpha-deploy).

## Contexto
- Bug observado no alpha: a página Feeds do Gestor (gestor.boulangerie.com.br/feeds) renderiza links com http://127.0.0.1:8000 (Admin, Ver feed, Abrir TV) — quebrados no ar.
- Causa raiz (docs/reports/2026-08-28-revisao-alpha-gestor-pedidos.md §10/§12): o serviço orders-nuxt no App Platform VIVO não tem a env NUXT_PUBLIC_DJANGO_BASE_URL (RUN_AND_BUILD_TIME), então o bundle client foi buildado com o fallback 127.0.0.1:8000. O .do/app.alpha-subdomains.yaml (espelho de referência) JÁ tem a env para orders-nuxt (linha ~605) — o spec VIVO está desatualizado/buildado antes.
- Decisão do dono (B-1): APROVADO aplicar; base pública = https://api.boulangerie.com.br (os 7 irmãos pos/kds/production/purchase/hub/marketing/bi usam essa base).

## Tarefa
1. Capturar o spec vivo: doctl --context shopman-alpha-deploy apps spec get <APP_ID> --format yaml > /tmp/spec-vivo.yaml (preserve o arquivo).
2. No bloco envs do componente orders-nuxt do spec vivo, garantir (adicionar se faltar): key NUXT_PUBLIC_DJANGO_BASE_URL, scope RUN_AND_BUILD_TIME, value https://api.boulangerie.com.br, type GENERAL. RUN_AND_BUILD_TIME é obrigatório: a env é assada no bundle client no build; RUN_TIME não basta.
3. Aplicar PRESERVANDO secrets: edite o spec capturado e aplique com doctl apps update <APP_ID> --spec /tmp/spec-vivo.yaml --update-sources --wait. NUNCA use doctl apps update --spec com o .do/app.alpha-subdomains.yaml do repo (sobrescreveria o spec vivo e apagaria variáveis encriptadas do painel).
4. Garantir o REBUILD da imagem orders: env RUN_AND_BUILD_TIME só entra no bundle se a imagem for rebuildada. Confirme que a tag orders foi publicada/redeployada (deploy_on_push); se preciso, dispare o workflow .github/workflows/deploy-images.yml (componente orders) ou o redeploy manual do componente.
5. Checar o componente bi-nuxt: NÃO tem NUXT_PUBLIC_DJANGO_BASE_URL no spec do repo (bloco ~783+) — decida se o B.I. precisa da env (se usa djangoPublicBaseUrl) e aplique o mesmo tratamento se necessário.
6. NÃO mexer em mais nada do spec (topologia, outras envs, secrets).

## Verificação (pós-redeploy)
- Login gestor (admin/admin) -> Feeds: links Admin, Ver feed, Abrir TV devem abrir https://api.boulangerie.com.br/... com HTTP 200 (admin/shop/feed/, feed/*.xml, menuboard/*).
- Catálogo -> deep-links de feed idem. Curl: /menuboard/<ref>/ e /feed/<ref>.xml respondem 200 em https://api.boulangerie.com.br.

## Regras
- Worktree se for editar código do repo (não precisa para o spec DO).
- NUNCA sobrescrever secrets: parta sempre do doctl apps spec get.
- Se a base correta for outra (ex.: Admin em admin.boulangerie.com.br), confirme antes de aplicar (convenção atual: todos os irmãos usam api.boulangerie.com.br).
- Reporte o diff do spec aplicado (antes/depois) e a evidência da verificação.
