# Brief comum das prévias do modo compacto (30/10/2026)

Somente PRÉVIA. Nada em `surfaces/` da worktree, Core, backend, kit do produto; sem commit,
push, PR, merge ou deploy (a sessão-mãe cuida do repositório). Tudo roda em CÓPIA temporária
extraída por `git archive origin/main surfaces/<app> surfaces/operator-kit`, Node 22
(`/opt/homebrew/opt/node@22/bin`), `npm ci --ignore-scripts --no-audit --no-fund` em cada um.
Portas 4186-4193, 38792, 38798, 38898 são de outras prévias: não use, não mate processos alheios.

## Método (conciliação reversa)
- A = app atual intacto (só simulação de conexão, se necessária, aplicada igual em A e C).
- C = A + aplicador `apply-compact.mjs` seu, mínimo, com âncoras de string que FALHAM
  alto se não casarem. Componentes e fluxos maduros ficam idênticos.
- Peças compartilhadas: `compact-kit/OperatorCompactBar.vue` e `OperatorCompactSeal.vue`,
  copiadas para o operator-kit da cópia por `node compact-kit/apply-kit.mjs <kit>`.
  Referência de uso real: `kds-compact/apply-compact.mjs` (KDS já feito).
- Selo do app leva à "Central" simulada: passe `to="https://sim-washing-refers-roberts.trycloudflare.com/"`.

## Regras do compacto (hipótese em teste, não aprovada)
1. Celular (< md): cabeçalho = UMA linha: selo 44px com chip de conexão | grupo Filtro ·
   Busca elástica · ⋮ | Avisos (controle próprio por padrão; `?avisos=options` como variante).
2. Título de SEÇÃO não se repete (é a vaga ativa da barra inferior/lateral; fica no h1 acessível).
   Tela de REGISTRO (detalhe, conferência, venda) mantém identidade do registro visível
   (`#identity`) e o voltar (`#lead`); nunca esconda o que identifica o registro/tarefa.
3. Cadência ("Atualiza sozinho a cada N s") sai da linha permanente: vai para o topo das Opções.
   Erro e sem conexão continuam EXPLÍCITOS no topo/conteúdo, com cor + texto.
4. Estados que hoje ganham vaga de ícone por serem urgentes (ex.: "Visto", "Som bloqueado",
   "Não salvo", PIX pendente) NÃO podem sumir no ⋮: viram aviso explícito ou ficam visíveis.
5. Ações primárias da tela que hoje caem numa toolbar própria ("Nova encomenda" etc.) vão
   para o lugar da tarefa (rodapé/ação flutuante já existente ou ⋮), sem barra nova.
6. Busca/filtro ativo: faixa logo abaixo da linha com contagem e Limpar (o cabeçalho não rola).
7. Sem ☰ no celular: a gaveta completa abre pelo "Mais" da barra inferior. Se o app NÃO tiver
   "Mais", registre como bloqueio (a gaveta tem troca de operador/Ajustes).
8. Desktop: preserve o indicador de conexão (OperatorLiveStatus) e o rail; mude só o necessário.
9. Alvos ≥44px, sem rolagem horizontal, texto sem corte que mude sentido, sem travessão em copy.

## Evidência (Playwright headless, NÃO use o navegador do app)
Use `@playwright/test`/`playwright` do node_modules do app (chromium já em
~/Library/Caches/ms-playwright). Viewports: 320×740, 320×568, 375×667, 390×844, 1440×900.
Para A e C: capturas `.png` na sua pasta, e medidas JSON (topo do 1º conteúdo útil, alturas de
topo e base, scrollWidth, tamanhos dos alvos do cabeçalho). Exercite: busca ativa + Limpar,
filtro, Opções, Avisos, estado sem conexão, um erro de escrita e a recuperação, modais/folhas
da tela. Diga o que o mock NÃO cobre. Não declare equivalência funcional.

## Entrega
Pasta `docs/previews/consolidacao-2026-10-30/<app>-compact/`: `apply-compact.mjs`, `run.sh`
(reprodutível, portas fixas), capturas, `evidence.json`, `README.md` curto (preservado /
melhorado / precisa de decisão, com riscos a 320px e pouca altura). Deixe os servidores A e C
rodando em segundo plano e abra `cloudflared tunnel --url http://127.0.0.1:<porta> --no-autoupdate`
para cada um (DNS local pode demorar; teste com `curl --doh-url https://1.1.1.1/dns-query`).
Relatório final: URLs dos túneis com caminhos úteis, medidas A×C, achados adversariais.
