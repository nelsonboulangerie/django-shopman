# Prompt de execução — WP-PWA fase F0 (Storefront)

> Copiar o bloco abaixo para o agente externo. Preencher os `<<…>>` com os materiais
> do Anexo A antes de enviar. Uma fase por sessão, um PR por fase. As regras da casa
> não estão repetidas aqui de propósito: moram em `CLAUDE.md` e no brief.

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
