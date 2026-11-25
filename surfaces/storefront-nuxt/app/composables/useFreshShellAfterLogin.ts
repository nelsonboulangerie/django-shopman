/**
 * Quem sai do login chega à próxima página com o shell da pessoa logada (#3572).
 *
 * O shell (`shopman-shell`) carregado antes do login é o do anônimo: sem nome, com
 * "Entrar" no rodapé e com a versão padrão de todo experimento. O `app.vue` relia o
 * shell num `watch` da rota, que só dispara DEPOIS de a página de destino montar: a
 * primeira tela depois do login saía com o shell do anônimo (versão A para quem é B)
 * e só trocava quando a releitura voltava.
 *
 * Aqui a releitura vira guarda do roteador: ao sair de uma rota de login para uma
 * que não é, a navegação espera o shell novo antes de resolver, e a página de destino
 * já monta lendo a versão que o servidor decidiu para quem entrou (D1: quem decide
 * continua sendo o servidor; o cliente só relê). Falha da releitura não prende a
 * cliente no login: a navegação segue com o que houver.
 */
export function useFreshShellAfterLogin (
  isAuthRoute: (path: string) => boolean,
  refreshShell: () => Promise<unknown>
) {
  const removeGuard = useRouter().beforeResolve(async (to, from) => {
    if (!isAuthRoute(from.path) || isAuthRoute(to.path)) return
    await refreshShell().catch(() => null)
  })
  if (getCurrentScope()) onScopeDispose(removeGuard)
}
