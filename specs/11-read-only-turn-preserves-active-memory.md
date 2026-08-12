# 11 — Preservar memória ativa em turno somente leitura

## Problem Statement

Uma memória recém-capturada e recuperada corretamente foi marcada como `stale`
ao final de um turno que não modificou seu símbolo. O caso ocorre quando o
histórico contém uma memória stale anterior para o mesmo ref: sua assinatura
histórica sobrescreve a evidência da memória ativa. Isso produz falso positivo,
remove conhecimento válido dos turnos seguintes e degrada a recuperação.

## Solution

Garantir que o ciclo de hooks compare somente mudanças ocorridas depois do
snapshot do `UserPromptSubmit`. Um `Stop` sem alteração no arquivo referenciado
deve preservar a assinatura, o status `active` e a elegibilidade da memória
para recuperação.

## User Stories

1. Como usuário, quero consultar memória sem invalidá-la para que leitura não
   seja confundida com mudança semântica.
2. Como agente, quero receber apenas a versão ativa mais recente para não usar
   fatos obsoletos.
3. Como mantenedor, quero um teste de regressão no ciclo público de hooks para
   detectar falsos positivos de staleness.

## Observable Test Seam

O seam confirmado é o ciclo público `UserPromptSubmit → Stop`, executado pelos
comandos reais de hook em um repositório Git temporário. O arquivo referenciado
já estará modificado antes do início do turno e haverá uma memória stale e uma
ativa para o mesmo ref, reproduzindo o estado de trabalho real. O arquivo
permanecerá byte a byte igual entre os dois hooks.

## Expected Behavior

- Uma memória ativa cuja assinatura corresponde ao símbolo atual continua
  `active` após um turno somente leitura.
- Mudanças preexistentes no worktree não são atribuídas ao turno atual.
- A memória continua sendo recuperada para uma consulta pelo ref exato.
- Memórias stale continuam excluídas e consultas sem relação continuam vazias.

## Implementation Constraints

- Git continua obrigatório e é a única fonte de identidade do worktree.
- Não enfraquecer a detecção de mudanças semânticas feitas durante o turno.
- Não adicionar estado global, heurística semântica ou chamadas a outro LLM.
- Manter hooks não bloqueantes e writes atômicos.

## Testing Decisions

- Primeiro teste: arquivo tracked já dirty, uma memória stale com assinatura
  anterior e uma ativa assinada contra o conteúdo atual, ciclo de hooks sem
  novas edições; observar falha antes da correção e depois exigir que somente a
  memória atual permaneça `active` e recuperável.
- Executar o teste focado em red e green, a suíte relevante e todos os gates.
- Repetir a validação no plugin instalado após atualizar seu cachebuster.

## Out of Scope

- Alterar o ranking BM25, o orçamento de contexto ou a identidade de memórias.
- Remover o histórico stale.
- Criar fallback para arquivos fora do Git ou linguagens não suportadas.
