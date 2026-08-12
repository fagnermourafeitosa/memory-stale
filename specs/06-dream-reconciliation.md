# 06 — `/memory-stale dream`

## Problem Statement

Usuário precisa poder disparar reconciliação ampla sem esperar uma tarefa normal alterar código.

## Solution

Adicionar operação explícita da skill: `/memory-stale dream`.

## User Stories

1. Como usuário, quero disparar auditoria consciente de memória quando desejar.
2. Como usuário, quero ajustes aplicados e resumidos no mesmo fluxo.
3. Como mantenedor, quero que dream não reescreva memória active sem evidência.

## Implementation Decisions

- Dream audita somente stale, refs quebradas e símbolos não resolvíveis.
- Mesma instância Codex revisa contexto e usa `memory.capture` para novos facts; não existe outro LLM.
- Ajustes são aplicados diretamente e resumo lista criadas, stale e erros.
- Dream não altera memórias active sem motivo verificável.

## Testing Decisions

- Seam confirmado pela autorização contínua: a operação pública `dream`
  recebe o repositório, audita o store real e devolve resumo estruturado; a
  skill orienta a mesma instância Codex a usar essa operação e `memory.capture`.
- Simular corpus misto e verificar escopo limitado de auditoria.
- Testar resumo e propagação não bloqueante de erros.

## Out of Scope

- Reescrita total da base, embeddings ou execução automática de dream.

## Further Notes

- Dream é feature manual disparada por usuário; lifecycle normal permanece automático.
