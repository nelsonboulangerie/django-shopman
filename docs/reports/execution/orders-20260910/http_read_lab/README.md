# Ensaio HTTP de leitura — laboratório sintético

Código medido: `8a016ae2e`. Banco exclusivo `orders_perf_lab`, PostgreSQL local
55439, Redis local 56389/db2, Daphne 8015 e Nitro 3005. Nenhum fornecedor real.
O runner força essas conexões e `DATABASE_CONN_MAX_AGE=0`, conforme o guia de
DigitalOcean para Daphne com conexão direta sem pool. Não altera produção.

Usar o Python canônico com pacotes do próprio worktree (o runner configura os
paths). Executar `run_http_lab.py migrate`, `seed N`, `serve`; em outro terminal
`measure N` e `measure N 3005`. N aceita somente 1, 10, 100 ou 500. O Nitro deve
usar o build Orders deste SHA e ambas as variáveis NUXT de Django apontadas a
`http://127.0.0.1:8015`, HOST=127.0.0.1 e PORT=3005. A porta 3005 é exclusiva.

Executar o navegador com Node 22, `ORDERS_PERF_LAB=1 ORDERS_PERF_N=N` e
`npm --prefix surfaces/orders-nuxt exec -- playwright test --config surfaces/orders-nuxt/playwright.performance.config.ts`.
Sequenciar seed → HTTP direto → BFF → navegador antes do próximo N. Não executar
outros testes de carga nem editar o código servidor durante as medições.

Cada pedido tem três itens fracionários, seis eventos, pagamento capturado,
reserva planejada e dados de contexto; estados alternam nas zonas canônicas.
As transações sintéticas anteriores permanecem imutáveis entre cargas. As
credenciais/cookies do laboratório ficam em `.orders-lab/http-lab-auth.json`
(mode 0600), nunca nos artefatos versionados. Não usar contas ou pedidos reais.

Cada endpoint tem uma primeira requisição e 20 amostras por concorrência 1/2/10.
p95 é o 19º valor ordenado; p50 é a mediana. Os cabeçalhos de instrumentação
existem apenas neste middleware de laboratório. Contam autenticação, queries e
serialização; acrescentam overhead. O BFF não repassa esses cabeçalhos: seus
tempos internos são indisponíveis, não zero. CPU é janela do processo, que
inclui outras threads simultâneas; RSS é fotografia do processo. Não são CPU
isolada ou memória exclusiva de uma requisição. Payload HTTP é descomprimido.

O navegador mede 20 páginas autenticadas, abertura/hidratação, entrada do filtro
e observação de uma linha. A primeira página usa contexto novo; as seguintes
podem usar cache. Login é excluído desta medição técnica e continua obrigatório
nas contagens integrais de jornada. Primeira requisição não significa banco,
SO ou processo frio: estes não são reiniciados entre todas as amostras.

Limites: um processo Daphne e um Nitro em macOS local, rede loopback, sem TLS,
sem rede/dispositivo/persona piloto; nenhuma inferência de ganho em campo.
Não mede escrita, fornecedor, fila de worker ou SLA homologado externo.

## Preparação com falha (preservada no histórico)

Gunicorn/Uvicorn não estavam instalados; adotou-se Daphne já usado pelo projeto.
Doorman recusou inicialmente chave/domínio ausentes com DEBUG=False; valores
exclusivamente sintéticos resolveram a preparação. A primeira busca de browser
usou textbox em vez de searchbox e foi interrompida. Outra execução falhou por
esgotamento das 100 conexões PostgreSQL: herdava age=60 sem o pool usado na
configuração publicada. A solução age=0 já era documentada, não é descoberta
de defeito novo de produção. Servidores próprios anteriores foram encerrados;
não se aumentou max_connections nem se encerrou processo de terceiros.

A limpeza inicial entre cargas encontrou FK protegida de PaymentTransaction;
a segunda encontrou a imutabilidade explícita do livro. A fixture final conserva
PaymentIntent/PaymentTransaction anteriores e reutiliza a mesma referência em
repetição. Nenhuma proteção do domínio foi desativada. Os pedidos/holds desta
base exclusivamente sintética são substituídos para controlar N.
