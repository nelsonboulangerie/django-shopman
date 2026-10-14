# WP-SUPERFÍCIES-MESMO-TRILHO: um contrato de engenharia para todos os apps

> Work package aberto em 14/10/2026, por decisão do dono, depois de mais uma
> falha intermitente do gate `Marketing — cadeia completa` na merge queue. Este
> WP é independente do WP-WATCHMAN: aqui o objeto observado é a fábrica das
> superfícies, não a saúde do Django em produção.

## 1. Decisão

Os apps não terão dez receitas implícitas de build, teste e evidência. Todos passam
por um **trilho canônico versionado**, fornecido pelo `operator-kit` e cobrado pela
CI. Diferença de domínio continua permitida; diferença acidental de ferramenta,
harness, ordem de boot, critério visual ou nome de gate não.

O objetivo não é afrouxar o Marketing até ficar verde. É separar três coisas que
hoje estão misturadas:

1. contrato funcional e de acessibilidade, que deve ser determinístico;
2. geometria responsiva, que o scanner canônico consegue avaliar por regra;
3. revisão estética por pixels, que é útil em poucos marcos escolhidos, mas não
   deve transformar todo detalhe assíncrono em 82 arquivos binários frágeis.

## 2. O que a evidência já prova

O Marketing não é apenas "mais um app" na esteira atual. Ele recebeu uma fábrica
própria ao longo de muitas ondas e virou, sem decisão explícita, a exceção mais cara.

| Evidência em `main` (14/10) | Marketing | Demais superfícies observadas |
|---|---:|---:|
| Baselines PNG versionadas | **82** (4,7 MB) | POS 4; todas as outras 0 |
| Linhas TypeScript no diretório visual | **1.351 em um único spec** | POS 108; Compras 114; Cozinha 201 |
| Configurações Playwright próprias | **3** | 1 a 5, sem contrato uniforme |
| Commits desde 01/09 cujo assunto cita baseline/retrato/snapshot | **45** | POS 1; Produção 0; Compras 0; Pedidos 5 |
| Receita visual | `nuxt dev`, client-only, mock Python | Compras usa build de produção + mock Node + scanner |
| Job de CI | job monolítico exclusivo em macOS | matriz genérica e alguns jobs especiais |

O incidente que abriu este WP também não foi uma diferença sutil de rasterização.
No primeiro ciclo do PR do Watchman, o teste passou. Na merge queue, o cenário
`settings__offer-form__1280x800__light` capturou a tela **sem o diálogo**, apesar de
o teste tê-lo visto antes da captura: 194.967 pixels (20%) divergiram. Os outros 80
cenários passaram. A `main` entre os dois ciclos só recebeu documentação.

Isso aponta para uma corrida de ciclo de vida/estado no harness ou no app: a
interação fica momentaneamente pronta, uma carga tardia recompõe a página e o
retrato acontece depois. Atualizar a baseline seria aceitar uma tela errada. Repetir
até passar esconderia o defeito. O gate precisa provar e manter a **prontidão da
cena**, não apenas esperar o primeiro `data-v-app` e torcer para que o DOM pare.

Há um segundo achado: os demais apps também não estão realmente no mesmo trilho.
O Marketing apenas tornou a divergência mais visível. Existem de uma a cinco
configurações Playwright por app, `nuxt dev` e build de produção, mocks Python e
Node, matrizes com e sem pixel baseline, jobs genéricos e jobs exclusivos. Portanto
este WP não é uma reforma isolada do Marketing.

## 3. Hipóteses a provar antes de consertar

1. **Prontidão insuficiente.** `openScenario()` espera hidratação estrutural, mas
   não há uma barreira canônica de dados/rota/cena estável. Respostas tardias podem
   substituir estado depois de um clique.
2. **Dev server no gate visual.** Compilação lazy e HMR acrescentam transições de
   estado que não existem na imagem de produção. Compras documenta exatamente esse
   problema e já usa build de produção.
3. **Golden master em excesso.** O mesmo spec mistura comportamento, acessibilidade,
   geometria e pixel exato; qualquer falha produz um grande diff sem classificar a
   causa.
4. **Harness particular.** Mock Python, três configs e variáveis especiais mantêm
   o Marketing fora do caminho exercitado pelas outras superfícies.
5. **Ausência de contrato de equivalência.** A CI verifica versões, mas não verifica
   se cada app possui as mesmas fases, helpers, políticas de retry, evidências e
   exceções declaradas.

Cada hipótese deve terminar como **confirmada ou refutada por experimento**. Não
vale reescrever o app com base apenas nesta leitura inicial.

## 4. O trilho canônico

Cada superfície declara um manifesto pequeno, consumido localmente e pela CI:

```ts
export default defineSurfaceContract({
  id: "marketing",
  kind: "operator",
  commands: {
    unit: "npm run test:unit",
    component: "npm run test:component",
    build: "npm run build",
  },
  browser: {
    mock: "tests/support/mockBackend.mjs",
    scenarios: "tests/scenarios.ts",
    signatureViews: [],
  },
});
```

O formato final pode mudar durante o desenho, mas o contrato precisa gerar ou
validar as mesmas fases para todas as superfícies aplicáveis:

1. instalação reproduzível (`npm ci`) e versões canônicas;
2. lint e typecheck;
3. unitários e componentes;
4. build de produção;
5. smoke do artefato produzido;
6. fluxos funcionais no navegador;
7. acessibilidade;
8. scanner de geometria/responsividade do `operator-kit`;
9. segurança e PWA quando a capability existir;
10. evidência diagnóstica com o mesmo formato e retenção.

O pipeline é por **capability**, não por nome do app. Uma superfície pode não ter
PWA ou autenticação, mas a ausência é declarada e validada; não é um `if` perdido
num YAML. Exceções exigem motivo, responsável e data de expiração.

## 5. Política visual canônica

- Regra semântica, acessível ou geométrica vira asserção/scanner, não pixel.
- Evidência PNG pode ser capturada em toda execução sem ser golden master.
- Baseline pixel a pixel fica restrita a poucas `signatureViews` deliberadamente
  escolhidas. A quantidade máxima inicial será definida após medir valor e custo;
  nenhuma superfície começa com 82 por inércia.
- Toda cena expõe uma barreira explícita de prontidão, por exemplo
  `data-surface-ready` + estado do cenário, e o helper confirma que o sujeito ainda
  está presente imediatamente antes e depois da captura.
- O gate usa o build de produção. `nuxt dev` fica para desenvolvimento local.
- Relógio, locale, timezone, fontes, animações, viewport, backend e dados são
  fixados pelo helper compartilhado.
- Baseline nunca é promovida automaticamente a partir de `actual.png`. A revisão
  registra por que a mudança visual é desejada.
- Retry não transforma vermelho em verde. Uma repetição pode classificar flake e
  produzir evidência, mas o orçamento de flake continua reprovado até a causa ser
  removida.

## 6. Ondas de execução

### Onda 1 — autópsia reproduzível do Marketing

- Rodar o cenário da oferta repetidamente no mesmo commit, com trace da sequência
  de requests, eventos de rota, mounts/unmounts do diálogo e mutações relevantes.
- Comparar `nuxt dev` e build de produção.
- Identificar qual carga tardia fecha/substitui o diálogo e criar um teste funcional
  mínimo que falhe sem depender de screenshot.
- Medir taxa de flake de cada uma das 82 cenas em pelo menos 20 repetições
  controladas; publicar ranking, duração e classe de falha.
- Inventariar, para as dez superfícies, comandos, configs, mocks, gates, capabilities,
  duração, flakes e evidências.

Saída: laudo causal, não uma lista de sintomas.

### Onda 2 — contrato e runner canônicos

- Criar `defineSurfaceContract` e um runner único no `operator-kit`.
- Criar um gate de drift que compare todas as superfícies com o contrato.
- Padronizar artefatos, nomes de fases, ambiente determinístico e diagnósticos.
- Manter adaptadores temporários para não exigir um big bang.

### Onda 3 — Marketing no trilho

- Corrigir a corrida provada na onda 1.
- Migrar mock, boot e cenas para o harness compartilhado e build de produção.
- Separar asserções funcionais, a11y, geometria e assinatura visual.
- Reduzir os goldens com critério explícito; preservar screenshots restantes como
  evidência não bloqueante quando ainda forem úteis.
- Apagar configs e helpers particulares que o contrato substituiu.

### Onda 4 — todas as superfícies

- Migrar em lotes pequenos, começando por uma superfície estável como controle.
- Remover condicionais por nome de app dos workflows e substituí-las por capability.
- Fazer o gate de drift começar informativo e tornar-se obrigatório quando todas as
  superfícies estiverem declaradas.

### Onda 5 — orçamento permanente de confiabilidade

- Publicar duração e taxa de flake por fase e superfície.
- Sinalizar regressão de tempo, novo helper particular ou nova exceção vencida.
- Meta: qualquer pessoa consegue reproduzir localmente o mesmo comando que a CI
  executa, com o mesmo artefato e o mesmo diagnóstico.

Cada onda usa branch e PR próprios e percorre a merge queue inteira.

## 7. Critérios de aceite

- O cenário `nova oferta` passa 100 execuções consecutivas no runner da CI e local
  sem retry; uma mutação que reproduza a corrida faz o teste funcional reprovar.
- Todas as superfícies possuem manifesto validado e percorrem o mesmo pipeline por
  capability.
- Zero condição nova na CI baseada diretamente em `matrix.app == <nome>`; exceções
  existentes foram removidas ou estão declaradas com expiração.
- Build visual usa artefato de produção em todas as superfícies.
- Nenhuma baseline é aceita apenas porque veio da CI; toda assinatura visual tem
  dono, propósito e histórico de decisão.
- Taxa de flake dos gates obrigatórios é inferior a 0,1% em 30 dias; qualquer flake
  acima do orçamento abre trabalho e não vira rotina de rerun.
- Tempo total da esteira não piora: o runner compartilha instalação/build e distribui
  cenas sem sacrificar isolamento.
- Uma mudança no `operator-kit` consegue provar, numa única matriz, quais apps e
  capabilities foram exercitados — sem depender da memória de quem alterou o kit.

## 8. O que este WP não autoriza

- Não atualizar as 82 baselines para fazer a fila passar.
- Não desativar o gate de Marketing antes de haver cobertura equivalente.
- Não tornar todos os apps iguais visualmente ou apagar diferenças de domínio.
- Não reescrever todas as superfícies de uma vez.
- Não aceitar retry automático como solução de estabilidade.

O resultado esperado é mais rigor com menos ruído: uma só fábrica, diferenças
explícitas e falhas que digam qual contrato quebrou.
