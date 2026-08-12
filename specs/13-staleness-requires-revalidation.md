# 13 — Staleness exige revalidação

## Problem Statement

O produto atualmente associa uma memória a assinaturas estruturais e a marca
como `stale` quando alguma evidência registrada muda. A linguagem pública ainda
permite interpretar esse resultado como prova de que a claim se tornou falsa,
embora o motor apenas consiga provar que a evidência observada deixou de ser a
mesma. A interpretação excessiva enfraquece a tese técnica e esconde tanto
revalidações desnecessárias quanto mudanças semânticas fora das refs registradas.

## Solution

Formalizar `active` e `stale` como estados de validação da provenance, não como
valores de verdade da claim. Uma revisão `active` tem todas as evidências
registradas resolvíveis e com os fingerprints observados na captura. Uma revisão
`stale` teve ao menos uma evidência alterada, removida ou não resolvível e exige
revalidação antes de voltar ao contexto normal. O produto continuará usando os
nomes `active` e `stale`, mas explicará explicitamente que `active` não prova
verdade e `stale` não prova falsidade.

## User Stories

1. Como usuário, quero entender que `stale` significa “requer revalidação”, para que eu não trate o diagnóstico como prova de falsidade.
2. Como usuário, quero entender que `active` significa “evidência registrada inalterada”, para que eu não presuma que o conjunto de evidências é completo.
3. Como mantenedor, quero uma definição única dos estados, para que README, skill, ferramentas MCP, relatório e specs não expressem contratos contraditórios.
4. Como mantenedor, quero preservar a invalidação conservadora, para que uma correção conceitual não reduza silenciosamente a proteção do contexto.
5. Como avaliador do projeto, quero distinguir validade da evidência e verdade semântica, para que os limites científicos do produto sejam verificáveis.
6. Como Codex, quero receber somente revisões `active` no contexto normal, para que claims cuja provenance mudou continuem fora do uso automático.

## Implementation Decisions

- A tese pública do produto será “provenance de memória com revalidação determinística quando a evidência-fonte muda”.
- `active` significa somente que todas as evidências registradas ainda correspondem aos fingerprints observados; não significa que a claim foi provada nem que a provenance está completa.
- `stale` significa que ao menos uma evidência registrada mudou, desapareceu ou não pôde ser resolvida; não significa que a claim foi refutada.
- Mudança estrutural continuará sendo um gatilho conservador de revalidação. Comentários e formatação continuarão fora da assinatura estrutural.
- Revisões `stale` continuarão excluídas do contexto normal e preservadas para auditoria.
- Toda superfície pública que descreva invalidação, validade ou verdade adotará o mesmo vocabulário, incluindo documentação, instruções da skill, descrições MCP e relatório.
- O lifecycle observado não será alterado nesta spec; ela corrige o contrato epistemológico e a linguagem que o apresenta.
- A limitação de provenance incompleta e de dependências não registradas será explícita.

## Testing Decisions

- Seam mais alto confirmado: as superfícies públicas observáveis do plugin e o lifecycle já exercitado pelo harness instalado.
- Esta é uma mudança de contrato e documentação; não será fabricado um teste vermelho para texto editorial.
- Os testes existentes de lifecycle e end-to-end continuarão provando que evidência alterada produz `stale` e que revisões `stale` não entram no contexto.
- Se descrições MCP ou conteúdo renderizado forem alterados de forma estruturada, os testes observarão a resposta pública completa, não funções auxiliares ou chamadas internas.
- A revisão documental verificará que nenhuma superfície afirma que o motor detecta falsidade semântica.

## Out of Scope

- Alterar a identidade de claims ou revisões de evidência.
- Reativar uma claim após revalidação.
- Adicionar novos tipos de evidência ou dependências transitivas.
- Medir taxas de revalidação desnecessária ou mudanças semânticas perdidas.
- Adicionar embeddings, outro LLM, vector database, GraphRAG ou inferência semântica local.

## Further Notes

- Esta spec é pré-requisito conceitual para todas as specs seguintes.
- “Invalidação” permanece aceitável quando seu objeto é a validação da evidência, não a verdade da claim.
