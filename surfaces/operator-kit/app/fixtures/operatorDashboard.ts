// Turno fixo: não usa relógio, dados vivos, imagens externas ou aleatoriedade.
export const dashboardTrend = [
  { index: 0, label: "09h", orders: 12 },
  { index: 1, label: "10h", orders: 18 },
  { index: 2, label: "11h", orders: 25 },
  { index: 3, label: "12h", orders: 31 },
  { index: 4, label: "13h", orders: 23 },
  { index: 5, label: "14h", orders: 16 },
];
export const dashboardTeam = [
  { name: "Ana Ferreira", role: "Caixa", initials: "AF", status: "Ativa" },
  { name: "João Santos", role: "Produção", initials: "JS", status: "Ativo" },
  {
    name: "Maria Oliveira",
    role: "Retirada",
    initials: "MO",
    status: "Em pausa",
  },
];
export const dashboardTabs = [
  {
    label: "Resumo",
    value: "overview",
    slot: "overview",
    icon: "i-lucide-chart-no-axes-combined",
  },
  {
    label: "Fila",
    value: "queue",
    slot: "queue",
    icon: "i-lucide-list-checks",
    badge: 3,
  },
  {
    label: "Equipe",
    value: "team",
    slot: "team",
    icon: "i-lucide-users",
    badge: 3,
  },
];
export const dashboardSegments = [
  { label: "Prontos", value: 18, color: "success" as const },
  { label: "Em preparo", value: 4, color: "info" as const },
  { label: "Aguardando", value: 2, color: "warning" as const },
];
