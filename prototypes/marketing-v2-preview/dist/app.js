const pages = {
  today: ["Operação", "Hoje"],
  campaigns: ["Campanhas", "Nova campanha"],
  offers: ["Comercial", "Ofertas"],
  platforms: ["Configuração", "Plataformas"],
};

const destinationCompositions = {
  "instagram-feed": {
    title: "Instagram · @nelson · Feed",
    ratioName: "Feed retrato · 4:5",
    pixels: "1080 × 1350",
    ratioClass: "ratio-feed",
    formats: ["Imagem", "Vídeo"],
    editorScope: "Só para Instagram · Feed",
    editorScopeNote: "O Feed recebe uma composição própria; opções de Story, Google ou WhatsApp não aparecem aqui.",
    textLabel: "Legenda do Feed",
    formatLabel: "Tipo de mídia no Feed",
    secondaryLabel: "Ajuste vertical da imagem",
    secondaryType: "range",
    secondaryValue: "50",
    rule: "Publicação orgânica: a legenda pode orientar a ação, mas a API não oferece um botão CTA genérico neste formato.",
    headline: "",
    body: "A primavera chegou à Nelson. Nesta semana, o Hibisco ganha 15% de desconto. #primavera",
    cta: "",
    badge: "",
    coupon: "",
    note: "A mídia usa o canvas 4:5 escolhido e preserva o foco. O Instagram pode adaptar elementos de interface; publicação orgânica não ganha um botão CTA genérico.",
  },
  "instagram-story": {
    title: "Instagram · @nelson · Story",
    ratioName: "Story · 9:16",
    pixels: "1080 × 1920",
    ratioClass: "ratio-story",
    formats: ["Imagem", "Vídeo"],
    editorScope: "Só para Instagram · Story",
    editorScopeNote: "A composição vertical e a área segura existem somente para este Story.",
    textLabel: "Texto da composição do Story",
    formatLabel: "Conteúdo do Story",
    secondaryLabel: "Ajuste vertical da imagem",
    secondaryType: "range",
    secondaryValue: "50",
    rule: "A prévia protege a área editorial; controles, stickers e recursos disponíveis na conta continuam sendo responsabilidade do Instagram.",
    headline: "Primavera na Nelson",
    body: "15% OFF no Hibisco nesta semana.",
    cta: "",
    badge: "15% OFF",
    coupon: "",
    note: "O canvas é 9:16 e a guia marca a área editorial protegida de textos e controles. A interface final do Story pertence ao Instagram.",
  },
  "facebook-feed": {
    title: "Facebook · Página Centro · Feed",
    ratioName: "Feed retrato · 4:5",
    pixels: "1080 × 1350",
    ratioClass: "ratio-facebook",
    formats: ["Imagem + link", "Texto", "Vídeo"],
    editorScope: "Só para Facebook · Página Centro",
    editorScopeNote: "A composição e o link pertencem a este post do Facebook.",
    textLabel: "Texto do post",
    formatLabel: "Composição do post",
    secondaryLabel: "Link do post",
    secondaryType: "url",
    secondaryValue: "https://nelson.example/hibisco",
    rule: "O link integra o conteúdo do post. Ele não é apresentado como se fosse um CTA arbitrário da API orgânica.",
    headline: "Hibisco Primavera",
    body: "A primavera chegou à Nelson. Aproveite 15% de desconto nesta semana.",
    cta: "Abrir link",
    badge: "15% OFF",
    coupon: "",
    note: "O arquivo mantém 4:5, mas o Facebook pode reformatar o card por dispositivo. “Abrir link” representa o link do post, não um CTA arbitrário da API orgânica.",
  },
  google: {
    title: "Google · Loja Jardins",
    ratioName: "Google Post · 4:3 editorial",
    pixels: "1200 × 900",
    ratioClass: "ratio-google",
    formats: [],
    headline: "15% OFF no Hibisco",
    body: "A primavera chegou à Nelson. Aproveite 15% de desconto no Hibisco nesta semana.",
    cta: "Ver oferta",
    badge: "15% OFF",
    coupon: "PRIMAVERA15",
    note: "O arquivo e o corte editorial respeitam 4:3; o Google pode adaptar o card conforme a superfície onde ele aparecer.",
  },
  whatsapp: {
    title: "WhatsApp · Conta Principal",
    ratioName: "Cabeçalho do template · 1,91:1",
    pixels: "1125 × 600",
    ratioClass: "ratio-whatsapp",
    formats: ["Template oferta_v3"],
    editorScope: "Só para WhatsApp · Conta Principal",
    editorScopeNote: "O template foi aprovado previamente e determina texto, variáveis e botões permitidos.",
    textLabel: "Texto resultante do template",
    formatLabel: "Template aprovado",
    secondaryLabel: "Variável {{cupom}}",
    secondaryType: "text",
    secondaryValue: "PRIMAVERA15",
    rule: "Não há tipo de publicação genérico: o operador apenas escolhe um template aprovado e preenche as variáveis autorizadas.",
    headline: "Oferta da semana",
    body: "Olá, {{primeiro_nome}}! O Hibisco está com 15% de desconto.",
    cta: "Comprar agora",
    badge: "15% OFF",
    coupon: "PRIMAVERA15",
    note: "A proporção acompanha o cabeçalho de mídia do template. Texto, variáveis e botão são definidos pelo template aprovado; o operador apenas preenche o que ele permite.",
  },
};

const connectorDefinitions = {
  meta: {
    name: "Meta",
    title: "Autorizar Instagram e Facebook",
    description: "A Meta devolve as contas profissionais e Pages que esta pessoa pode administrar.",
    icon: '<span class="provider-icons"><span class="platform-icon instagram">IG</span><span class="platform-icon facebook">f</span></span>',
    permissions: [
      "Ler as Pages e contas profissionais disponíveis",
      "Publicar somente nas contas escolhidas",
      "Consultar permissões e status da publicação",
    ],
    resourceTitle: "Quais contas Meta o Marketing poderá usar?",
    resourceDescription: "Instagram e Facebook compartilham a autorização, mas continuam como destinos independentes.",
    resources: [
      { id: "ig-nelson", name: "Instagram · @nelson", detail: "Conta profissional · Feed e Story", status: "Pronta", checked: true },
      { id: "fb-centro", name: "Facebook · Página Centro", detail: "Page · Feed", status: "Pronta", checked: true },
      { id: "fb-jardins", name: "Facebook · Página Jardins", detail: "Page encontrada nesta conta", status: "Nova", checked: false },
    ],
    verification: "As contas escolhidas têm as permissões mínimas para publicação.",
  },
  google: {
    name: "Google Business Profile",
    title: "Autorizar Google Business Profile",
    description: "A conta Google será usada para descobrir os perfis e lojas que ela administra.",
    icon: '<span class="platform-icon google">G</span>',
    permissions: [
      "Listar as locations administradas pela conta",
      "Criar e acompanhar publicações nas lojas escolhidas",
      "Ler o estado necessário para validar cada publicação",
    ],
    resourceTitle: "Quais lojas o Marketing poderá usar?",
    resourceDescription: "Cada location vira um destino separado e pode ter sua própria composição.",
    resources: [
      { id: "google-jardins", name: "Google · Loja Jardins", detail: "Location verificada · já conectada", status: "Pronta", checked: true },
      { id: "google-centro", name: "Google · Loja Centro", detail: "Location encontrada nesta conta", status: "Nova", checked: true },
      { id: "google-lago", name: "Google · Quiosque do Lago", detail: "Sem permissão para publicar", status: "Bloqueada", checked: false, disabled: true },
    ],
    verification: "Duas locations estão aptas; a location bloqueada não será adicionada.",
  },
  whatsapp: {
    name: "WhatsApp via ManyChat",
    title: "Validar conta ManyChat",
    description: "O conector usa um token da API ManyChat e mantém o texto oficial dentro do fluxo aprovado.",
    icon: '<span class="platform-icon whatsapp">W</span>',
    permissions: [
      "Consultar fluxos ativos da conta",
      "Resolver somente contatos com consentimento",
      "Executar ensaio antes da liberação geral",
    ],
    resourceTitle: "Qual configuração do WhatsApp ficará ativa?",
    resourceDescription: "Escolha a conta e o fluxo que será revalidado antes de cada campanha.",
    resources: [
      { id: "whatsapp-main", name: "WhatsApp · Conta Principal", detail: "ManyChat · número comercial verificado", status: "Atenção", checked: true },
    ],
    verification: "O token será guardado no cofre; o fluxo escolhido será verificado ao salvar.",
    needsToken: true,
    needsTemplate: true,
  },
};

const pageFromHash = window.location.hash.replace("#", "");
let currentPage = Object.hasOwn(pages, pageFromHash) ? pageFromHash : "campaigns";
let currentStep = 3;
let currentDestination = "google";
let currentGoogleType = "offer";
let currentConnector = null;
let connectionStep = 1;
let connectionMode = "add";
let toastTimer;

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

function showToast(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 2400);
}

function openPage(page) {
  currentPage = page;
  $$(".nav-item").forEach((button) => button.classList.toggle("active", button.dataset.page === page));
  $$(".page-view").forEach((view) => { view.hidden = view.id !== `page-${page}`; });
  $("#pageEyebrow").textContent = pages[page][0];
  $("#pageTitle").textContent = pages[page][1];
  $(".save-state").hidden = page !== "campaigns";
  if (window.location.hash !== `#${page}`) history.replaceState(null, "", `#${page}`);
}

function selectConnector(connectorRef) {
  currentConnector = connectorRef;
  $$('[data-connector-choice]').forEach((button) => {
    const selected = button.dataset.connectorChoice === connectorRef;
    button.setAttribute("aria-checked", String(selected));
  });
  $("#connectionNextButton").disabled = false;
}

function resourceMarkup(resource) {
  return `
    <label class="resource-option">
      <input type="checkbox" value="${resource.id}" ${resource.checked ? "checked" : ""} ${resource.disabled ? "disabled" : ""} />
      <span><strong>${resource.name}</strong><small>${resource.detail}</small></span>
      <em>${resource.status}</em>
    </label>`;
}

function renderAuthorization(connector) {
  $("#authorizationIcon").outerHTML = `<span id="authorizationIcon">${connector.icon}</span>`;
  $("#authorizationTitle").textContent = connector.title;
  $("#authorizationDescription").textContent = connector.description;
  $("#authorizationPermissions").innerHTML = connector.permissions.map((permission) => `<li>${permission}</li>`).join("");
  $("#authorizationFields").innerHTML = connector.needsToken
    ? `<label class="token-field"><span>Token da API ManyChat</span><input type="password" value="preview-token-not-real" aria-describedby="tokenHelp" /><small id="tokenHelp">Não use um token real neste ambiente de demonstração.</small></label>`
    : "";
}

function renderResources(connector) {
  $("#resourceTitle").textContent = connector.resourceTitle;
  $("#resourceDescription").textContent = connector.resourceDescription;
  const template = connector.needsTemplate
    ? `<label class="template-choice"><span>Fluxo aprovado para campanhas</span><select><option>oferta_v3 · Oferta com cupom</option><option>novidade_v2 · Novidade da semana</option><option>Sem fluxo · somente janela de 24 horas</option></select></label>`
    : "";
  $("#resourcePicker").innerHTML = connector.resources.map(resourceMarkup).join("") + template;
  $("#verificationSummary").textContent = connector.verification;
}

function updateConnectionWizard() {
  $$('[data-connection-step-panel]').forEach((panel) => {
    panel.hidden = Number(panel.dataset.connectionStepPanel) !== connectionStep;
  });
  $$('[data-connection-step-indicator]').forEach((indicator) => {
    const step = Number(indicator.dataset.connectionStepIndicator);
    indicator.classList.toggle("active", step === connectionStep);
    indicator.classList.toggle("done", step < connectionStep);
  });

  $("#connectionBackButton").textContent = connectionStep === 1 ? "Cancelar" : "Voltar";
  $("#connectionNextButton").disabled = connectionStep === 1 && !currentConnector;
  $("#connectionNextButton").textContent = connectionStep === 1
    ? "Continuar"
    : connectionStep === 2
      ? (currentConnector === "whatsapp" ? "Validar token" : "Simular autorização")
      : (connectionMode === "manage" ? "Salvar configuração" : "Adicionar conexão");
  $("#connectionStepHint").textContent = [
    "Você poderá adicionar outras contas depois.",
    "A autorização real acontecerá no provedor.",
    "Nada é publicado durante a configuração.",
  ][connectionStep - 1];

  if (currentConnector && connectionStep === 2) renderAuthorization(connectorDefinitions[currentConnector]);
  if (currentConnector && connectionStep === 3) renderResources(connectorDefinitions[currentConnector]);
}

function openConnectionWizard(connectorRef = null, mode = "add") {
  currentConnector = connectorRef;
  connectionMode = mode;
  connectionStep = connectorRef && mode === "manage" ? 3 : connectorRef ? 2 : 1;
  $("#connectionWizardEyebrow").textContent = mode === "manage" ? "Configuração existente" : "Nova conexão";
  $("#connectionWizardTitle").textContent = mode === "manage"
    ? `Gerenciar ${connectorDefinitions[connectorRef].name}`
    : "Adicionar plataforma";
  $$('[data-connector-choice]').forEach((button) => {
    button.setAttribute("aria-checked", String(button.dataset.connectorChoice === connectorRef));
  });
  updateConnectionWizard();
  $("#connectionWizard").showModal();
}

function closeConnectionWizard() {
  $("#connectionWizard").close();
}

function openStep(step) {
  currentStep = Math.max(1, Math.min(5, step));
  $$(".step-panel").forEach((panel) => {
    const active = Number(panel.dataset.stepPanel) === currentStep;
    panel.hidden = !active;
    panel.classList.toggle("active", active);
  });
  $$(".step").forEach((button) => {
    const number = Number(button.dataset.step);
    button.classList.toggle("active", number === currentStep);
    button.classList.toggle("done", number < currentStep);
  });
  $("#backButton").disabled = currentStep === 1;
  const selectedCount = getSelectedDestinations().length;
  $("#nextButton").textContent = currentStep === 5
    ? `Agendar ${selectedCount} ${selectedCount === 1 ? "publicação" : "publicações"}`
    : ["Escolher destinos", "Criar conteúdo", "Continuar para público", "Revisar campanha"][currentStep - 1];
  const hints = [
    "A oferta comercial existe uma vez e alimenta os destinos.",
    "Cada conta e formato vira uma consequência independente.",
    "Os limites e campos pertencem a cada destino.",
    "Público só aparece onde a plataforma realmente permite.",
    "Falhas serão acompanhadas e repetidas por destino.",
  ];
  $("#stepHint").textContent = hints[currentStep - 1];
}

function getSelectedDestinations() {
  return $$('.destination-check input[data-destination]:checked:not(:disabled)').map((input) => input.dataset.destination);
}

function configureDestinationEditor(destination) {
  $("#editorScope").textContent = destination.editorScope;
  $("#editorScopeNote").textContent = destination.editorScopeNote;
  $("#destinationTextLabel").textContent = destination.textLabel;
  $("#destinationText").value = destination.body;
  $("#destinationFormatLabel").textContent = destination.formatLabel;
  $("#destinationFormat").innerHTML = destination.formats.map((format) => `<option>${format}</option>`).join("");
  $("#destinationSecondaryLabel").textContent = destination.secondaryLabel;
  const input = $("#destinationSecondaryInput");
  input.type = destination.secondaryType;
  input.value = destination.secondaryValue;
  if (destination.secondaryType === "range") {
    input.min = "0";
    input.max = "100";
  } else {
    input.removeAttribute("min");
    input.removeAttribute("max");
  }
  $("#destinationRule").textContent = destination.rule;
}

function updatePreview(destinationRef) {
  currentDestination = destinationRef;
  const destination = destinationCompositions[destinationRef];
  $$(".composition-tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.destination === destinationRef));
  $("#previewTitle").textContent = destination.title;
  $("#ratioName").textContent = destination.ratioName;
  $("#ratioPixels").textContent = destination.pixels;
  $("#socialHeadline").textContent = destination.headline;
  $("#socialHeadline").hidden = !destination.headline;
  $("#socialBody").textContent = destination.body;
  $("#previewCta").textContent = destination.cta;
  $("#previewCta").hidden = !destination.cta;
  $("#offerBadge").textContent = destination.badge;
  $("#offerBadge").hidden = !destination.badge;
  $("#couponLine").hidden = !destination.coupon;
  if (destination.coupon) $("#couponLine strong").textContent = destination.coupon;
  $("#previewNote").innerHTML = `<strong>${destinationRef === "google" ? "Proporção controlada, renderização variável." : "Prévia por destino."}</strong> ${destination.note}`;
  $("#mediaFrame").className = `media-frame ${destination.ratioClass}`;
  $("#socialPreview").className = `social-preview ${destinationRef === "google" ? "google-preview" : ""}`;

  const isGoogle = destinationRef === "google";
  $("#googleEditor").hidden = !isGoogle;
  $("#genericEditor").hidden = isGoogle;
  if (isGoogle) updateGoogleType(currentGoogleType);
  else configureDestinationEditor(destination);
}

function refreshSelectedDestinations() {
  const selected = getSelectedDestinations();
  $$(".composition-tab").forEach((tab) => { tab.hidden = !selected.includes(tab.dataset.destination); });
  $$('[data-review-destination]').forEach((row) => { row.hidden = !selected.includes(row.dataset.reviewDestination); });

  if (!selected.includes(currentDestination) && selected.length) updatePreview(selected[0]);

  const count = selected.length;
  const label = count === 1 ? "publicação" : "publicações";
  $("#reviewHeading").textContent = `${count === 4 ? "Quatro" : count} ${label}, sem surpresas`;
  $("#reviewTotal").textContent = `Agendar ${count} ${label}`;
  if (currentStep === 5) $("#nextButton").textContent = `Agendar ${count} ${label}`;
}

function updateGoogleType(type) {
  currentGoogleType = type;
  $$('[data-google-type]').forEach((button) => button.classList.toggle("active", button.dataset.googleType === type));
  $("#googleStandardFields").hidden = type !== "standard";
  $("#googleEventFields").hidden = type !== "event";
  $("#googleOfferFields").hidden = type !== "offer";
  $("#couponLine").hidden = type !== "offer";

  const content = {
    standard: {
      headline: "Novidade na Nelson",
      cta: "Saiba mais",
      badge: "Novidade",
      note: "Atualização permite escolher Reservar, Fazer pedido, Comprar, Saiba mais, Inscrever-se, Ligar ou nenhum botão. A URL é configurada quando o CTA exige navegação.",
    },
    event: {
      headline: "Semana do Hibisco",
      cta: "Fazer pedido",
      badge: "28 SET — 04 OUT",
      note: "Evento exige título e período. Ele também pode usar os CTAs disponíveis para publicações com ação.",
    },
    offer: {
      headline: "15% OFF no Hibisco",
      cta: "Ver oferta",
      badge: "15% OFF",
      note: "Oferta não usa o CTA genérico: o Google renderiza a experiência a partir de cupom, URL de resgate, termos e período.",
    },
  }[type];

  $("#socialHeadline").textContent = content.headline;
  $("#previewCta").textContent = content.cta;
  $("#previewCta").hidden = false;
  $("#offerBadge").textContent = content.badge;
  $("#previewNote").innerHTML = `<strong>Comportamento real do Google.</strong> ${content.note}`;
}

$$('.nav-item').forEach((button) => button.addEventListener("click", () => openPage(button.dataset.page)));
$$('.step').forEach((button) => button.addEventListener("click", () => openStep(Number(button.dataset.step))));
$$('.composition-tab').forEach((button) => button.addEventListener("click", () => updatePreview(button.dataset.destination)));
$$('[data-google-type]').forEach((button) => button.addEventListener("click", () => updateGoogleType(button.dataset.googleType)));

$("#nextButton").addEventListener("click", () => {
  if (currentStep === 5) {
    showToast("Prévia: 4 consequências seriam agendadas de forma independente.");
    return;
  }
  openStep(currentStep + 1);
});
$("#backButton").addEventListener("click", () => openStep(currentStep - 1));

$("#safeAreaToggle").addEventListener("click", (event) => {
  const pressed = event.currentTarget.getAttribute("aria-pressed") === "true";
  event.currentTarget.setAttribute("aria-pressed", String(!pressed));
  $("#safeArea").classList.toggle("visible", !pressed);
});

$("#destinationSecondaryInput").addEventListener("input", (event) => {
  if (event.target.type === "range") $("#previewImage").style.objectPosition = `50% ${event.target.value}%`;
});

$("#destinationText").addEventListener("input", (event) => {
  $("#socialBody").textContent = event.target.value;
});

$("#googleSummary").addEventListener("input", (event) => {
  $("#socialBody").textContent = event.target.value;
  $(".counter strong").textContent = `${event.target.value.length} / 1.500`;
});

$("#couponCode").addEventListener("input", (event) => {
  $("#couponLine strong").textContent = event.target.value || "SEM CÓDIGO";
});

$("#googleCta").addEventListener("change", (event) => {
  $("#previewCta").textContent = event.target.value;
  $("#previewCta").hidden = event.target.value === "Nenhum";
});

$$('.choice-card').forEach((button) => button.addEventListener("click", () => {
  $$('.choice-card').forEach((item) => item.classList.remove("selected"));
  button.classList.add("selected");
}));

$$('.destination-check input').forEach((input) => input.addEventListener("change", () => {
  input.closest(".destination-check").classList.toggle("selected", input.checked);
  refreshSelectedDestinations();
}));

$("#addConnectionButton").addEventListener("click", () => openConnectionWizard());
$$('[data-add-connector]').forEach((button) => {
  button.addEventListener("click", () => openConnectionWizard(button.dataset.addConnector));
});
$$('[data-manage-connector]').forEach((button) => {
  button.addEventListener("click", () => openConnectionWizard(button.dataset.manageConnector, "manage"));
});
$$('[data-connector-choice]').forEach((button) => {
  button.addEventListener("click", () => selectConnector(button.dataset.connectorChoice));
});

$("#connectionNextButton").addEventListener("click", () => {
  if (!currentConnector) return;
  if (connectionStep < 3) {
    connectionStep += 1;
    updateConnectionWizard();
    return;
  }

  const connector = connectorDefinitions[currentConnector];
  const selectedCount = $$('#resourcePicker input[type="checkbox"]:checked').length;
  closeConnectionWizard();
  showToast(connectionMode === "manage"
    ? `Prévia: configuração de ${connector.name} atualizada.`
    : `Prévia: ${connector.name} conectado com ${selectedCount} ${selectedCount === 1 ? "destino" : "destinos"}.`);
});

$("#connectionBackButton").addEventListener("click", () => {
  if (connectionStep === 1) {
    closeConnectionWizard();
    return;
  }
  connectionStep -= 1;
  updateConnectionWizard();
});
$("#closeConnectionWizard").addEventListener("click", closeConnectionWizard);
$("#connectionWizard").addEventListener("click", (event) => {
  if (event.target === event.currentTarget) closeConnectionWizard();
});
$("#connectionWizard").addEventListener("cancel", (event) => {
  event.preventDefault();
  closeConnectionWizard();
});
$("#connectionWizard form").addEventListener("submit", (event) => event.preventDefault());

$("#verifyConnectionsButton").addEventListener("click", (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.textContent = "Verificando…";
  setTimeout(() => {
    button.disabled = false;
    button.textContent = "Verificar todas";
    showToast("Prévia: permissões e capacidades das conexões foram verificadas.");
  }, 650);
});

$$('.preview-cta, .page-action-row .primary-button:not(#addConnectionButton), .activity-row button').forEach((button) => {
  button.addEventListener("click", () => showToast("Interação demonstrativa — nenhum efeito externo foi executado."));
});

openPage(currentPage);
openStep(currentStep);
refreshSelectedDestinations();
updatePreview(currentDestination);
