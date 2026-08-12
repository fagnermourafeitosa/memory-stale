# 01 — Runtime do plugin e hooks

## Problem Statement

O plugin precisa receber contexto antes da tarefa e concluir manutenção depois dela sem depender de ação humana.

## Solution

Empacotar skill, MCP e handlers dos hooks `UserPromptSubmit`, `PostToolUse` e `Stop`.

## User Stories

1. Como usuário, quero instalar e confiar no plugin uma vez para que hooks operem no ciclo do Codex.
2. Como Codex, quero receber contexto antes de agir.
3. Como mantenedor, quero mudanças reais da tarefa disponíveis no fim do turno.

## Implementation Decisions

- `UserPromptSubmit` pede contexto ao módulo de retrieval.
- `PostToolUse` acrescenta operações de escrita ao ledger da tarefa.
- `Stop` combina ledger com diff contra snapshot inicial e chama o motor de lifecycle.
- Snapshot do working tree é criado no início da tarefa; mudanças pré-existentes não entram no ledger da tarefa.
- Hooks são adaptadores finos e tolerantes a erro.

## Testing Decisions

- Simular payload JSON de cada hook e verificar chamadas/saídas do adaptador.
- Validar que workspace sujo anterior à tarefa não aparece como mudança da tarefa.
- Validar que erro interno não impede retorno normal do hook.

## Out of Scope

- Política de memória, parsing de símbolos e persistência.

## Further Notes

- A ativação por projeto será definida junto à configuração em 07.
