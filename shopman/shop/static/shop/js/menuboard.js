// Quadro-negro da TV — a camada AO VIVO.
//
// ⚠️ Este arquivo existe por causa do CSP. Em produção o `script-src` não tem
// `'unsafe-inline'` (só em DEBUG), então o `<script>` inline que definia esta
// função era BLOQUEADO: o Alpine carregava, não achava `menuboard`, e cada
// expressão dele falhava — apagando de quebra o texto que o servidor tinha
// renderizado. A tela ficava com um ponto (o indicador "ao vivo", o único
// elemento sem `x-text`) e mais nada.
//
// O estado inicial vem de um `<script type="application/json">`: bloco de DADO,
// não de código, e por isso o CSP não o bloqueia.

function menuboard() {
  var root = document.getElementById("menuboard-root");
  var inicial = JSON.parse(document.getElementById("menuboard-initial").textContent);

  var ref = root.dataset.ref;
      return {
        hydrated: false,
        board: inicial,
        live: true,
        get totalItems() { return (this.board.groups || []).reduce(function (n, g) { return n + (g.items || []).length; }, 0); },
        brl: function (q) { return "R$ " + ((q || 0) / 100).toFixed(2).replace(".", ","); },
        refresh: function () {
          var self = this;
          fetch("/menuboard/" + ref + "/data/", { headers: { accept: "application/json" }, credentials: "same-origin" })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (b) { if (b) { self.board = b; self.live = true; } })
            .catch(function () { self.live = false; });
        },
        init: function () {
          var self = this;
          // A partir daqui quem desenha é o Alpine: o bloco do servidor sai de
          // cena e o dele entra. Sem esta linha os dois apareceriam juntos.
          this.hydrated = true;
          // Quem esconde a pintura do servidor é o Alpine, de dentro do init:
          // se ele não rodar, ela fica. É a diferença entre falhar aberto e
          // falhar fechado, e foi o que deixou a TV em branco.
          var servidor = document.getElementById("menuboard-server");
          if (servidor) { servidor.remove(); }
          try {
            var es = new EventSource("/menuboard/" + ref + "/events/");
            var onEvt = function () { self.refresh(); };
            es.onmessage = onEvt;
            ["listing-changed", "product-paused", "stock-update"].forEach(function (t) { es.addEventListener(t, onEvt); });
            es.onopen = function () { self.live = true; };
            es.onerror = function () { self.live = false; };
          } catch (e) { self.live = false; }
          setInterval(function () { self.refresh(); }, 30000);
        },
      };
    }