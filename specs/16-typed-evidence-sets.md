# 16 — Evidence sets tipados

## Problem Statement

Uma claim pode depender de mais de um símbolo ou de estado estruturado fora do
símbolo alterado. O contrato atual permite várias refs, mas exige que todas tenham
mudado no turno, impedindo registrar dependências de suporte intactas. Ele também
trata toda evidência como símbolo de código, sem representar explicitamente
configuração, schemas ou testes. Isso mantém claims `active` quando uma fonte de
suporte não registrada muda.

## Solution

Substituir o conjunto implícito de refs por um evidence set explícito e tipado em
cada revisão. Evidências terão locator, fingerprint, tipo e papel. Pelo menos uma
evidência `primary` deverá ter mudado durante o turno; evidências `supporting`
precisarão resolver e serão fingerprintadas mesmo quando não tiverem mudado. A
revisão exigirá revalidação quando qualquer item registrado divergir.

## User Stories

1. Como Codex, quero ancorar uma claim no símbolo alterado e em símbolos de suporte intactos, para que mudanças futuras em qualquer suporte sejam detectadas.
2. Como usuário, quero que uma mudança em configuração registrada torne a revisão stale, para que comportamento controlado fora do método não permaneça implícito.
3. Como usuário, quero registrar um schema estruturado como evidência, para que mudanças de contrato de dados exijam revalidação.
4. Como mantenedor, quero distinguir evidência primária e de suporte, para que a regra de elegibilidade da captura continue rigorosa sem exigir que tudo mude no turno.
5. Como auditor, quero ver tipo, papel, locator e fingerprint de cada evidência, para que a provenance seja legível.
6. Como usuário, quero que testes relevantes possam ser evidência explícita, para que a remoção ou alteração do cenário de proteção exija revalidação.
7. Como mantenedor, quero rejeitar formatos e locators não suportados, para que não surja um fallback impreciso por arquivo.
8. Como usuário de memórias existentes, quero que refs legadas sejam migradas para evidências primárias de símbolo, para que o histórico continue utilizável.
9. Como Codex, quero receber erros por item inválido, para que uma evidence set parcialmente resolvida nunca seja capturada como válida.

## Implementation Decisions

- Cada revisão conterá um conjunto canônico de `EvidenceItem` com `type`, `role`, `locator` e `fingerprint`.
- Os papéis serão `primary` e `supporting`. Pelo menos um item `primary` deverá ter mudado no turno ativo; itens `supporting` não precisarão ter mudado.
- Todos os itens deverão resolver no estado final antes da captura. A captura será rejeitada atomicamente se qualquer item for inválido.
- Tipos suportados serão `symbol`, `config`, `schema` e `test`.
- `symbol` continuará usando resolução tree-sitter e assinatura estrutural do símbolo, sem fallback por arquivo.
- `test` resolverá uma função ou método de teste como símbolo estrutural, mas manterá tipo próprio para explicar seu papel de provenance.
- `config` apontará para um nó exato em documento JSON, YAML ou TOML por locator estruturado. O fingerprint será calculado sobre a representação canônica do nó, ignorando formatação e comentários.
- `schema` apontará para um nó exato de JSON Schema ou OpenAPI em JSON ou YAML. O fingerprint será calculado sobre a representação canônica do nó selecionado.
- Documento inteiro, formato não suportado, parse inválido ou locator inexistente serão rejeitados; não haverá fallback para hash bruto do arquivo.
- Mudança, remoção ou impossibilidade de resolver qualquer item registrado tornará a revisão `stale`, com razão por evidence item.
- A identidade da claim usará somente o escopo das evidências `primary`; adicionar ou trocar suporte produzirá nova evidence revision da mesma claim quando o escopo primário permanecer igual.
- A ordem fornecida dos itens não afetará IDs, comparação nem resultado.
- O schema legado de refs será migrado para itens `symbol` com papel `primary`.
- Skill, MCP, Markdown, Dream e relatório usarão o mesmo modelo tipado e mostrarão razões acionáveis por item.

## Testing Decisions

- Seam mais alto confirmado: chamada MCP real em repositório Git temporário, seguida por hooks ou Dream, persistência Markdown e observação do status final.
- Primeiro slice comportamental: alterar o símbolo primário, capturar uma claim com um símbolo de suporte intacto, mudar somente o suporte em turno posterior e observar a revisão `stale`.
- O teste inicial deverá falhar sob o contrato atual porque uma ref intacta não pode participar da captura.
- Slices seguintes cobrirão configuração, schema e teste com alterações semânticas e mudanças apenas de formatação/comentários quando o formato permitir.
- Cada tipo terá fixtures válidos, locator inexistente, parse inválido, remoção e canonicalização independente.
- Testes confirmarão rejeição atômica de evidence sets parcialmente inválidos e razões de staleness por item.
- A migração de refs legadas será exercitada através do store público e do fluxo instalado.
- Os sete indexadores continuarão usando fixtures reais para itens `symbol` e `test` suportados.

## Out of Scope

- Inferir automaticamente quais evidências sustentam uma claim.
- Criar ou percorrer relações `depends_on` entre evidence items.
- Suportar hashes de arquivo inteiro, regiões arbitrárias de texto ou linguagens não suportadas.
- Interpretar semanticamente o conteúdo de uma configuração ou schema.
- Adicionar SQL, banco vetorial, serviço remoto ou outro LLM.
- Usar evidence types para ranking semântico de retrieval.

## Further Notes

- Esta spec depende do schema revisionado da spec 14 e deve ser avaliada com o corpus da spec 15.
- Evidence sets planos entregam invalidação por múltiplas fontes antes do custo de um grafo.
