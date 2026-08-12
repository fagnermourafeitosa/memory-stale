# 14 — Claims com revisões versionadas de evidência

## Problem Statement

A identidade persistida atual combina kind, claim normalizada e refs, mas não
inclui os fingerprints da evidência. Depois que uma memória fica `stale`, uma
captura semanticamente idêntica com as mesmas refs e uma implementação nova
produz o mesmo ID e é descartada como conhecida. O produto não consegue
representar que a mesma claim foi sustentada por revisões diferentes ao longo do
tempo nem restaurá-la ao contexto sem perder o histórico anterior.

## Solution

Separar a identidade estável da claim da identidade imutável de cada revisão de
evidência. A mesma claim poderá acumular revisões históricas, das quais no máximo
uma será a revisão corrente `active`. Uma nova captura com fingerprints novos
criará outra revisão, preservará as anteriores e tornará a claim novamente
elegível para retrieval. O armazenamento Markdown receberá `schema_version` e
uma migração determinística do formato pre-alpha existente.

## User Stories

1. Como usuário, quero revalidar a mesma claim após uma mudança irrelevante, para que conhecimento ainda útil volte ao contexto.
2. Como usuário, quero preservar cada revisão anterior, para que a evolução da evidência permaneça auditável em Git.
3. Como Codex, quero recapturar a mesma claim e o mesmo escopo com fingerprints novos, para que a deduplicação não bloqueie uma revalidação legítima.
4. Como Codex, quero que repetir exatamente a mesma revisão seja idempotente, para que hooks repetidos não criem duplicatas.
5. Como mantenedor, quero separar `claim_id` e `revision_id`, para que identidade semântica e observação histórica não sejam o mesmo objeto.
6. Como mantenedor, quero um schema versionado, para que futuras mudanças do Markdown tenham migrações explícitas.
7. Como usuário de uma instalação existente, quero que memórias do formato anterior continuem legíveis, para que o upgrade não perca histórico.
8. Como usuário, quero que retrieval mostre uma claim apenas uma vez, usando sua revisão `active`, para que o histórico não polua o contexto.
9. Como auditor, quero ver commit e instante observados quando disponíveis, para que eu possa relacionar uma revisão ao estado do repositório.

## Implementation Decisions

- O modelo durável terá uma entidade lógica de claim e uma ou mais revisões imutáveis de evidência.
- `claim_id` será determinístico a partir de kind, claim normalizada e escopo canônico. Nesta etapa, o escopo canônico é o conjunto ordenado de locators de símbolo atualmente representado por refs.
- `revision_id` será determinístico a partir de `claim_id` e do conjunto ordenado de fingerprints da evidência.
- Repetir uma captura com o mesmo `revision_id` será idempotente.
- Capturar a mesma claim e escopo com fingerprints diferentes criará uma nova revisão, mesmo que exista uma revisão `stale` anterior.
- No máximo uma revisão será corrente `active` para cada `claim_id`. Ao aceitar uma nova revisão, qualquer revisão anteriormente corrente será preservada fora do contexto normal.
- O status pertence à revisão de evidência. A claim é elegível para retrieval somente quando possui uma revisão corrente `active`.
- O armazenamento continuará em Markdown, auditável e diffável, e usará `revision_id` para impedir colisão entre arquivos históricos.
- Todo registro persistido terá `schema_version`. Documentos sem versão serão interpretados como o schema legado da versão pre-alpha.
- A migração será determinística, não destrutiva e idempotente. IDs legados permanecerão disponíveis como provenance de migração quando diferirem dos novos IDs.
- A revisão armazenará metadados de observação determinísticos disponíveis no repositório, incluindo commit quando houver. Timestamp será metadado e nunca participará da deduplicação.
- A escrita do corpus reconciliado continuará atômica e não deixará claims ou revisões parcialmente gravadas.
- O relatório mostrará o agrupamento por claim e o histórico de revisões; o contexto normal continuará recebendo somente a revisão corrente `active`.

## Testing Decisions

- Seam mais alto confirmado: servidor MCP real e hooks reais em repositório Git temporário, observando captura, Markdown persistido, staleness, recaptura e retrieval.
- Primeiro slice comportamental: capturar uma claim, alterar seu símbolo, observar a revisão antiga `stale`, recapturar exatamente a mesma claim/refs e observar uma revisão nova `active` no contexto.
- O teste inicial deverá falhar no comportamento atual porque a deduplicação pelo ID legado descarta a recaptura.
- Slices seguintes cobrirão idempotência da mesma revisão, agrupamento no retrieval, preservação de histórico e uma única revisão corrente.
- Fixtures legadas sem `schema_version` provarão leitura, migração idempotente e ausência de perda de claim, status, razões e signatures.
- O store será testado pelo diretório Markdown público; IDs, agrupamentos e metadados serão observados no documento persistido, sem mocks de módulos do projeto.
- Testes usarão commits reais em repositórios Git temporários para validar provenance de commit.

## Out of Scope

- Alterar quais evidências podem ser associadas a uma claim.
- Permitir refs de suporte que não mudaram no turno.
- Evidência de configuração, schema ou teste como tipos próprios.
- Dependency graph ou descoberta automática de dependências.
- Deduplicação semântica entre claims com redações diferentes.
- Reparação automática de claims sem captura explícita do Codex atual.

## Further Notes

- Esta spec depende do significado de `stale` definido na spec 13.
- A migração ocorre antes de qualquer expansão para evidence sets, para que as specs seguintes tenham uma base versionada.
