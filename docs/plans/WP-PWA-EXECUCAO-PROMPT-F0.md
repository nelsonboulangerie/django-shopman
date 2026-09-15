# Prompt de execução — WP-PWA fase F0 (Storefront)

> Estado atual (2026-09-15): **arquivado; não copiar nem executar.** A F0 foi
> entregue e publicada por [#668](https://github.com/nelsonboulangerie/django-shopman/pull/668),
> com ajustes em [#691](https://github.com/nelsonboulangerie/django-shopman/pull/691),
> [#693](https://github.com/nelsonboulangerie/django-shopman/pull/693) e
> [#694](https://github.com/nelsonboulangerie/django-shopman/pull/694). Falta a
> validação no iPhone físico da barra inferior, pull-to-refresh e teclado; essa
> prova pendente não desfaz a publicação. F1–F3 continuam futuras e exigem um
> prompt novo, autorizado e baseado no estado corrente de `main`.
>
> O bloco abaixo é preservado somente como registro do prompt enviado para a F0;
> placeholders, dependências e critérios não devem ser reutilizados como instrução
> atual.

```text
Execute a fase F0 (Storefront) de docs/plans/WP-PWA-EXECUCAO.md no repositório
django-shopman, base main.

Leia por inteiro, nesta ordem, antes de escrever: CLAUDE.md;
docs/plans/WP-PWA-EXECUCAO.md (seções 0, 2, 3, 7, 8 e Anexo A);
docs/plans/WP-PWA-CONFORMIDADE.md. Os arquivos de código citados no brief você
lê quando a tarefa chegar neles.

Escopo: somente F0.1–F0.9. Nada de operator-kit, PDV, backstage ou Web Push. O que
parecer exigir outra fase, registre e siga.

Materiais do dono (Anexo A):
- símbolo da marca (SVG): <<caminho>>
- logotipo completo (SVG): <<caminho>>
- theme_color <<#7C3A40>> · background_color <<#FCF7EE>>
- name <<Nelson Boulangerie>> · short_name <<Nelson>> · description <<…>>
  (gravados no Admin, em Loja; se faltarem, use o fallback do build e registre)
- copy da tela offline e do convite de instalação: <<texto>> ou "voz da casa"
Sem o SVG do símbolo, pare na F0.6 e entregue o PR parcial com a pendência nomeada.

Duas regras desta fase que mais se violam: o service worker não guarda nada de
/api/, /events/, /admin/ nem navegação (só /img/products/** e /fonts/**); e a CSP do
Storefront não ganha diretiva nova.

Entrega: PR "feat(storefront): PWA F0 — instalável, casco offline, atualização
controlada", no formato da seção 7 do brief, com os gates do storefront rodados em
node 22 e o gate make pwa app=storefront que você cria na F0.8. Prova que não tem,
diz que não tem.
```
