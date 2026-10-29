# Triagem de trabalho dormente em 29/10/2026

Base da comparação: `origin/main` em `7288b4462`. Nenhuma worktree de outra sessão foi alterada ou apagada.

## Resultado

| Frente | Evidência | Destino |
|---|---|---|
| `fix/a4-1b-admin-troca-de-contato`, 199 arquivos staged | Árvore do índice `d1042bb25aedd0c1a06fe452e9f0b352a92693d4` é exatamente a do commit `4d4826883ea9b6187903f0c6df58d853b53e297f`, ancestral de main. Sem alteração unstaged. | Conteúdo já entregue. O índice antigo diante de um HEAD diferente produz falso trabalho novo; não aplicar esse delta no main. |
| `fix/a8-get-detalhe-pedido-nao-pergunta-gateway`, 178 arquivos staged | Árvore do índice `a5c928c6edcffa71bdf2ba35632cb1c2d6ae15a8` é exatamente a do commit `4216105ea1014a7ba25a47b38628e50016ff3576`, ancestral de main. Sem alteração unstaged. | Conteúdo já entregue; preservar worktree original. |
| `claude/google-merchant-center-ratings-f47010`, três arquivos locais de alertas | Nenhum commit fora de main. `alertActions.ts` já tem a alteração local no main. Configuração atual inclui `max-sm:basis-full` além do empilhamento. PR #2021 mergeada. | Alteração antiga superada pela implementação entregue. Não reaplicar. |
| `claude/despacho-conferencia-de-volumes-a6730` | Feature entregue no commit `e51c420fe` via #1737. `volume_check.py` idêntico. Arquivos do último ajuste idênticos, exceto mock visual que ganhou tratamento posterior de catálogo. | Commits locais reescritos geram falso delta; implementação preservada. |
| `claude/whatsapp-rastreio-entregador` | Feature entregue no commit `9c90bd117` via #1690. Adapter atual preserva a variante de rastreio e acrescenta confirmação de encomenda e correção de referência ADR. | Não reintroduzir versão antiga. |

Os grandes índices staged são código e documentação históricos, não saída gerada nem centenas de mudanças inéditas. A evidência de árvore completa é mais forte que contagem de arquivos ou comparação textual isolada.

## Pendências encaminhadas à coordenação

O checkout principal contém seis arquivos alterados de edição em grade (kit e Catálogo do Gestor), com testes de colagem de preço e preservação de conflitos. Esta frente precisa de identificação de autoria, recuperação isolada e validação própria. Não foi misturada com a triagem histórica. Os sete arquivos não rastreados `docs/coordination/ORDERS/next*.md` também permanecem preservados no principal.

Não foi feito reset, limpeza, exclusão de branch ou alteração das worktrees examinadas. A limpeza visual dos índices antigos pode ocorrer depois, com seu dono; ela não é requisito para recuperar código porque as árvores já são ancestrais de main.

## Reprodução

- `git -C <worktree> diff --cached --stat` distingue índice de alterações unstaged.
- `git -C <worktree> write-tree` identifica a árvore do índice sem trocar arquivos.
- `git log --all --format="%H %T %s"` permite localizar a mesma árvore no histórico.
- `git merge-base --is-ancestor <commit> origin/main` confirma a entrega.
- `gh pr view 1737`, `gh pr view 1690` e `gh pr list --state all --head claude/aviso-botoes-empilhados` confirmam os PRs correspondentes.
