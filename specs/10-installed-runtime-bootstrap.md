# 10 — Bootstrap do runtime instalado

## Problem Statement

Um plugin recém-instalado recebe um `PLUGIN_DATA` vazio. Os hooks atuais usam
`uv run --no-sync`, portanto o ambiente isolado não contém as dependências do
runtime e a memória não consegue operar fora do checkout de desenvolvimento.

## Solution

Adicionar um bootstrap determinístico compartilhado pelos hooks e pelo MCP que
sincroniza o ambiente isolado em `PLUGIN_DATA` a partir do lockfile do plugin
antes de executar o módulo solicitado.

## User Stories

1. Como usuário, quero que a primeira execução prepare o runtime local para que
   o plugin funcione imediatamente após a instalação.
2. Como usuário, quero cache e ambiente sob `PLUGIN_DATA` para que o plugin não
   escreva no cache Python global.
3. Como mantenedor, quero execução frozen para que a instalação respeite o
   lockfile publicado.

## Implementation Decisions

- Um script único sob `scripts/` é o entrypoint de hooks e MCP.
- O script define ambiente e cache sob `PLUGIN_DATA`, executa `uv sync --frozen`
  e então `uv run --frozen --no-sync` para o módulo solicitado.
- O bootstrap não usa pip, não grava no repositório alvo e não exige uma
  instalação Python global de dependências.
- Harnesses já sincronizados podem definir `MEMORY_STALE_SKIP_SYNC=1`; o plugin
  instalado nunca define esse bypass. Eles apontam explicitamente para a
  `.venv` de desenvolvimento sem reutilizar a raiz como `PLUGIN_DATA`.
- Falhas de bootstrap permanecem não bloqueantes para hooks por meio dos
  adaptadores existentes; o MCP encerra com erro observável de processo.

## Testing Decisions

- Seam confirmado pela necessidade de instalação: copiar o plugin para uma
  pasta isolada, fornecer `PLUGIN_DATA` vazio e executar o comando real de
  `UserPromptSubmit` em um repositório Git temporário.
- Verificar criação da `.venv` e do cache somente dentro de `PLUGIN_DATA`, JSON
  válido no stdout e sucesso em uma segunda execução.

## Out of Scope

- Marketplace, publicação pública, atualização automática e novos recursos de
  memória.

## Further Notes

- Esta correção é pré-requisito para validar a instalação local real.
