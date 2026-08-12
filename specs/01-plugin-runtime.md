# 01 — Runtime do plugin e hooks

## Problem Statement

O plugin precisa receber contexto antes da tarefa e concluir manutenção depois dela sem depender de ação humana.

## Solution

Empacotar manifesto, skill e handlers dos hooks `UserPromptSubmit`,
`PostToolUse` e `Stop`, deixando a inclusão do MCP para a spec 02, quando seu
servidor e contrato existirem de fato.

## User Stories

1. Como usuário, quero instalar e confiar no plugin uma vez para que hooks operem no ciclo do Codex.
2. Como Codex, quero receber contexto antes de agir.
3. Como mantenedor, quero mudanças reais da tarefa disponíveis no fim do turno.

## Implementation Decisions

- O repositório é a raiz instalável do plugin e contém manifesto
  `.codex-plugin/plugin.json`, skill em `skills/` e configuração descoberta por
  padrão em `hooks/hooks.json`.
- Cada hook é um comando JSON: recebe um objeto por `stdin`, escreve somente o
  JSON aceito pelo evento em `stdout` e usa o diretório de trabalho informado
  pelo Codex como raiz do repositório.
- Os comandos dos hooks executam Python por `uv`, em modo frozen e sem sync
  implícito; ambiente e cache do plugin ficam sob o diretório gravável
  `PLUGIN_DATA`, nunca no cache global do usuário.
- `UserPromptSubmit` pede contexto ao módulo de retrieval.
- `PostToolUse` acrescenta operações de escrita ao ledger da tarefa.
- `Stop` combina ledger com diff contra snapshot inicial e chama o motor de lifecycle.
- Snapshot do working tree é criado no início da tarefa; mudanças pré-existentes não entram no ledger da tarefa.
- Hooks são adaptadores finos e tolerantes a erro.
- Até os motores das specs 04 e 05 existirem, suas fronteiras retornam resultado
  vazio sem inventar política de memória; a integração posterior substitui
  somente essas fronteiras, sem alterar o contrato dos hooks.
- Estado efêmero por `turn_id` fica fora do store durável e suas escritas são
  atômicas.

## Testing Decisions

- Seam confirmado: executar os comandos reais declarados em
  `hooks/hooks.json`, enviando payload JSON por `stdin` dentro de repositórios
  Git temporários e verificando `stdout`, exit code e estado local observável.
- A cobertura instrumenta os subprocessos desses comandos e combina seus dados,
  preservando o seam público em vez de duplicar testes em funções internas.
- Validar o manifesto com o validador de plugins usado pelo Codex.
- Simular payload JSON de cada hook e verificar as saídas públicas do adaptador.
- Validar que workspace sujo anterior à tarefa não aparece como mudança da tarefa.
- Validar que erro interno não impede retorno normal do hook.

## Out of Scope

- Ferramenta e configuração MCP, política de memória, parsing de símbolos e persistência.

## Further Notes

- A ativação por projeto será definida junto à configuração em 07.
