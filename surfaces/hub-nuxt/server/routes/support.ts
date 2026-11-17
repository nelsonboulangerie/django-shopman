// `/support` é o link que a equipe guarda. O hub é one-page; o painel abre
// por `?support=1`. Quando o hub ganhar pages/, esta rota vira a página.
export default defineEventHandler((event) => {
  return sendRedirect(event, "/?support=1", 302);
});
