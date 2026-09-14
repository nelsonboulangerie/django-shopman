# Prompt de execução — WP-PWA fase F0 (Storefront)

> Copiar o bloco abaixo, inteiro, para o agente externo. Preencher os itens marcados
> `<<…>>` com os materiais do Anexo A antes de enviar. Uma fase por sessão, um PR por
> fase. As fases F1–F3 ganham prompt próprio quando a F0 estiver no ar.

```text
Você vai executar a fase F0 do plano docs/plans/WP-PWA-EXECUCAO.md no repositório
django-shopman (branch main). Leia, nesta ordem e por inteiro, antes de escrever
qualquer linha:

1. CLAUDE.md (regras do repositório; a seção sobre worktree é obrigatória)
2. docs/plans/WP-PWA-EXECUCAO.md (o brief: regras da casa, decisões fechadas A1–A10,
   tarefas F0.1–F0.9 com aceite, formato de entrega, o que NÃO fazer, Anexo A)
3. docs/plans/WP-PWA-CONFORMIDADE.md (o porquê; seção "Por surface" e "Gate make pwa")
4. docs/decisions/adr-026-operator-surface-security-envelope.md
5. surfaces/storefront-nuxt/server/utils/storefrontSecurity.ts,
   surfaces/storefront-nuxt/nuxt.config.ts,
   shopman/storefront/presentation/shop.py,
   shopman/shop/brand_tokens.py,
   shopman/shop/omotenashi/copy.py

ESCOPO DESTA SESSÃO: somente a fase F0 (Storefront). Nada de operator-kit, PDV,
backstage ou Web Push. Se uma tarefa da F0 parecer exigir algo fora da F0, pare,
registre no relatório e siga com o resto.

MATERIAIS DO DONO (Anexo A), já disponíveis:
- Símbolo da marca (SVG): <<caminho ou anexo>>
- Logotipo completo (SVG): <<caminho ou anexo>>
- theme_color: <<#7C3A40>>   background_color: <<#FCF7EE>>
- name: <<Nelson Boulangerie>>  short_name: <<Nelson>>  description: <<…>>
  (gravados no Admin em Loja; se não estiverem, o manifesto cai no fallback do
  build e você registra a pendência)
- Copy da tela offline e do convite de instalação: <<texto>> ou "voz da casa"
Sem o símbolo em SVG a F0.7 não roda: nesse caso pare na F0.6 e entregue o PR
parcial com a pendência nomeada.

REGRAS QUE REPROVAM O PR (resumo; a lista completa está no brief, seção 0 e 8):
- Trabalhe em worktree próprio. git add só de arquivo nomeado. Sem git stash.
- Node 22.x. Django só por .venv/bin/python.
- O service worker NÃO cacheia /api/, /events/, /admin/ nem resposta de navegação.
  Cache em runtime só para /img/products/** e /fonts/**.
- Nenhuma diretiva nova na CSP do Storefront. Ela já libera worker-src e manifest-src.
- Manifesto é rota Nitro lendo a projeção pública da loja (A1); ícones estáticos em
  public/pwa/ gerados por npm run pwa:assets a partir do SVG (A7); Shop.logo (upload)
  nunca vira ícone.
- Copy que o cliente lê vai em OmotenashiCopy (chaves PWA_*), nunca literal em componente.
- URL em inglês, identificador em inglês, texto de tela em português. Zero alias,
  zero nome antigo, zero TODO.
- Não pedir permissão de notificação; não há push nesta fase.
- Não tocar em packages/*.

ENTREGA (formato obrigatório, seção 7 do brief):
1. PR contra main, título "feat(storefront): PWA F0 — instalável, casco offline,
   atualização controlada", com o diff só dos arquivos da fase.
2. Saída colada dos gates, rodados com node 22 em surfaces/storefront-nuxt:
   npm test · npm run typecheck · npm run lint · npm run build · npm run test:e2e ·
   make pwa app=storefront (o gate você cria na F0.8, em tools/pwa-gate/).
   E, na raiz: .venv/bin/python -m pytest shopman/shop/tests/test_omotenashi_copy_keys.py
3. Evidência humana: curl -I de /manifest.webmanifest e /sw.js; captura do precache
   gerado provando ausência de /api/, /events/, /admin/; a imagem maskable-512 anexada
   para checagem da zona segura; se tiver aparelho, as provas da seção
   "Prova humana da F0". Se não tiver, diga que não tem, não simule.
4. Lista do que ficou de fora e por quê, e toda pendência do dono nomeada.
5. Atualize docs/reference/commands.md (make pwa) e o README da surface (seção PWA).

Relatório final em português, curto, factual: o que foi feito, o que foi provado, o
que ficou pendente. Contagem de testes não substitui evidência.
```
