/**
 * Quem pode ASSINAR uma autorização de gerente.
 *
 * O diálogo compartilhado (`OperatorManagerAuth`) precisa só disto: um nome para
 * mostrar na lista e o `username` que o servidor resolve. Ele NÃO precisa
 * conhecer a projeção do PDV.
 *
 * Fica aqui, e não em `pos-nuxt/app/types/pos.ts`, porque era esse import que
 * prendia o diálogo ao PDV: `defineProps<…>` resolve tipos em tempo de
 * COMPILAÇÃO, então um tipo que não resolve não gera prop nenhuma e o
 * componente renderiza vazio — sem erro de runtime, o que torna o sintoma
 * difícil de ler.
 *
 * `POSManagerProjection` do PDV continua existindo e descreve outra coisa: o
 * contrato de fio daquela projeção. Os dois casam por tipagem ESTRUTURAL, sem
 * um importar o outro.
 */
export interface ManagerOption {
  username: string;
  name: string;
}
