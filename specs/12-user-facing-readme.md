# 12 — README orientado ao usuário final

## Problem Statement

O README descreve bem a arquitetura, mas não oferece uma jornada clara de
adoção. Faltam pré-requisitos, instalação local, primeiro uso, configuração
completa e uma forma simples de verificar que recuperação e staleness estão
funcionando. Algumas descrições também divergem do produto implementado.

## Solution

Reorganizar o README como página pública de produto: começar pelo resultado
para o usuário, apresentar um exemplo curto, explicar instalação e uso normal,
e mover detalhes internos para depois. Corrigir o contrato dos hooks e dos três
MCP tools e separar funcionalidades entregues do roadmap futuro.

## User Stories

1. Como usuário, quero entender rapidamente o valor do plugin e instalá-lo sem
   conhecer sua arquitetura interna.
2. Como usuário, quero saber onde a memória fica, o que devo versionar e como
   verificar recuperação e staleness.
3. Como usuário avançado, quero configurar orçamento e relatório com exemplos
   copiáveis.
4. Como potencial contribuidor, quero distinguir estado atual, limitações e
   trabalhos futuros reais.

## Observable Test Seam

O seam mais alto é o próprio `README.md` renderizado como contrato público. A
revisão verificará que comandos, caminhos, configuração, linguagens, hooks,
MCP tools, estados e defaults correspondem aos manifests e ao código atual.

## Expected Behavior

- A proposta de valor e o fluxo automático ficam claros antes dos detalhes.
- Pré-requisitos e instalação local não prometem uma distribuição pública que
  ainda não existe.
- O README inclui primeiro uso, verificação, configuração e versionamento.
- Os três MCP tools e a divisão entre julgamento do Codex e validação
  determinística são descritos corretamente.
- O roadmap contém apenas trabalho ainda não entregue.

## Implementation Constraints

- Manter o README em inglês como a documentação pública existente.
- Não introduzir um CLI humano como superfície principal.
- Não prometer release público, fallback por arquivo, embeddings ou outro LLM.
- Não inventar comandos de marketplace que dependam de publicação inexistente.
- Preservar Git, `uv`, armazenamento local e as limitações de linguagens.

## Testing Decisions

- Mudança exclusivamente documental: não fabricar teste red-green.
- Conferir links, headings, exemplos TOML, caminhos, nomes de tools e defaults
  por busca textual e comparação com o código.
- Executar `ruff format --check`, `ruff check`, mypy e pytest para garantir que
  a documentação não acompanha alterações acidentais de produção.

## Out of Scope

- Publicar marketplace ou release.
- Alterar manifest, runtime, configuração, ranking ou lifecycle.
- Criar site, screenshots, vídeo ou documentação externa.
