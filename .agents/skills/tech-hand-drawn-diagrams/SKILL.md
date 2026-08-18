---
name: hand-drawn-technical-diagram
description: >
  Creates image-generation prompts for hand-drawn technical diagrams using a
  consistent whiteboard/sketchnote visual language with irregular black ink,
  pastel colors, handwritten typography, simple technical primitives, and
  generous whitespace. Use when the user wants to visualize a system,
  architecture, flow, protocol, concept, or technical explanation.
---

# Hand-Drawn Technical Diagram

Generate image prompts using the visual language defined in this skill.

The visual style is fixed.

The subject, components, relationships, and explanatory narrative come from
the user.

Do not generate the image immediately unless explicitly requested.

## Interaction

When invoked without enough information, ask the user:

> What do you want to illustrate?

After receiving the concept, determine whether the diagram can be composed
without additional information.

If important details are missing, ask only the minimum necessary questions.

Prefer questions such as:

- What are the main components that must appear?
- What relationships or flow should be shown?
- Is there a specific sequence of events?
- Should any component receive special emphasis?
- Should the diagram include a title?

Do not ask questions whose answers can be reasonably inferred from the
concept.

For well-known technical concepts, infer the minimum architecture necessary
to explain them clearly.

Example:

User:

> Kafka consumer group rebalance

The skill should already understand concepts such as brokers, partitions,
consumers, assignments, and rebalance coordination.

Do not force the user to describe the entire architecture.

## Goal

Transform the user's concept into a complete image-generation prompt while
preserving the following visual language.

The result should look like a hand-drawn technical explainer sketched on a
whiteboard or notebook by an engineer while explaining a system.

The image should communicate the concept primarily through spatial
organization, arrows, simple shapes, short labels, and selective color.

## Visual Style Contract

### Core aesthetic

Use:

- white or very light off-white background
- hand-drawn black outlines
- slightly irregular geometry
- simple flat pastel colors
- minimal visual detail
- technical diagram composition
- informal human-made appearance
- clear visual hierarchy
- generous whitespace
- occasional subtle visual humor

Everything should feel intentionally sketched rather than professionally
vectorized.

Overall visual impression:

**technical whiteboard sketch + hand-drawn system diagram + pastel highlights
+ minimal explanatory cartoon**

### Line style

Use black ink-like strokes with visible hand-drawn irregularity.

Lines should:

- have medium-thick black outlines
- wobble slightly
- avoid perfectly straight geometry
- use soft or imperfect corners
- occasionally overshoot intersections
- look manually drawn rather than vector-generated

Arrows should:

- have organic shafts
- sometimes curve around objects
- use manually drawn arrowheads
- vary slightly in shape and length

Avoid polished connector routing.

### Shapes

Build the diagram from simple primitives:

- rounded rectangles
- rectangles
- boxes
- cubes
- cylinders
- capsules
- circles
- blobs
- document sheets
- arrows
- connectors
- simple doodle characters

Reduce every concept to its minimum recognizable visual form.

Examples:

- service or node → rounded rectangle
- broker → container with smaller blocks
- database → cylinder
- file or configuration → irregular sheet of paper
- partition or segment → colored rectangle or cube
- memory or buffer → container holding small tokens
- storage → disk stack
- cluster → group of boxes
- network → loosely connected collection of components

Do not add unnecessary detail.

### Controlled imperfection

Preserve intentional imperfections:

- slightly crooked boxes
- uneven proportions
- imperfect perspective
- fills that do not perfectly match outlines
- natural spacing inconsistencies
- labels that are slightly off-center
- organic arrow curves
- repeated objects that are similar but not identical

The result should feel handmade but not messy or childish.

### Colors

Use black for outlines and text.

Use only a small subset of pastel colors in each image.

Preferred palette:

- turquoise: `#54D6CF`
- light cyan: `#A8E5E3`
- blue: `#6CBDF0`
- light blue: `#B9D7F2`
- pink: `#F064B7`
- light pink: `#F3ADD4`
- green: `#B8E49B`
- yellow: `#F4E58B`
- purple: `#B99AF2`
- coral: `#EF7775`

Use color semantically.

Objects with the same role may share a color.

Different categories may use different pastel colors.

Do not use color merely as decoration.

Avoid:

- gradients
- glossy effects
- complex shading
- realistic lighting
- strong shadows
- neon colors
- large saturated backgrounds

### Typography

All visible text should look handwritten with a black marker.

Typography should have:

- narrow handwritten characters
- slightly inconsistent baselines
- rounded handwritten forms
- high legibility
- medium stroke weight
- informal technical-note appearance

Never use polished UI typography such as:

- Helvetica
- Arial
- Inter
- Roboto
- geometric sans-serif fonts

Text hierarchy:

1. Diagram title
2. Main component labels
3. Relationship labels
4. Small annotations

Prefer short labels.

Avoid paragraphs inside the illustration.

### Composition

Treat the canvas as a technical whiteboard.

Prefer:

- left-to-right flows
- top-to-bottom dependency chains
- clusters of related components
- central concepts surrounded by dependencies
- spatial separation between logical groups

Do not force components into a rigid grid.

Leave substantial whitespace.

The diagram should be understandable within a few seconds.

### Connections

Use hand-drawn arrows as the primary representation of relationships.

Place short handwritten annotations near arrows when useful.

Examples:

- request
- response
- depends on
- publish
- consume
- replicate
- ACK
- commit
- metadata
- read
- write

The arrow and its annotation should behave as one visual element.

### Characters

When a human, developer, consumer, producer, AI, or external actor needs to be
represented, use a minimal doodle character.

Characteristics:

- black outline
- simple blob-like body
- two small eyes
- tiny neutral or slightly amused mouth
- minimal limbs
- intentionally awkward proportions
- no anatomical realism

Characters are explanatory devices, not illustrations.

### Visual hierarchy

The primary concept should be obvious immediately.

Establish hierarchy using:

- size
- proximity
- whitespace
- arrows
- selective pastel color
- handwritten labels

Every prominent visual element should serve an explanatory purpose.

## Prohibited Styles

Do not produce:

- corporate infographics
- PowerPoint-style diagrams
- Figma-perfect vectors
- UML-looking formal diagrams
- polished cloud architecture diagrams
- detailed vendor icons
- photorealism
- realistic illustration
- elaborate 3D
- isometric enterprise diagrams
- glossy surfaces
- gradients
- strong shadows
- detailed textures
- perfect grids
- perfectly uniform spacing
- decorative clutter
- polished typography

## Composition Strategy

Before writing the final prompt, internally identify:

1. the central concept
2. the main actors or components
3. the relationships between them
4. the direction of the explanation
5. the most important interaction
6. which concepts should share colors
7. which details can be removed

Prefer approximately 4–10 major visual objects.

For complex systems, group related objects into larger visual containers
instead of adding excessive individual elements.

The goal is explanation, not exhaustive architecture documentation.

## Final Prompt Construction

After gathering enough information, produce one self-contained image-generation
prompt.

Use this structure:

### Subject

State exactly what the diagram explains.

### Composition

Describe where the major elements appear on the canvas and how the eye should
move through the explanation.

### Components

Describe the required visual objects and their labels.

### Relationships

Describe arrows, direction, sequence, dependencies, requests, responses, or
data movement.

### Visual emphasis

Describe which component or interaction is the primary focus.

### Style

Append the visual style contract in compressed form.

The final prompt must be understandable without access to this skill or to the
original reference images.

## Final Prompt Template

Use the following pattern:

---

Create a hand-drawn technical whiteboard diagram explaining:

**{SUBJECT}**

Composition:

{SPATIAL_COMPOSITION}

Show these main components:

{COMPONENTS}

Show these relationships and interactions:

{RELATIONSHIPS}

The primary visual emphasis should be:

{PRIMARY_FOCUS}

Use short handwritten labels directly beside components and arrows.

Represent technical concepts using minimal visual primitives such as rounded
boxes, cubes, cylinders, document shapes, small containers, arrows, and simple
doodle characters.

Use a white or very light off-white background with generous whitespace.

Draw everything using medium-thick, slightly irregular black marker outlines.
Lines, boxes, arrows, and shapes should look manually drawn, with controlled
imperfections such as slight wobble, uneven proportions, imperfect alignment,
and organic curves.

Use only a few flat pastel accent colors such as turquoise, blue, pink, green,
yellow, and purple. Use color semantically to distinguish component roles.

All typography must resemble neat handwritten marker lettering with slightly
irregular baselines.

Keep the illustration minimal and immediately understandable.

The final result should feel like an engineer explaining the system on a
whiteboard using a black marker and several pastel markers.

Avoid polished vector graphics, corporate infographics, PowerPoint aesthetics,
Figma-perfect geometry, gradients, realistic lighting, shadows, photorealism,
detailed vendor icons, precise grids, 3D rendering, and polished typography.

---

Return only the completed image-generation prompt unless the user explicitly
asks for explanation or alternatives.
