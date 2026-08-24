// Guarda compartilhada dos atalhos GLOBAIS do PDV (numpad do carrinho, numpad
// de tender, F2/F3/F4/F6/Esc/Enter): a página continua montada por baixo do
// overlay de identificação e de qualquer diálogo — sem esta guarda, passar o
// crachá na tela travada (token com dígitos) ou digitar o PIN do gerente com um
// diálogo aberto reescrevia quantidades da linha ativa e salvava no servidor.
//
// A detecção é pelo DOM, de propósito: diálogo aberto é o conteúdo do reka-ui,
// que marca `role="dialog"`/`role="alertdialog"` com `data-state="open"`;
// terminal travado é o overlay do kit, marcado com `data-operator-lock`. Ler o
// DOM evita que cada diálogo novo tenha de lembrar de se registrar num estado
// global: o que abre por cima bloqueia, sem cadastro.
export function globalKeysBlocked(): boolean {
  if (typeof document === "undefined") return true;
  return Boolean(
    document.querySelector(
      '[data-operator-lock], [role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]',
    ),
  );
}
