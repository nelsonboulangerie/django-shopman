# C07: proteção de saída dos motivos e notas

Base fb2e80fc9. Motivo local era apagado ao reabrir após fechamento sem decisão.
No componente, testemunha válida:3 falhas/11 sucessos. A primeira preparação
falhou por window.confirm ausente no happy-dom; log separado. Browser anterior
falhou esperando beforeunload; não é prova isolada de cada gesto.

Detalhe: fechar via shell/Voltar pede descarte só se há texto/código, bloqueia
fechamento ocupado, emite dirty para a guarda da página. Nota/comentário/motivo
agora protegem reload, usando o padrão já existente no catálogo. Fechar pelo
pai depois de sucesso conhecido continua sem confirmação redundante.
Fila: editor de recusa recebe a mesma proteção, além de bloquear clique ocupado.
Antes fila: nenhuma confirmação (esperada1, observada0). Depois: duas jornadas
reais Chromium→Nitro→Django/PG passaram8,8s, incluindo teclado Escape/Enter,
recarga recusada, texto igual e status canônico inalterado.

Rodada do detalhe:303 Vitest3,88s, typecheck/build e27 integrações51,5s.
Depois da extensão à fila: typecheck/build e duas integrações direcionadas;
rodada final Vitest em reject-discard-unit.txt. As27 integrações antecedem
a extensão à fila; não reportar como28 em uma rodada.

R=0 nos cenários ensaiados; confirmação explícita acrescenta um gesto apenas
a saída que descartaria texto. Não mede compreensão humana/leitor de tela.
Sem persistência pós-reload, DDL, envio de cancelamento novo ou efeito externo.
Rollback de código apenas; conserva recibos, livros e guardas do backend.
