# 04 — Store e lifecycle de memória

## Problem Statement

Claims capturados precisam virar memória auditável, e memórias ligadas a código mudado precisam se tornar stale de forma determinística.

## Solution

Implementar motor puro que recebe memórias, ledger e captures e devolve operações persistíveis.

## User Stories

1. Como equipe, quero memórias versionáveis junto ao projeto.
2. Como usuário, quero saber por que uma memória ficou stale.
3. Como Codex, quero criar uma memória com várias refs alteradas na mesma tarefa.

## Implementation Decisions

- Memórias: `<repo>/.agents/skills/.agent-memory/memories/*.md` com front matter estruturado.
- Motor cria memória para candidate válido e marca active existente como stale quando assinatura atual diverge.
- Stale registra razão por ref: mudança, símbolo ausente, arquivo ausente ou não resolvível.
- Não edita claim active para representar mudança; novo fato é nova memória.
- Escritas são atômicas: falha não deixa memória parcial.

## Testing Decisions

- Testar criação, múltiplas refs, cada razão de stale, idempotência e escrita atômica.
- Testar motor como seam único com entradas/saídas puras.

## Out of Scope

- Rendering HTML, ranking e chamadas de hook.

## Further Notes

- Cache e ledger não pertencem ao store durável.
