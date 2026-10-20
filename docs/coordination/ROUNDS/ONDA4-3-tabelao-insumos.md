# ONDA4-3: tabelão de insumos

Ordem: `ORDERS/next-onda4.md`, frente 3. Base: `65b658d31`.
Branch: `codex/tabelao-insumos`. Estado: validação final antes do PR.

## Entrega

Custos e mínimos aceitam colar uma coluna na célula inicial, seguindo a ordem visível,
com vírgula decimal em TSV/CSV da casa. Campos vazios não substituem os valores já
rascunhados. A pilha do `useGridEdit` desfaz cada célula por vez, incluindo digitação
sobre valor colado. Limpar e salvar esvaziam a pilha. Valores inválidos aparecem junto
ao insumo e impedem a gravação, tanto na ação da mesa quanto na barra do celular.
O envio continua nos endpoints canônicos de lote, uma requisição por operação.

Leitura de insumos, fornecedores e conversões na validação de custo é em lote.
Mínimos atualizam exclusivamente metadata e updated_at num `bulk_update` atômico;
a identidade e a unidade do insumo não mudam. Não há migração. Custos continuam
passando pelo escritor e validações canônicas do Buyman, por entidade.
Os dois POSTs agora expõem o Server-Timing canônico.

## Verificação

- Backend: testes dos contratos existentes e de rollback depois de escrita, com
  toda a transação revertida. Guardas com 1 e 12 insumos medem as leituras de
  validação e a gravação de mínimos, reprovando crescimento de consultas.
- Frontend: componentes exercitam colagem TSV, decimal pt-BR, erro por insumo,
  zero de mínimo e Desfazer. A suíte do Compras passou: 18 arquivos, 188 testes.
- Typecheck e lint do Compras passaram. Ruff dos arquivos Python passou.
- Navegador Chromium, build de produção e backend hermético: duas rotas, claro
  e escuro. O teste exige a classe correta do tema e nenhuma resposta 4xx/5xx.
  Capturas abertas pelo agente, não apenas gravadas.

## Desempenho medido

Amostra hermética SQLite com 1 e 12 insumos, mesmo processo de teste:

| Caminho | Antes (1 / 12) | Depois (1 / 12) |
|---|---:|---:|
| Validação de custo com conversão, sem escritor/projeção | 5 / 38 consultas | 5 / 5 consultas |
| Mínimos, sem projeção | 5 / 38 consultas | 4 / 4 consultas |
| POST custos completo | 50 / 238 consultas | 50 / 216 consultas |
| POST mínimos completo | 33 / 66 consultas | 32 / 32 consultas |

Server-Timing `projection` de 12 insumos: custos 883,97 ms antes e 63,05 ms depois;
mínimos 31,76 ms antes e 707,45 ms depois. São amostras individuais numa máquina
com builds concorrentes, com forte variação de CPU. Não sustentam promessa de
latência; a redução determinística é de consultas. Valores `db`: custos 33,31 ms
antes e 9,66 ms depois; mínimos 3,81 ms antes e 5,34 ms depois. Baseline dos POSTs
medido com a mesma instrumentação ServerTimingMixin, aplicada sem mudar o serviço.
Os guardas falharam contra o serviço original e passaram com a mudança.
Suite backend final: **28 passed in 100.84s**. A saída relevante está em
`../EVIDENCE/ONDA4-3-tabelao-insumos/performance.txt`.

## D1 a D12

- D1: preservadas tabelas outline, cartão interno soft sem nova borda, selos sem variant.
- D2: nenhuma área de cabeçalho/rodapé destacada adicionada.
- D3: Desfazer neutral/outline do conjunto mínimo, centrado, sem esticar.
- D4: grade usa a largura disponível da tabela existente.
- D5: ações irmãs mantêm altura canônica igual.
- D6: rótulo completo Desfazer, acompanhado do ícone; campos têm aria por insumo.
- D7: campos mantêm a altura padrão dos botões.
- D8: erro vermelho junto ao insumo, corrigível no campo ou removido com Desfazer.
- D9: rascunho inline com salvar em lote e Limpar, sem destruição de cadastro.
- D10: copy em português, sem travessão, vocabulário da casa.
- D11: NuxtInput, NuxtButton, OperatorTable e useGridEdit canônicos.
- D12: oito capturas antes/depois, claro/escuro, abertas e conferidas.

## Evidência visual

Arquivos em `../EVIDENCE/ONDA4-3-tabelao-insumos/`:

- `before-costs-light.png` e `before-costs-dark.png`.
- `after-costs-light.png` e `after-costs-dark.png`.
- `before-materials-light.png` e `before-materials-dark.png`.
- `after-materials-light.png` e `after-materials-dark.png`.

O spec próprio corrige a chave do tema da evidência: `purchase-nuxt-color-mode`.
Sem a chave certa, emular o esquema escuro não muda a preferência explícita clara.

## Limites

A colagem é de uma coluna por operação, limitada às linhas visíveis; não é importação
por SKU. Import/export é a frente 5. Custos e mínimos são lotes independentes,
conforme os dois endpoints existentes. As escritas e validações de domínio por custo
continuam crescendo com a quantidade de entidades; o guarda de N+1 cobre a leitura
prévia, inclusive conversões. Não foi usado banco vivo nem regenerado baseline.
