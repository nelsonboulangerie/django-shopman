// Configuração do Gestor sobre a do operator-kit (as camadas se fundem). Sem tema
// aqui: cor, densidade e variantes são do kit.
export default defineAppConfig({
  operatorHeader: {
    // O posto deste dispositivo não vira selo no cabeçalho: o título já diz a visão
    // ("Saída") e o posto está no menu do operador. Ver OperatorPageHeader.
    workstationBadge: false,
  },
});
