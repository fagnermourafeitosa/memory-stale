# 17 — Grafo explícito de dependências da evidência

## Problem Statement

Evidence sets planos conseguem registrar várias fontes, mas repetem manualmente
toda dependência em cada claim e não explicam por que uma evidência indireta a
sustenta. Uma claim ligada a `AuthService.login` pode depender de uma policy que,
por sua vez, depende de configuração ou de outra policy. Sem relações explícitas,
o produto não consegue percorrer essa provenance nem reutilizar dependências já
declaradas. Construir um call graph automático agora, porém, exigiria resolução
semântica que tree-sitter sozinho não oferece de forma confiável nas sete
linguagens.

## Solution

Adicionar um evidence dependency graph explícito e local. Claims terão relações
`supported_by` com evidence items, e evidence items poderão declarar
`depends_on` para outros evidence items. O Codex atual fornecerá as relações ao
capturar conhecimento; o core apenas validará locators, registrará fingerprints e
percorrerá o grafo deterministicamente. Uma alteração em qualquer evidence item
alcançável exigirá revalidação da revisão dependente.

## User Stories

1. Como usuário, quero que uma mudança em dependência transitiva registrada torne a revisão stale, mesmo quando o símbolo local permaneceu igual.
2. Como auditor, quero saber o caminho de provenance que liga a claim à evidência alterada, para que a razão de revalidação seja explicável.
3. Como Codex, quero declarar que uma policy depende de outra policy ou configuração, para que a relação seja reutilizável e não fique escondida na prosa.
4. Como mantenedor, quero travessia determinística e segura em ciclos, para que grafos reais não bloqueiem hooks.
5. Como mantenedor, quero validar todos os nós antes de persistir relações, para que arestas quebradas não criem confiança artificial.
6. Como usuário, quero que Dream audite dependências transitivas, para que mudanças ocorridas fora do turno atual também sejam encontradas.
7. Como usuário, quero que o relatório mostre paths de invalidação, para que o grafo tenha valor operacional e não apenas estrutural.
8. Como mantenedor, quero medir o efeito do grafo no corpus existente, para que maior cobertura não esconda crescimento descontrolado de revalidações.
9. Como avaliador, quero que o projeto continue sendo provenance determinística, para que o grafo não seja confundido com GraphRAG ou retrieval semântico.

## Implementation Decisions

- O grafo terá nós de claim revision e evidence items tipados, com arestas dirigidas `supported_by` e `depends_on`.
- Arestas serão declaradas pelo Codex que já realiza o julgamento semântico da captura. O motor local não inferirá significado nem chamará outro modelo.
- Todo nó de evidência persistido terá locator resolvível e fingerprint pelo adapter de seu tipo.
- Uma revisão será `active` somente quando todos os evidence items alcançáveis a partir de suas arestas `supported_by` corresponderem aos fingerprints registrados.
- Mudança, remoção ou falha de resolução em nó alcançável tornará a revisão `stale` e registrará ao menos um path determinístico da claim até o nó afetado.
- A travessia terá ordenação canônica, conjunto de visitados e comportamento finito diante de ciclos. Ciclos não alterarão o resultado pela ordem de visita.
- A captura ou atualização de relações será atômica: nós ausentes, tipos incompatíveis e arestas malformadas rejeitarão o conjunto inteiro.
- Dependências compartilhadas poderão ser referenciadas por identidade canônica, mas cada evidence revision preservará o snapshot de fingerprints que a validou.
- Hooks farão auditoria direcionada aos itens tocados no turno e às revisões reversamente alcançáveis. Dream continuará oferecendo auditoria ampla.
- O relatório apresentará claims, revisões, nós, arestas e paths de staleness sem se tornar a superfície primária de edição.
- O armazenamento continuará Git-native e Markdown. Índices derivados para travessia reversa poderão ser reconstruídos e não serão fonte de verdade.
- O corpus da spec 15 comparará o baseline plano e o grafo, incluindo revalidação desnecessária e mudança semântica perdida.
- A feature será descrita como evidence/provenance graph, nunca como knowledge graph semântico ou GraphRAG.

## Testing Decisions

- Seam mais alto confirmado: captura MCP real de uma revisão com dependência transitiva, alteração apenas do nó folha, execução de Stop ou Dream e observação do Markdown, contexto e relatório.
- Primeiro slice comportamental: `login supported_by authentication policy depends_on MFA policy`; mudar somente MFA policy deverá marcar a revisão de login `stale` e registrar o path completo.
- O teste inicial deverá falhar com evidence sets planos que não incluam explicitamente o nó folha na revisão da claim.
- Slices seguintes cobrirão dependência compartilhada por múltiplas claims, ciclos, nó removido, locator quebrado, atualização de aresta e ordenação determinística.
- Testes usarão arquivos e repositórios Git reais; apenas fronteiras externas verdadeiras poderão ser simuladas.
- A auditoria direcionada e Dream deverão produzir o mesmo estado final para o mesmo grafo.
- Testes observarão paths e estados públicos, não ordem de chamadas, representação interna de adjacency ou funções privadas.
- O corpus de avaliação deverá registrar a variação das duas métricas antes que o grafo seja considerado melhoria concluída.

## Out of Scope

- Descobrir automaticamente call graphs, imports, dispatch dinâmico ou dataflow.
- Consultar language servers, compiladores remotos ou serviços de indexação.
- GraphRAG, embeddings, vector database ou ranking por passeio no grafo.
- Tratar o grafo como prova de completeness da provenance ou de verdade da claim.
- Editar o grafo por uma interface humana dedicada.
- Adicionar fallback por arquivo ou suporte genérico a formatos desconhecidos.

## Further Notes

- Esta spec depende de claims revisionadas, métricas baseline e evidence sets tipados das specs 14, 15 e 16.
- A implementação só deverá avançar se o corpus demonstrar benefício adicional sobre evidence sets planos proporcional ao custo e à taxa de revalidação.
