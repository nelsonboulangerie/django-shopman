// Sonda de TEXTO CORTADO — roda DENTRO da página (Playwright `page.evaluate`).
//
// Queixa do dono (28/09/2026): "tem copy estourando o espaço disponível… está
// muito deselegante". Em vez de caçar um por um, a sonda MEDE: todo elemento
// visível com texto próprio cuja caixa não comporta o texto.
//
//   - `ellipsis`: `text-overflow: ellipsis` efetivamente cortando (o "Dividir co…");
//   - `clip-x` / `clip-y`: overflow oculto com o conteúdo maior que a caixa
//     (linha cortada, `line-clamp`, texto escondido sem reticências);
//   - `spill`: overflow visível e o texto sai da caixa do próprio elemento — ou
//     da tela — por cima do vizinho.
//
// Cada achado sai classificado pelo papel do texto, porque o critério da casa
// é por papel: texto de AÇÃO (botão, link, aba) e de AVISO (alerta, faixa de
// avisos, descrição de diálogo) NUNCA se cortam; DADO do usuário (nome de
// produto, endereço) pode ser truncado se o texto inteiro estiver disponível
// (`title` no próprio elemento ou num ancestral próximo).
//
// Arquivo JS puro, sem import: é serializado e injetado como está.

export function findClippedText(options) {
  const opts = Object.assign({ tolerance: 1 }, options || {});
  const results = [];
  const seen = new Set();
  const vw = document.documentElement.clientWidth;

  const ACTION = 'button, a[href], [role="button"], [role="tab"], [role="menuitem"], [role="option"], [role="radio"], [role="checkbox"], [role="switch"], summary, label';
  const NOTICE = '[role="alert"], [role="status"], [aria-label="Avisos"], [data-notice], [data-slot="dialog-description"], [data-slot="alert"], [data-slot="alert-description"], [data-slot="alert-title"]';

  function visible(el, cs) {
    if (cs.display === "none" || cs.visibility === "hidden" || Number(cs.opacity) === 0) return false;
    if (el.closest('[aria-hidden="true"], .sr-only, [hidden]')) return false;
    const r = el.getBoundingClientRect();
    if (r.width <= 2 || r.height <= 2) return false;
    // Visualmente escondido de propósito (texto só para leitor de tela: a caixa
    // de 1px com `clip`). Não é corte, é o padrão sr-only.
    for (let node = el, depth = 0; node && depth < 4; node = node.parentElement, depth += 1) {
      const ncs = getComputedStyle(node);
      if ((ncs.clip && ncs.clip !== "auto") || ncs.clipPath === "inset(50%)") return false;
      const nr = node.getBoundingClientRect();
      if (nr.width <= 2 || nr.height <= 2) return false;
    }
    return true;
  }

  function ownText(el) {
    let text = "";
    for (const node of el.childNodes) {
      if (node.nodeType === 3) text += node.textContent;
    }
    return text.replace(/\s+/g, " ").trim();
  }

  function fullText(el) {
    return (el.innerText || el.textContent || "").replace(/\s+/g, " ").trim();
  }

  const norm = (text) => (text || "").replace(/\s+/g, " ").trim().toLowerCase();

  /** O texto INTEIRO está disponível num `title` (do próprio elemento ou de um ancestral próximo)? */
  function titled(el) {
    const whole = norm(fullText(el));
    for (let node = el, depth = 0; node && depth < 4; node = node.parentElement, depth += 1) {
      const title = norm(node.getAttribute && node.getAttribute("title"));
      if (title && whole && title.includes(whole)) return true;
    }
    return false;
  }

  function role(el) {
    if (el.closest(NOTICE)) return "notice";
    if (el.closest(ACTION)) return "action";
    if (/^H[1-6]$/.test(el.tagName) || el.closest('[data-slot="dialog-title"], [data-slot="card-title"]')) return "heading";
    return "data";
  }

  function textRect(el) {
    const range = document.createRange();
    let rect = null;
    for (const node of el.childNodes) {
      if (node.nodeType !== 3 || !node.textContent.trim()) continue;
      range.selectNodeContents(node);
      for (const r of range.getClientRects()) {
        if (!r.width) continue;
        rect = rect
          ? { left: Math.min(rect.left, r.left), right: Math.max(rect.right, r.right), top: Math.min(rect.top, r.top), bottom: Math.max(rect.bottom, r.bottom) }
          : { left: r.left, right: r.right, top: r.top, bottom: r.bottom };
      }
    }
    return rect;
  }

  function describe(el) {
    const parts = [];
    for (let node = el, depth = 0; node && node !== document.body && depth < 4; node = node.parentElement, depth += 1) {
      let piece = node.tagName.toLowerCase();
      const label = node.getAttribute("aria-label");
      if (label) piece += `[aria-label="${label.slice(0, 40)}"]`;
      else if (node.getAttribute("data-slot")) piece += `[data-slot="${node.getAttribute("data-slot")}"]`;
      parts.unshift(piece);
    }
    return parts.join(" > ");
  }

  function report(el, kind, cs, extra) {
    const key = `${kind}:${fullText(el)}:${Math.round(el.getBoundingClientRect().left)}`;
    if (seen.has(key)) return;
    seen.add(key);
    const r = el.getBoundingClientRect();
    results.push(Object.assign({
      kind,
      role: role(el),
      titled: titled(el),
      text: fullText(el).slice(0, 160),
      width: Math.round(el.clientWidth || r.width),
      needed: Math.round(el.scrollWidth),
      height: Math.round(el.clientHeight || r.height),
      neededHeight: Math.round(el.scrollHeight),
      selector: describe(el),
      ellipsisStyle: cs.textOverflow === "ellipsis",
    }, extra || {}));
  }

  const all = document.body.querySelectorAll("*");
  for (const el of all) {
    if (el.tagName === "SCRIPT" || el.tagName === "STYLE" || el.tagName === "svg" || el.closest("svg")) continue;
    if (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT") continue;
    const text = ownText(el);
    if (!text) continue;
    const cs = getComputedStyle(el);
    if (!visible(el, cs)) continue;
    const hidesX = cs.overflowX !== "visible";
    const hidesY = cs.overflowY !== "visible";
    const t = opts.tolerance;
    // Rolagem de propósito (lista que rola) não é corte de texto.
    const scrollsX = cs.overflowX === "auto" || cs.overflowX === "scroll";
    const scrollsY = cs.overflowY === "auto" || cs.overflowY === "scroll";
    if (hidesX && !scrollsX && el.scrollWidth > el.clientWidth + t) {
      report(el, cs.textOverflow === "ellipsis" ? "ellipsis" : "clip-x", cs);
      continue;
    }
    if (hidesY && !scrollsY && el.scrollHeight > el.clientHeight + t) {
      report(el, "clip-y", cs);
      continue;
    }
    // Coluna ESMAGADA: o texto não é cortado, mas a caixa ficou tão estreita
    // que a frase vira uma palavra por linha (o pagamento em 1024px com a barra
    // aberta: o aviso da cozinha em 30px de largura). Medido pela palavra mais
    // longa: se ela não cabe na linha, a caixa é mais estreita que o texto.
    let block = el;
    while (block && block.parentElement && getComputedStyle(block).display === "inline") block = block.parentElement;
    if (text.length >= 12 && block.clientWidth > 0 && block.clientWidth < 72) {
      report(el, "crushed", cs, { width: block.clientWidth });
      continue;
    }
    const rect = textRect(el);
    if (!rect) continue;
    // Dentro de quem ROLA na horizontal (a fileira de categorias), o texto fora
    // da borda está ao alcance do gesto de deslizar: não é corte.
    let slidAway = false;
    for (let node = el.parentElement; node && node !== document.body; node = node.parentElement) {
      const ncs = getComputedStyle(node);
      if (ncs.overflowX === "auto" || ncs.overflowX === "scroll") {
        const nbox = node.getBoundingClientRect();
        slidAway = rect.right > nbox.right + t || rect.left < nbox.left - t;
        break;
      }
    }
    if (slidAway) continue;
    const box = el.getBoundingClientRect();
    if (rect.right > vw + t) {
      report(el, "spill", cs, { spill: "viewport", overflowPx: Math.round(rect.right - vw) });
      continue;
    }
    // O texto sai da caixa do PRÓPRIO elemento (só quando o elemento tem caixa
    // própria — inline não tem largura a respeitar).
    if (cs.display !== "inline" && (rect.right > box.right + t || rect.left < box.left - t)) {
      report(el, "spill", cs, { spill: "box", overflowPx: Math.round(Math.max(rect.right - box.right, box.left - rect.left)) });
      continue;
    }
    // …ou da caixa de quem o CONTÉM, sem corte nenhum: o botão "Preencher CPF
    // na nota" que não quebra linha empurra a borda do aviso e passa por cima
    // da coluna vizinha. Três níveis de ancestrais com caixa própria.
    let spilled = false;
    for (let parent = el.parentElement, depth = 0; parent && parent !== document.body && depth < 4; parent = parent.parentElement) {
      const pcs = getComputedStyle(parent);
      if (pcs.display === "inline" || pcs.display === "contents") continue;
      depth += 1;
      if (["auto", "scroll"].includes(pcs.overflowX) || ["auto", "scroll"].includes(pcs.overflowY)) break;
      const pbox = parent.getBoundingClientRect();
      if (rect.right > pbox.right + t || rect.left < pbox.left - t) {
        report(el, "spill", cs, { spill: "container", overflowPx: Math.round(Math.max(rect.right - pbox.right, pbox.left - rect.left)) });
        spilled = true;
        break;
      }
    }
    if (spilled) continue;
    // …ou de um ancestral que corta (overflow oculto) — o texto está lá, mas
    // some atrás da borda de quem o contém.
    for (let parent = el.parentElement, depth = 0; parent && parent !== document.body && depth < 8; parent = parent.parentElement, depth += 1) {
      const pcs = getComputedStyle(parent);
      if (pcs.overflowX === "visible" && pcs.overflowY === "visible") continue;
      // Quem ROLA não corta: o que passa da borda está ao alcance da rolagem
      // (a lista abaixo da dobra, a fileira de categorias que desliza). E os
      // ancestrais acima dele não julgam o que está dentro dele.
      if (["auto", "scroll"].includes(pcs.overflowX) || ["auto", "scroll"].includes(pcs.overflowY)) break;
      const pbox = parent.getBoundingClientRect();
      if (rect.right > pbox.right + t || rect.left < pbox.left - t || rect.bottom > pbox.bottom + t) {
        report(el, "clip-parent", cs, { overflowPx: Math.round(Math.max(rect.right - pbox.right, rect.bottom - pbox.bottom, pbox.left - rect.left)) });
        break;
      }
    }
  }
  return results;
}

/**
 * O critério da casa. Aviso e título nunca se cortam, e coluna esmagada nunca
 * passa. O resto (rótulo de botão, dado do usuário) só passa cortado quando o
 * texto INTEIRO está no `title` — o que, para rótulo FIXO de botão, é barrado
 * antes, na varredura estática (`guardrails.copyNeverTruncates.test.ts`): texto
 * escrito no template nunca leva `truncate`.
 */
export function violatesHouseRule(finding) {
  if (finding.kind === "crushed") return true;
  if (finding.role === "notice" || finding.role === "heading") return true;
  return !finding.titled;
}
