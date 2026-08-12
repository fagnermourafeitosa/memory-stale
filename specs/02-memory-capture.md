# 02 — MCP local `memory.capture`

## Problem Statement

O hook sabe quais símbolos mudaram, mas não sabe o significado final da mudança. O próprio Codex precisa fornecer claim estruturado, sem outro LLM.

## Solution

Oferecer ferramenta MCP local `memory.capture` para Codex registrar candidato de memória durante a própria tarefa.

## User Stories

1. Como Codex, quero enviar uma decisão final estruturada ao plugin.
2. Como mantenedor, quero rejeitar claims sem evidência no código alterado.
3. Como usuário, quero que pedido inicial e resumo de diff não virem memória.

## Implementation Decisions

- O servidor MCP local usa transporte stdio JSON-RPC e é declarado pelo plugin
  em `.mcp.json`; o processo usa o repositório Git corrente e o único turno
  ativo para localizar seu ledger efêmero.
- Entrada obrigatória: `kind`, `claim`, `refs`, `durability_reason`.
- `kind`: `behavior`, `contract`, `constraint`, `architecture`, `operation`.
- Skill exige checklist: comportamento durável, risco real de erro futuro, evidência no código final e mais que histórico de tarefa.
- Cada ref deve resolver e ter mudado nesta tarefa.
- Repetição com mesmo kind, claim normalizado e refs é idempotente.
- Candidato válido fica disponível ao `Stop`; MCP não grava memória final sozinho.

## Testing Decisions

- Seam confirmado pela autorização de execução contínua: iniciar o servidor MCP
  real, negociar JSON-RPC por stdio e chamar `memory.capture` em repositórios
  Git temporários cujo turno foi iniciado pelos hooks.
- Testar schema obrigatório, enum fechado, refs ausentes/inalteradas e repetição idempotente.
- Testar que captura válida não persiste memória antes do lifecycle.

## Out of Scope

- Geração de claim por modelo externo ou deduplicação semântica.

## Further Notes

- Skill orienta Codex; MCP valida contrato estrutural.
