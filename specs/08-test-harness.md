# 08 — Harness de testes end-to-end

## Problem Statement

Plugin depende de Git, hooks, MCP, arquivos e tree-sitter; testes isolados não bastam para provar lifecycle.

## Solution

Montar harness com repositórios Git temporários e eventos de Codex simulados.

## User Stories

1. Como mantenedor, quero testar fluxo completo sem sessão Codex real.
2. Como mantenedor, quero reproduzir tarefas que alteram muitos arquivos e linguagens.
3. Como usuário, quero confiança de que falha de memória não trava trabalho.

## Implementation Decisions

- Harness constrói repositório temporário, baseline sujo opcional, eventos de hooks e capturas MCP.
- Cenários atravessam retrieval, ledger, capture, lifecycle e persistência.
- Fixtures abrangem todas linguagens v1.

## Testing Decisions

- Seam confirmado pela autorização contínua: o harness inicia repositório Git
  temporário e executa hooks/MCP reais por subprocesso, sem sessão Codex e sem
  chamar funções internas de produção.
- Fluxo: contexto active → edição → capture → Stop → Markdown e stale corretos.
- Cenários: múltiplos arquivos, refs múltiplas, comentário, remoção, linguagem inválida, captura duplicada, falha de indexação e dream.
- Testes verificam comportamento observável e conteúdo persistido, não chamadas internas.

## Out of Scope

- Testar UI real do Codex ou rede externa.

## Further Notes

- Este harness é base de demonstração de qualidade para portfólio.
