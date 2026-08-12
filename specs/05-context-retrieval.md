# 05 — Recuperação de contexto

## Problem Statement

Codex precisa receber poucas memórias úteis antes da tarefa, sem contexto stale, embeddings ou custo de outro modelo.

## Solution

Rankear memórias active por match estrutural e BM25, respeitando orçamento configurável.

## User Stories

1. Como Codex, quero receber decisão relacionada antes de alterar código.
2. Como usuário, quero que memória stale nunca seja tratada como fato.
3. Como mantenedor, quero ranking auditável e configurável.

## Implementation Decisions

- Filtrar `active` antes de qualquer ranking.
- Prioridade: match exato de path/símbolo, BM25 em claim e durability reason, boost por refs relacionadas.
- Sem embeddings no v1.
- Orçamento default: 1500 tokens; configurável.
- Resultado é `additionalContext` do `UserPromptSubmit`.

## Testing Decisions

- Seam confirmado pela autorização contínua: a função pública de retrieval
  recebe corpus, prompt e budget e devolve exatamente o contexto injetável;
  integração é observada pelo comando real `UserPromptSubmit`.
- Testar filtro stale, match exato acima de texto, ranking BM25 e corte por orçamento.
- Testar corpus vazio e prompt sem resultado.

## Out of Scope

- Busca semântica, banco vetorial e injeção de toda base de memória.

## Further Notes

- Index local é derivado; Markdown permanece fonte de verdade.
