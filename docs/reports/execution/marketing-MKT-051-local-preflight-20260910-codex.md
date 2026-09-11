# MKT-051 — preflight local de shadow e canário

**Estado:** evidência local concluída; ambiente externo ainda não autorizado

**Ambiente:** worktree isolada, bancos pytest descartáveis e simulador sem rede

**Efeito externo:** nenhum

## Integração sem conflito

Antes do preflight, a branch incorporou 34 commits novos de `origin/main`, concentrados
em Produção e PDV. Nove arquivos tinham alterações nos dois lados e foram combinados
automaticamente sem descartar nenhum deles. As duas folhas legítimas de migration do
Backstage foram preservadas por uma migration de merge vazia; nenhum histórico foi
renumerado ou reescrito.

Antes do fechamento, outros treze commits já presentes em `origin/main` também foram
incorporados. Nove trouxeram ajustes de PDV/display e um chevron canônico para os
`select` nativos do `operator-kit`; os dois finais trouxeram a impressão compartilhada
de etiquetas de Produção, seguidos por dois commits isolados de reconhecimento da rota
do display do PDV. Os merges permaneceram limpos e a branch terminou sem
commits pendentes de `origin/main`. As sete referências visuais que contêm `select`
foram revistas e atualizadas somente depois de confirmar que a diferença se limitava
ao novo ícone e ao espaço reservado para ele. A integração final passou ainda 48 testes
de seed/release/impressão e o kit compartilhado subiu para 26 arquivos / 237 testes.

O merge também trouxe um componente novo do `operator-kit`. A instalação limpa revelou
um lock ainda em Vitest 4.1.9 e SVGO 4.0.2, com duas vulnerabilidades moderadas e uma
alta. O follow-up eleva somente Vitest para 4.1.11 e força SVGO 4.1.0, versões já usadas
pelo Marketing. O workflow agora audita separadamente o kit compartilhado e o app.

## Evidência de shadow/reconciliação sem provider

- 19 drills backend e 4 probes Nuxt passaram;
- 56 testes do runtime real de outbox, ledger, lease, retry seletivo, resultado
  incerto e reconciliação passaram;
- o cenário incerto usa `lookup` e nunca repete `send`;
- diagnóstico do banco demo: `result=OK`, zero alerta aberto, zero chamada de provider,
  três outboxes despachadas, uma futura não vencida e 36/36 destinos confirmados pelo
  simulador;
- nenhuma mensagem, publicação, credencial ou chamada externa foi usada.

## Capacidade

O gate completo materializou 200 mil candidatos, 100 mil elegíveis e 20 mil destinos.
A primeira medição ocorreu enquanto outro pytest e um renderer externo ocupavam mais
CPU que os oito cores lógicos; o p95 de audiência ficou inconclusivo em 3,70 s. Depois
que o processo concorrente terminou, o mesmo teste, sem alteração de código, passou:

| Métrica | Resultado | Budget |
|---|---:|---:|
| audiência p95 | 1,85 s | ≤2 s |
| queries | 6 | ≤30 |
| pico de memória | 82,59 MiB | ≤256 MiB |
| fan-out de 20 mil | 8,56 s | ≤10 s |
| claim worker 1/2 | 0,072 / 0,056 s | ≤1 s |
| interseção entre workers | 0 | 0 |

## Regressão do HEAD integrado

- Backend Marketing: 641 casos passaram na execução ampla; cinco testes antigos
  denunciaram contratos de teste desatualizados e depois passaram focados. Eles agora
  usam capacidades granulares, protocolo CAS/idempotência/confirmação e horário útil
  determinístico; dois casos permanecem pulados por desenho.
- Marketing Nuxt: 34 arquivos / 245 testes, lint, typecheck e build verdes.
- Browser: 1 E2E, 2 fluxos de acessibilidade e 69/69 estados visuais verdes, incluindo
  uma segunda passagem integral após a atualização dirigida dos sete `select`.
- Segurança: 4 contratos Marketing, audit Marketing zero; 26 arquivos / 237 testes do
  operator-kit e audit do kit zero.
- Migration drift, Ruff, YAML e `git diff --check`: verdes.

## Limite deste preflight

Isto prova o comportamento local hermético e prepara o canário, mas não declara que um
provider real aceitou uma consequência. Push, PR, merge, imagem, deploy, staging,
produção, credencial externa, destinatário e envio continuam intocados. O próximo
passo externo deve nomear ambiente, commit, flags, alvo limitado, janela, observador e
rollback antes da execução.
