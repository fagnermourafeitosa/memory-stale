# 07 — Configuração e relatório HTML

## Problem Statement

Usuário precisa controlar budget e relatório sem gerar ruído em toda tarefa.

## Solution

Ler configuração do projeto e gerar HTML apenas por pedido ou quando auto-report estiver ativo.

## User Stories

1. Como usuário, quero ajustar orçamento de contexto por projeto.
2. Como usuário, quero pedir relatório de saúde de memória.
3. Como usuário, quero optar por gerar relatório automaticamente após mudanças.

## Implementation Decisions

- Configuração: `<repo>/.agents/skills/.agent-memory/config.toml`.
- Default de retrieval é 1500 tokens.
- Relatório é explícito por padrão; auto-report é opção de configuração.
- HTML mostra active, stale, refs e razões; não é interface principal.

## Testing Decisions

- Testar defaults, override válido/inválido e ausência de config.
- Testar HTML com corpus vazio, active, stale e caracteres escapados.
- Testar que relatório não é produzido sem pedido/configuração.

## Out of Scope

- Dashboard servido, frontend reativo ou envio remoto de métricas.

## Further Notes

- Localização do arquivo HTML será configurável.
