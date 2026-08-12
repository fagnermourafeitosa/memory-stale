# 15 — Corpus de avaliação de staleness

## Problem Statement

O lifecycle usa mudança estrutural como proxy conservador de revalidação, mas o
projeto ainda não mede quando esse proxy reage a mudanças semanticamente
irrelevantes nem quando deixa de reagir porque a mudança ocorreu fora da
evidência registrada. Sem um corpus rotulado, decisões sobre granularidade,
evidence sets ou dependências transitivas permanecem anedóticas e não há baseline
para avaliar se a arquitetura melhora o diferencial do produto.

## Solution

Adicionar um corpus pequeno, versionado e revisável de cenários before/after com
claims, evidências registradas, resultado semântico rotulado e resultado esperado
do lifecycle. Um avaliador determinístico calculará métricas separadas para
revalidações semanticamente desnecessárias e mudanças semânticas não detectadas.
As labels serão exemplos independentes escritos por humanos; nenhum LLM será
chamado para julgar verdade durante a avaliação.

## User Stories

1. Como mantenedor, quero medir revalidações desnecessárias, para que eu conheça o custo da heurística conservadora.
2. Como mantenedor, quero medir mudanças semânticas perdidas, para que eu conheça o risco de provenance incompleta.
3. Como contribuidor, quero cenários reproduzíveis, para que uma mudança no indexador ou lifecycle possa ser comparada ao baseline.
4. Como avaliador, quero separar comportamento determinístico e verdade rotulada, para que as métricas não confundam contrato com semântica.
5. Como mantenedor, quero cobrir todas as gramáticas suportadas, para que melhorias não sejam inferidas a partir de uma única linguagem.
6. Como usuário, quero que instrumentation e refactors equivalentes apareçam nas medições, para que casos comuns de falso stale sejam visíveis.
7. Como usuário, quero que mudanças em dependências e configuração apareçam nas medições, para que falsos negativos arquiteturais sejam visíveis.
8. Como contribuidor, quero atualizar deliberadamente labels e baselines, para que regressões não sejam escondidas por expectativas recomputadas.

## Implementation Decisions

- Cada cenário conterá estado anterior, estado posterior, claim independente, evidence snapshot registrado e uma label semântica `preserved` ou `changed`.
- A expectativa semântica será literal e revisada; nunca será calculada pelo mesmo algoritmo usado pelo produto.
- O avaliador executará o lifecycle público sobre os fixtures e registrará se a revisão permaneceu `active` ou passou a `stale`.
- A métrica `unnecessary_revalidation_rate` contará claims rotuladas `preserved` que o motor marcou `stale`.
- A métrica `missed_semantic_change_rate` contará claims rotuladas `changed` que o motor manteve `active`.
- As métricas semânticas avaliarão trade-offs do produto; elas não redefinirão `stale` como falso nem tornarão uma revalidação conservadora um bug por si só.
- O corpus cobrirá, no mínimo, instrumentation, logging, métricas, refactor equivalente, mudança de literal relevante, mudança de controle de fluxo, rename/delete, mudança em dependência indireta, configuração, comentários e formatação.
- Cada gramática suportada terá fixtures de mudança preservadora e mudança semântica local. Casos transversais poderão começar pelas linguagens que expressem melhor o cenário, sem alegar cobertura universal.
- Resultados baseline serão versionados e mudanças deverão ser explicadas junto com alterações intencionais do comportamento.
- O avaliador será uma superfície de desenvolvimento/teste e não um CLI humano como superfície primária do produto.
- O corpus não chamará outro modelo, não usará embeddings e não dependerá de rede.

## Testing Decisions

- Seam mais alto confirmado: avaliador determinístico consumindo o corpus versionado e o lifecycle público, executado pela suíte normal do projeto.
- O schema do corpus será validado com mensagens acionáveis para cenário incompleto, label inválida ou evidence locator inconsistente.
- Testes provarão as fórmulas com um conjunto mínimo de resultados literais, sem recomputar expectativas pelo algoritmo de produção.
- Um cenário de instrumentation deverá demonstrar revalidação semanticamente desnecessária no baseline estrutural.
- Um cenário de política MFA indireta deverá demonstrar mudança semântica perdida enquanto somente a ref local estiver registrada.
- Fixtures de comentários e formatação continuarão comprovando ausência de mudança estrutural para todas as gramáticas suportadas.
- A suíte deverá distinguir regressão mecânica do lifecycle de mudança deliberada nas métricas semânticas.

## Out of Scope

- Otimizar automaticamente o lifecycle para melhorar as métricas.
- Usar um LLM como juiz das labels.
- Definir thresholds de qualidade como promessa pública antes de existir baseline.
- Adicionar evidence sets, tipos de evidência ou dependency graph.
- Medir qualidade de retrieval lexical ou semântico.
- Transformar o avaliador em serviço, dashboard remoto ou CLI principal.

## Further Notes

- Esta spec depende das definições da spec 13 e deve executar sobre o modelo revisionado da spec 14.
- O corpus orientará a prioridade das specs seguintes sem bloquear a correção já conhecida de evidence revisions.
