# 03 — Indexação tree-sitter multilíngue

## Problem Statement

Memória deve acompanhar símbolos em qualquer projeto suportado, sem invalidar por formatação e sem fallback impreciso.

## Solution

Criar indexadores tree-sitter que resolvem símbolos e produzem assinaturas estruturais canonizadas.

## User Stories

1. Como desenvolvedor, quero rastrear função/classe equivalente em linguagens diferentes.
2. Como desenvolvedor, quero editar comentário sem tornar memória stale.
3. Como usuário, quero erro claro para linguagem não suportada.

## Implementation Decisions

- V1: TypeScript, JavaScript, Python, Go, Java, Kotlin e Rust.
- Assinatura inclui estrutura e tokens reais; ignora whitespace e comentários.
- Símbolo mudado, removido, renomeado ou arquivo removido produz resultado inequívoco.
- Linguagem sem gramática rejeita captura; nunca degrada para arquivo inteiro.
- Interface comum permite adicionar gramáticas sem alterar lifecycle.

## Testing Decisions

- Seam confirmado pela autorização de execução contínua: a interface pública do
  indexador recebe raiz Git e ref `path:symbol`, retornando uma assinatura ou
  erro estruturado; fixtures reais exercitam cada gramática.
- Fixtures por linguagem para resolução, mudança semântica e mudança de comentário/formatação.
- Testar símbolo ausente, parser inválido e arquivo ausente.
- Testar que hash igual para trivia e diferente para mudança de lógica, assinatura, identificador ou literal.

## Out of Scope

- Suporte a outras linguagens e parsing tolerante a sintaxe quebrada.

## Further Notes

- Este módulo não decide se um claim é relevante; apenas prova estado de refs.
