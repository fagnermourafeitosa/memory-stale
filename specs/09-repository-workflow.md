# 09 — Workflow de contribuição e ambiente Python

## Problem Statement

O projeto precisa impedir mudanças sem contrato, commits não autorizados,
trabalho misturado na mesma branch e dependências Python instaladas diretamente
no ambiente global.

## Solution

Definir um workflow obrigatório de contribuição: spec antes de qualquer
feature, bug ou ajuste; branch dedicada por unidade de trabalho; TDD para
comportamento; autorização explícita antes de commit; e `uv` como único gestor
de Python, dependências, lockfile e ambiente virtual.

## User Stories

1. Como mantenedor, quero que toda mudança de comportamento tenha uma spec para
   que pedidos soltos não virem implementação ambígua.
2. Como mantenedor, quero uma branch por spec, feature, bug ou chore para que
   mudanças independentes não sejam misturadas.
3. Como usuário, quero autorizar cada commit para manter controle sobre o
   histórico do repositório.
4. Como contribuidor, quero um ambiente Python isolado e reproduzível para que
   ferramentas locais não dependam do Python global.
5. Como contribuidor, quero um único gestor de dependências e comandos para que
   instalação e CI usem o mesmo fluxo.
6. Como revisor, quero lint, formato, tipos, testes e cobertura padronizados para
   que qualidade não dependa do ambiente do autor.

## Implementation Decisions

- `to-spec` é obrigatório antes de implementar qualquer feature, bug fix ou
  ajuste de comportamento. A spec precisa existir no diretório numerado do
  projeto e declarar o seam observável de teste.
- Nenhuma implementação começa a partir de pedido solto. Documentação e
  governança também devem registrar uma spec quando alterarem o workflow.
- Cada unidade de trabalho usa branch própria, nomeada por categoria e assunto.
- Nenhum agente pode criar commit sem autorização explícita do usuário para o
  commit específico. Preparar mudanças não implica autorização para commitar.
- `uv` é a única interface permitida para criar ambiente, resolver, instalar,
  adicionar, remover ou executar dependências Python.
- O ambiente do projeto é `.venv`, criado e gerenciado por `uv`; `pip`, Python
  global e ambientes compartilhados não são usados para trabalho do projeto.
- Dependências de desenvolvimento usam o grupo `dev`; o lockfile é versionado.
- Os quality gates permanecem Ruff, mypy strict, pytest e cobertura de branch.

## Testing Decisions

- O seam desta mudança é um checkout limpo do repositório: `uv sync` precisa
  criar o ambiente isolado e os comandos `uv run` precisam localizar todas as
  ferramentas de qualidade.
- Configuração é validada pelo parser TOML e pelo próprio `uv`.
- Um smoke test público valida que o layout `src` instalado pelo ambiente do
  projeto torna o pacote `memory_stale` importável.
- Não se cria teste unitário artificial para arquivos de governança; o teste é
  o fluxo externo de bootstrap e validação do repositório.

## Out of Scope

- Implementar funcionalidades do plugin.
- Criar commit, publicar branch ou abrir pull request.
- Definir CI remoto nesta mudança.

## Further Notes

- Esta spec formaliza regras permanentes do repositório e deve ser aplicada por
  agentes e contribuidores humanos.
