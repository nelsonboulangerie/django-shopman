import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

// ⚠️ Os últimos termos são CHAVES de JSON que chegaram a aparecer na tela
// ("collections, skus", "bought_skus"): chave é contrato com o servidor, não
// vocabulário do gestor.
const FORBIDDEN_OPERATOR_TERMS =
  /\b(announcements?|churn|flows?|providers?|receipts?|sandboxes?|templates?|skus?|collections?|bought_\w+|price_tiers|rfm_segments|audience_rules|trigger_filter)\b/i;

function vueFiles(directory: string): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    return statSync(path).isDirectory()
      ? vueFiles(path)
      : path.endsWith(".vue")
        ? [path]
        : [];
  });
}

function literalTemplateText(source: string): string {
  const withoutScripts = source
    .replace(/<script[\s\S]*?<\/script>/g, "")
    .replace(/<style[\s\S]*?<\/style>/g, "");
  const templateStart = withoutScripts.indexOf("<template>");
  if (templateStart < 0) return "";
  return withoutScripts
    .slice(templateStart)
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/\{\{[\s\S]*?\}\}/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ");
}

describe("linguagem normal do operador", () => {
  it("não expõe vocabulário técnico em inglês nos textos literais da UI", () => {
    const appRoot = new URL("../app", import.meta.url).pathname;
    const leaks = vueFiles(appRoot).flatMap((path) => {
      const text = literalTemplateText(readFileSync(path, "utf8"));
      const found = text.match(FORBIDDEN_OPERATOR_TERMS)?.[0];
      return found ? [`${path}: ${found}`] : [];
    });

    expect(leaks).toEqual([]);
  });

  // ⚠️ "A fornada segue normalmente" no recusar: fornada é UM dos gatilhos (há
  // estoque baixo, produto novo, hora marcada, disparo manual). Copy que nomeia
  // um caso ensina o gestor a esperar só aquele.
  it("não nomeia um gatilho como se fosse o único", () => {
    const appRoot = new URL("../app", import.meta.url).pathname;
    const leaks = vueFiles(appRoot).flatMap((path) => {
      const text = literalTemplateText(readFileSync(path, "utf8"));
      const found = text.match(/\bfornada segue\b/i)?.[0];
      return found ? [`${path}: ${found}`] : [];
    });

    expect(leaks).toEqual([]);
  });
});

/** O nome acessível de um controle, estático ou interpolado.
 *
 *  Pega `aria-label="..."` e `:aria-label="..."`, inclusive quando o valor ocupa
 *  várias linhas — que foi exatamente onde o rótulo mentiroso se escondeu. */
function ariaLabelValues(source: string): string[] {
  const values: string[] = [];
  const pattern = /:?aria-label="([^"]*)"/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    values.push(match[1]!.replace(/\s+/g, " ").trim());
  }
  return values;
}

describe("o nome acessível não promete mais do que o controle faz", () => {
  // ⚠️ A régua da casa: "se 'Disparar agora' não dispara, então é mentira". O remédio
  // foi aplicado nos rótulos VISÍVEIS e o nome acessível ficou para trás — quem usa
  // leitor de tela ouvia "Disparar a campanha X agora" num botão que só abre um painel
  // de público. Esta varredura tranca o gêmeo: só o último gesto do caminho pode
  // prometer o ato agora, e ele vive na caixa de confirmação, onde o ato acontece.
  const ACT_NOW = /\b(disparar|enviar|publicar)\b[^"]{0,60}\bagora\b/i;
  const ALLOWED = ["MarketingCommandConfirmationDialog.vue"];

  it("nenhum aria-label diz 'agora' fora da caixa onde o ato acontece", () => {
    const appRoot = new URL("../app", import.meta.url).pathname;
    const leaks = vueFiles(appRoot).flatMap((path) => {
      if (ALLOWED.some((allowed) => path.endsWith(allowed))) return [];
      return ariaLabelValues(readFileSync(path, "utf8"))
        .filter((value) => ACT_NOW.test(value))
        .map((value) => `${path}: ${value}`);
    });

    expect(leaks).toEqual([]);
  });
});

/** Texto e código de um `.ts`, sem os comentários.
 *
 *  A regra da casa vale para STRING — o que chega a alguém —, não para comentário nem
 *  docstring. Tirar os comentários primeiro é o que separa uma coisa da outra. */
function codeWithoutComments(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, " ")
    .replace(/^\s*\/\/.*$/gm, " ");
}

function sourceFiles(directory: string, extensions: string[]): string[] {
  return readdirSync(directory).flatMap((entry) => {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) return sourceFiles(path, extensions);
    return extensions.some((extension) => path.endsWith(extension)) ? [path] : [];
  });
}

describe("a palavra da casa é dispositivo", () => {
  // ⚠️ Regra escrita do `CLAUDE.md`: **"dispositivo", nunca "aparelho"**, em toda
  // superfície de operador e em todo texto de tela. Não é opinião — e não é hipótese:
  // em 17/09 esta deriva custou 104 arquivos, e o convite de instalação dos oito apps
  // nasceu errado por causa dela. A trava que existe
  // (`shopman/backstage/tests/test_vocabulario_de_tela.py`) varre PYTHON; string de
  // `.vue` e de `.ts` passava por baixo dela, e era por baixo dela que o Marketing
  // estava fora da regra.
  //
  // A exceção da maquininha de cartão não cabe aqui: o Marketing não fala de pagamento.
  it("nenhum texto de tela chama o dispositivo de aparelho", () => {
    const appRoot = new URL("../app", import.meta.url).pathname;
    const leaks = [
      ...vueFiles(appRoot).flatMap((path) => {
        const text = literalTemplateText(readFileSync(path, "utf8"));
        return /aparelh/i.test(text) ? [`${path} (template)`] : [];
      }),
      ...sourceFiles(appRoot, [".ts"]).flatMap((path) => {
        const code = codeWithoutComments(readFileSync(path, "utf8"));
        return /aparelh/i.test(code) ? [`${path} (código)`] : [];
      }),
    ];

    expect(leaks).toEqual([]);
  });

  // O harness visual serve as respostas do servidor: um rótulo errado ali vira um
  // rótulo errado no retrato, e o retrato é o que diz que a tela está certa.
  it("o harness visual também não inventa 'aparelho' no lugar do servidor", () => {
    const mock = readFileSync(
      new URL("./visual/mock_backend.py", import.meta.url),
      "utf8",
    );

    expect(mock).not.toMatch(/aparelh/i);
  });
});

/** Texto de tela de um `.vue`: o que está entre as tags MAIS o que está em atributo
 *  que chega a alguém (`placeholder`, `aria-label`, `title`, `alt`). Sem os dois, meia
 *  varredura: "Sai por" é conteúdo, e um `placeholder="quando sai"` é atributo. */
function screenText(source: string): string {
  const attributes = Array.from(
    source.matchAll(/(?:placeholder|aria-label|title|alt)="([^"]*)"/g),
    (match) => match[1] ?? "",
  ).join(" ");
  return `${literalTemplateText(source)} ${attributes}`;
}

describe("o sistema não sai: ele envia, publica ou dispara", () => {
  // ⚠️ Vocabulário fechado do dono: mensagem se ENVIA (direta, não se apaga), postagem
  // se PUBLICA (pública, se apaga), e o genérico dos dois é DISPARAR. "Sair" não é ato
  // desta casa — quem lê "o que sai" tem que adivinhar qual dos três aconteceu, e os
  // três têm consequências diferentes.
  //
  // Esta varredura existe porque a primeira leva consertou as SEIS frases que a lista
  // nomeava e não varreu a classe: sobraram treze, em nove arquivos, e quem achou foi o
  // dono abrindo a tela. Instância consertada sem trava volta.
  const LEAVES = /\b(sai|saiu|saem|sair|sairá|sairão|saíram|saía)\b/i;

  /** O que PODE dizer "sair", com o motivo. Lista que só encolhe.
   *
   *  A regra é sobre o SISTEMA agindo. A padaria continua tendo forno, e pão continua
   *  saindo dele: quando a frase é a voz do padeiro, e não a do sistema, "sair" é a
   *  palavra certa e trocá-la produziria um português que ninguém fala. */
  const ALLOWED = [
    // Exemplo de mensagem no formulário de modelo — é o texto que o PADEIRO escreve.
    "acabou de sair do forno",
    // Exemplo de NOME de modelo, no mesmo formulário e pela mesma razão: quem nomeia
    // é o padeiro, e o que sai do forno é o pão.
    "Saiu do forno",
  ];

  it("nenhum texto de tela diz que alguma coisa 'sai'", () => {
    const appRoot = new URL("../app", import.meta.url).pathname;
    const strip = (text: string) =>
      ALLOWED.reduce((rest, allowed) => rest.split(allowed).join(" "), text);

    const leaks = [
      ...vueFiles(appRoot).flatMap((path) => {
        const found = strip(screenText(readFileSync(path, "utf8"))).match(LEAVES);
        return found ? [`${path} (tela): ${found[0]}`] : [];
      }),
      ...sourceFiles(appRoot, [".ts"])
        .filter((path) => !path.includes("/generated/"))
        .flatMap((path) => {
          const found = strip(
            codeWithoutComments(readFileSync(path, "utf8")),
          ).match(LEAVES);
          return found ? [`${path} (código): ${found[0]}`] : [];
        }),
    ];

    expect(leaks).toEqual([]);
  });
});

describe("um gesto, um rótulo", () => {
  // ⚠️ Havia NOVE maneiras de dizer a mesma coisa, em 20 lugares: "Tentar novamente",
  // "Verificar novamente", "Atualizar verificação", "Contar novamente", "Revalidar",
  // "Conferir de novo", "Tentar atualizar", "Tentar carregar o resultado". Nenhuma
  // errada sozinha; juntas, ensinam o gestor a ler cada tela do zero.
  //
  // São dois, e a diferença é real: "Tentar de novo" recarrega o que FALHOU;
  // "Atualizar" busca o estado novo de algo que JÁ carregou. Quem inventar um terceiro
  // trombar aqui, e a pergunta certa é qual dos dois ele é.
  const BANNED = [
    "Tentar novamente",
    "Verificar novamente",
    "Atualizar verificação",
    "Contar novamente",
    "Revalidar",
    "Conferir de novo",
    "Tentar atualizar",
    "Tentar carregar",
  ];

  it("só existem dois rótulos para recarregar e atualizar", () => {
    const appRoot = new URL("../app", import.meta.url).pathname;
    const leaks = [
      ...vueFiles(appRoot).flatMap((path) => {
        const text = screenText(readFileSync(path, "utf8"));
        const found = BANNED.filter((label) => text.includes(label));
        return found.map((label) => `${path} (tela): ${label}`);
      }),
      ...sourceFiles(appRoot, [".ts"])
        .filter((path) => !path.includes("/generated/"))
        .flatMap((path) => {
          const code = codeWithoutComments(readFileSync(path, "utf8"));
          const found = BANNED.filter((label) => code.includes(label));
          return found.map((label) => `${path} (código): ${label}`);
        }),
    ];

    expect(leaks).toEqual([]);
  });
});

describe("o mesmo conceito tem um nome só nas duas telas", () => {
  // ⚠️ A legenda das plataformas existe em DOIS lugares — o cartão de revisão e o
  // formulário de campanha — e elas derivaram: uma virou "Disparado via" e a outra
  // ficou em "Entregar por". Mesmo conceito, dois nomes, e nenhum teste reclamava,
  // porque cada tela tinha o seu.
  //
  // "por" também é ambíguo em português: serve para AGENTE ("disparado por Pablo") e
  // para MEIO ("disparado por Instagram"). Num cartão que mostra quem aprovou, a
  // leitura errada está ao alcance. "via" só pode ser meio.
  it("a legenda das plataformas é a mesma no cartão e no formulário", () => {
    const appRoot = new URL("../app", import.meta.url).pathname;
    const screens = vueFiles(appRoot)
      .filter((path) => /AnnouncementCard|CampaignForm/.test(path))
      .map((path) => screenText(readFileSync(path, "utf8")));

    expect(screens).toHaveLength(2);
    for (const text of screens) {
      expect(text).toContain("Disparado via");
      expect(text).not.toContain("Entregar por");
    }
  });
});

describe("faixa é preço; a lane chama-se plataforma", () => {
  // ⚠️ A colisão do §D7b do `omotenashi-copy.md`, que o §5 listava como dívida viva
  // ("B1, 5 ocorrências"): "faixa" servia de *lane* de processamento num app onde
  // **"Faixa de preço"** é conceito de negócio no formulário ao lado. O gestor acabava
  // de montar um público por faixa de preço e lia "3 faixas que não tinham começado
  // foram canceladas" — e ninguém desconfia de uma palavra que acabou de aprender no
  // app. A lane passou a ser nomeada pelo que é: **plataforma**.
  //
  // Esta é a razão de a trava existir em vez de uma lista de palavras proibidas: a
  // palavra não é proibida, o SENTIDO é. "Faixa de preço" fica e é retirada antes da
  // varredura; o que sobrar em texto de tela é a lane voltando.
  //
  // Comentário e docstring seguem livres — a regra é sobre a tela (§5.1: a ampliação
  // de canal valeu para "aparelho", e o documento diz explicitamente que ela NÃO
  // generaliza). É por isso que a faixa-banner ("a faixa dizia 'Enviado' em verde"),
  // que é outro sentido ainda, continua podendo ser escrita para quem lê o código.
  const PRICE_TIER = /faixa de preço/gi;
  const LANE = /\bfaixas?\b/i;

  it("nenhum texto de tela chama a plataforma de faixa", () => {
    const appRoot = new URL("../app", import.meta.url).pathname;
    const strip = (text: string) => text.replace(PRICE_TIER, " ");

    const leaks = [
      ...vueFiles(appRoot).flatMap((path) => {
        const found = strip(screenText(readFileSync(path, "utf8"))).match(LANE);
        return found ? [`${path} (tela): ${found[0]}`] : [];
      }),
      ...sourceFiles(appRoot, [".ts"])
        .filter((path) => !path.includes("/generated/"))
        .flatMap((path) => {
          const found = strip(
            codeWithoutComments(readFileSync(path, "utf8")),
          ).match(LANE);
          return found ? [`${path} (código): ${found[0]}`] : [];
        }),
    ];

    expect(leaks).toEqual([]);
  });

  // A outra metade da trava: se "Faixa de preço" sumir do formulário, a varredura
  // acima continuaria verde sem que ninguém percebesse que o conceito de negócio foi
  // renomeado por engano.
  it("'Faixa de preço' continua sendo o conceito de negócio no formulário", () => {
    const appRoot = new URL("../app", import.meta.url).pathname;
    const screens = vueFiles(appRoot)
      .map((path) => screenText(readFileSync(path, "utf8")))
      .filter((text) => /faixa de preço/i.test(text));

    expect(screens.length).toBeGreaterThan(0);
  });
});
