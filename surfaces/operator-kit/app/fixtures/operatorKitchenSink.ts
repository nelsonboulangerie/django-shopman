export const kitchenSinkNavigation = [
  {
    label: "Dashboard",
    icon: "i-lucide-chart-no-axes-combined",
    to: "#dashboard-exercises",
    badge: 3,
  },
  {
    label: "Laboratório",
    icon: "i-lucide-flask-conical",
    to: "#visual-exercises",
  },
  { label: "Fundamentos", icon: "i-lucide-swatch-book", to: "#foundations" },
  { label: "Anatomias", icon: "i-lucide-panels-top-left", to: "#anatomies" },
  { label: "Componentes", icon: "i-lucide-box", to: "#components" },
  { label: "Receitas", icon: "i-lucide-notebook-tabs", to: "#recipes" },
  { label: "Estados", icon: "i-lucide-circle-alert", to: "#states" },
  { label: "Matriz", icon: "i-lucide-table-properties", to: "#matrix" },
  { label: "Exceções", icon: "i-lucide-shield-alert", to: "#exceptions" },
] as const;

export const kitchenSinkMetrics = [
  {
    title: "Pedidos abertos",
    description: "12 aguardam uma decisão",
    value: "24",
  },
  {
    title: "Tempo médio",
    description: "Da confirmação à saída",
    value: "18 min",
  },
  {
    title: "Valor do dia",
    description: "Vendas confirmadas",
    value: "R$ 8.420,00",
  },
] as const;

export const kitchenSinkRows = [
  {
    pedido: "NB-1042",
    cliente: "Ana Ferreira",
    estado: "Pronto",
    total: "R$ 148,90",
  },
  {
    pedido: "NB-1043",
    cliente:
      "Nome extremo que prova a segunda linha deliberada sem diminuir a tipografia",
    estado: "Em preparo",
    total: "R$ 9.999.999,99",
  },
] as const;

export const kitchenSinkQueue = [
  {
    ref: "NB-1047",
    title: "Retirada atrasada",
    detail: "A pessoa já chegou",
    tone: "error",
  },
  {
    ref: "NB-1048",
    title: "Confirmar substituição",
    detail: "Falta um item",
    tone: "warning",
  },
  {
    ref: "NB-1049",
    title: "Separar encomenda",
    detail: "Saída às 15h30",
    tone: "info",
  },
] as const;

export const kitchenSinkSteps = [
  { title: "Identificar", description: "Pessoa e contexto" },
  { title: "Revisar", description: "Valores e consequência" },
  { title: "Confirmar", description: "Gesto final explícito" },
] as const;

export const kitchenSinkNeeds = [
  {
    apps: "Central, B.I.",
    need: "Dashboard, métricas e atenção",
    solution: "OperatorOfficeShell + OperatorPage + NuxtPageCard",
  },
  {
    apps: "PDV, Gestor, Compras",
    need: "Lista e detalhe simultâneos",
    solution: "OperatorSplitter; no celular, sequência ou sheet",
  },
  {
    apps: "Cozinha, Produção, PDV",
    need: "Fluxo contínuo de chão",
    solution: "OperatorOperationalShell + barra de ação",
  },
  {
    apps: "Marketing, Produção, Compras",
    need: "Formulário e revisão contextual",
    solution: "NuxtForm + OperatorPage aside",
  },
  {
    apps: "Todos",
    need: "Busca, filtro e período",
    solution: "OperatorPageHeader + DashboardToolbar + controles do kit",
  },
  {
    apps: "Todos",
    need: "Loading, vazio, erro e recuperação",
    solution: "NuxtSkeleton, NuxtEmpty e NuxtAlert por composição",
  },
  {
    apps: "Gestor, Cozinha, Produção",
    need: "Fila orientada a exceção",
    solution: "Receita queue com atenção antes do restante",
  },
  {
    apps: "B.I., Marketing",
    need: "Leitura analítica e comparação",
    solution:
      "Dashboard responsivo + tabela; visualização de domínio preservada",
  },
] as const;

export const kitchenSinkExceptions = [
  {
    app: "PDV",
    useCase: "Segundo monitor público",
    limitation: "Tem audiência e jornada distintas da pessoa operadora",
  },
  {
    app: "Cozinha",
    useCase: "Painel público de retirada",
    limitation: "Não pode expor sessão, navegação nem ações internas",
  },
  {
    app: "Produção",
    useCase: "Quadro distante",
    limitation:
      "Leitura a metros de distância e sinal audiovisual exigem modo próprio",
  },
  {
    app: "PDV e Produção",
    useCase: "Impressão e etiqueta",
    limitation: "Geometria é definida pelo meio físico, não pelo viewport",
  },
  {
    app: "Compras e PDV",
    useCase: "Câmera, scanner e periféricos",
    limitation:
      "A API do dispositivo muda o comportamento, não a linguagem visual",
  },
] as const;

export const kitchenSinkStateOptions = [
  { label: "Normal", value: "normal" },
  { label: "Carregando", value: "loading" },
  { label: "Vazio", value: "empty" },
  { label: "Erro", value: "error" },
  { label: "Offline", value: "offline" },
  { label: "Reconectando", value: "reconnecting" },
  { label: "Rede lenta", value: "slow-network" },
  { label: "Somente leitura", value: "readonly" },
  { label: "Sem permissão", value: "forbidden" },
  { label: "Sucesso", value: "success" },
  { label: "Conteúdo extremo", value: "extreme-content" },
] as const;

export type KitchenSinkState =
  (typeof kitchenSinkStateOptions)[number]["value"];
