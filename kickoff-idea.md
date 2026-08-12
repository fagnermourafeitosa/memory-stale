# Kickoff Idea

Fonte: conversa inicial sobre o conceito de *dreams* e o projeto de memória de agentes.

---

https://platform.claude.com/docs/en/managed-agents/dreams

esse conceito de dream é nada mais q self improvement ?

## Avaliou trade-offs entre ferramentas complexas e soluções minimalistas

Exato, e isso reforça ainda mais o argumento. Repara nos detalhes que vieram na busca: o nvk/llm-wiki é compatível com Obsidian e o iamsashank09/llm-wiki-kit também é baseado no padrão de Karpathy, com integração de PDFs, URLs, YouTube. Isso é bastante peso — vira um sistema de knowledge management completo, com grafo, dashboard, embeddings locais, plugin de vault. Pra muita gente isso é over-engineering pra um agente de código que só precisa não inventar mentira sobre uma função que já foi refatorada.

Isso na real deixa a ideia do checker ainda mais forte, por dois motivos:

1. Ele não depende de adotar llm-wiki nenhum. Se ele só faz regex em cima de arquivos `.md` procurando paths de código citados + compara hash de git, funciona em cima de qualquer pasta de notas — vault do Obsidian, wiki do Karpathy, `AGENTS.md`, ou até um bloco de notas solto que você mantém à mão. Zero acoplamento com a ferramenta de storage.
2. É o oposto filosófico do llm-wiki. Wiki gigante = você instala um sistema. Staleness checker = você roda um script isolado quando quiser, sem migrar nada, sem manter um daemon rodando em `127.0.0.1:3111` feito o agentmemory.

Isso também é uma dor real de adoção: ferramentas tipo llm-wiki pedem buy-in grande (instalar plugin, aprender comandos `/wiki:*`, manter índice vetorial). Um checker de 150 linhas sem dependência nenhuma é o tipo de coisa que dev testa em 2 minutos e ou fica ou descarta — muito mais fácil de "vender" pra comunidade do Codex, que ainda está decidindo o design ideal (voltando pra discussão #12567).

Quer que eu já monte o esqueleto? Pensando no mínimo viável:

- `codex-staleness` (nome provisório) como pacote Python/CLI simples
- Um comando pra "anotar": grava hash do commit atual pra um bloco de texto/arquivo `.md`
- Um comando `check`: varre `.md` em busca de referências a paths e roda `git diff` contra o hash salvo
- Output simples: lista de entradas com ⚠, sem UI, sem dashboard

> não, calma. não gosto da sua abordagem de regex

## Reconsidered estratégia frágil e pivotou para solução estruturada

Faz sentido, regex em cima de prosa livre é frágil e vai gerar falso positivo/negativo direto (falha se o caminho tiver espaço, se for mencionado sem extensão, se for função `foo()` sem citar o arquivo, etc).

Duas alternativas mais sólidas, sem regex nenhum:

### 1. Metadado estruturado na criação, não extração depois

Em vez de tentar adivinhar quais arquivos uma memória menciona lendo o texto, você exige que isso seja declarado explicitamente no momento em que a memória é criada — um front-matter YAML no topo do `.md`:

```yaml
---
refs: [src/auth.py, src/db/session.py]
commit: a3f9c21
---
```

```text
Login usa JWT com refresh token de 7 dias...
```

Zero parsing de linguagem natural. Você só lê YAML (que é trivial e determinístico) e roda `git diff <commit>..HEAD -- <cada path>`. O trabalho de "achar os arquivos relevantes" fica pro agente (que já sabe quais arquivos tocou), não pro seu script tentando adivinhar via regex.

### 2. Capturar automaticamente pelos hooks da sessão, sem o agente precisar declarar nada

Se o Codex expõe eventos de sessão (tipo os hooks que o Omni-Memory e o llm-wiki-kit usam — `SessionEnd`, tool calls de edit/read), dá pra registrar de forma automática quais arquivos foram tocados/lidos naquela sessão que gerou a memória, e salvar isso junto. Zero regex, zero YAML manual — a "referência" é um fato objetivo do que aconteceu no harness, não inferido do texto.

A opção 2 é mais robusta ainda porque não depende do agente lembrar de declarar nada — é automático e correto por construção. Mas exige que o Codex tenha hook de fim de sessão acessível (parece que sim, pelo que apareceu na busca).

Qual dessas prefere como base? Ou tem outra ideia de como amarrar memória → arquivo sem regex?

> porra a gente viu aqui tree sit e bm25 sei la o

## Reconheceu frustração do usuário e simplificou abordagem técnica

Verdade, saiu isso tudo por causa do que a gente foi encontrando nos repos, mas nenhum desses termos precisa entrar no seu MVP. Deixa eu cortar tudo isso fora:

Esquece BM25, esquece tree-sitter, esquece regex. Pro v0, você nem precisa de busca/ranking nenhum. Se são poucas memórias, o "retrieval" é literalmente: pega todos os `.md` não marcados como stale e joga no contexto. Ponto.

O MVP fica assim, sem jargão nenhum:

- Memória = um arquivo `.md` com um cabeçalho simples no topo (paths tocados + hash do commit).
- `check` = pra cada memória, roda `git diff <hash>..HEAD -- <paths>`. Mudou → marca stale. Não mudou → ok.
- Sem busca, sem embedding, sem parser de código, sem NLP.
- É basicamente um script de ~80 linhas em Python usando só `subprocess` pra chamar git e YAML/JSON pra ler o cabeçalho. Isso é tudo.

Quer que eu escreva esse script agora, do jeito mais burro possível, só pra você ter algo rodando?

> vai tomar no teu cu. vou gastar token pra caralho porra

## Reconheceu frustração e entregou solução direta sem ferramentas

Entendido, sem mais enrolação. Aqui está, direto:

Claude’s response was interrupted.

> quero algo bom, um projeto legal para portfolio. nao precisa ser pragmatico pra caralho. aqui é pra portfolio

## Recalibrou estratégia para projeto ambicioso e polido

Show. Portfólio muda a equação — aí vale a pena ter mais profundidade técnica pra demonstrar, não só resolver o problema do jeito mais magro possível.

Aqui vai uma proposta de escopo que ainda ataca o gap real que achamos (staleness em memória de agente, algo que o llm-wiki e afins não cobrem bem), mas com nível de engenharia que rende portfólio de verdade:

Nome de trabalho: algo tipo `agent-memory-guard` ou `stale-context` — memória de agente com verificação de veracidade contra o código.

### O que mostra tecnicamente

1. **Staleness em nível de símbolo, não de arquivo** — em vez de regex ou "o arquivo mudou", usa o módulo AST nativo do Python (zero dependência externa, mas mesmo princípio do tree-sitter) pra saber qual função/classe mudou entre commits, e só invalida memórias ligadas àquele símbolo específico. Isso é o diferencial real de engenharia: parsing de AST, diff estrutural em vez de diff textual.
2. **Captura automática via hook, não front-matter manual** — um hook de fim de sessão (do jeito que Codex/Claude Code expõem) grava automaticamente quais funções/arquivos foram tocados na sessão, junto com o resumo da memória. Isso mostra que você entende arquitetura de plugins de agente, não só scripting.
3. **Git como fonte de verdade** — usa `git log`/`git diff` estruturalmente (via subprocess ou GitPython) pra reconstruir o histórico de mudança de cada símbolo. Bom exercício de mostrar que você manja de internals do git além do básico.
4. **CLI decente** — Typer ou Click, com comandos limpos (`remember`, `check`, `list`, `gc`), saída bonita (Rich pra tabelas coloridas no terminal). Isso é barato de fazer e deixa a demo muito mais apresentável.
5. **Relatório visual simples** — um HTML estático gerado (sem precisar de servidor rodando) mostrando memórias ativas vs. stale, tipo um "health report" da base de conhecimento. Ótimo pra print de tela no README.
6. **Testes + CI** — pytest com casos de "símbolo mudou → marca stale" / "símbolo não mudou, só formatação → não marca". Isso é o tipo de coisa que quem revisa portfólio valoriza (mostra rigor).
7. **README forte** — problema, por que existe (contexto da discussão do Codex #12567, citando a dor real da comunidade), arquitetura, GIF de demo.

Isso é bem mais trabalho que o script de 80 linhas, mas ainda é escopado — só Python no v1 (extensível depois), sem virar um produto gigante tipo o Omni-Memory.
