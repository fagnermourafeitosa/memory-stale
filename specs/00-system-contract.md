# 00 — Contrato do sistema

## Problem Statement

Definir limites compartilhados antes de construir adaptadores ou lógica de memória.

## Solution

Fixar contratos, estados e ordem das specs seguintes.

## User Stories

1. Como mantenedor, quero limites explícitos para que módulos não criem regras conflitantes.
2. Como usuário, quero memória automática sem outro LLM ou CLI manual.

## Implementation Decisions

- Produto: plugin Codex `memory-stale` com skill, MCP local e hooks.
- Git é obrigatório; sem Git, plugin informa estado e não opera.
- Estados: `active` e `stale`. Mudança de ref marca stale; não há supersede implícito.
- Sem fallback por arquivo ou linguagem não suportada.
- Falhas de memória nunca bloqueiam tarefa Codex.
- Ordem: 01 runtime, 02 capture, 03 indexação, 04 lifecycle, 05 retrieval, 06 dream, 07 report/config, 08 testes.

## Testing Decisions

- Cada spec posterior valida seu contrato sem exigir Codex real.

## Out of Scope

- Implementação de qualquer módulo nesta spec.

## Further Notes

- Toda decisão de produto comum deve ser adicionada aqui, não duplicada nas specs de tarefa.
