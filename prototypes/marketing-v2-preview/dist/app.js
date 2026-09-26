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

let currentPage = "campaigns";
let currentStep = 3;
let currentDestination = "google";
let currentGoogleType = "offer";
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

$$('.preview-cta, .page-action-row .primary-button, .activity-row button').forEach((button) => {
  button.addEventListener("click", () => showToast("Interação demonstrativa — nenhum efeito externo foi executado."));
});

openPage(currentPage);
openStep(currentStep);
refreshSelectedDestinations();
updatePreview(currentDestination);
