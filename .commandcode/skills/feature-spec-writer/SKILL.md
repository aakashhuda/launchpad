---
name: feature-spec-writer
description: Turn a raw feature idea (typed inline or given as a file of one or more paragraphs) into a concise, structured feature specification grounded in the available project context and existing conventions.
argument-hint: idea-file-path-or-inline-text
---

# Feature Spec Writer

Converts a feature idea into a project-grounded feature specification.

The skill should work across different coding agents, repositories, languages, frameworks, databases, and architectural styles. Do not assume a particular agent, stack, framework, ORM, frontend library, directory structure, or development workflow unless the project context establishes it.

## Hard requirement: Plan Mode only

Check whether the session is currently in Plan Mode before doing anything else.

- **Not in Plan Mode:** Stop. Tell the user this skill is designed to run in Plan Mode
  (so the spec can be reviewed before anything is written to disk) and ask them to
  switch (Shift+Tab to cycle modes, or `/plan`) and re-issue the request. Do not read
  the idea, explore the repo, or draft anything yet.
- **In Plan Mode:** Continue with the workflow below. Plan Mode already prevents file
  writes and most commands, so steps 1–3 (read-only research and drafting) are safe to
  do freely. The actual file write happens only in step 4, after the user approves the
  plan and Plan Mode is exited.

## Workflow

### Idea File Path or Inline Text

Idea or idea file path: `$ARGUMENTS`

If `$ARGUMENTS` is empty, abort and display:

`Error! This skill needs a idea file path or inline`

### 1. Get the idea

- If the user provided the idea inline, use that text directly.
- If they pointed to a file, read the referenced file.
- Treat the entire idea file as the source idea, not only its first paragraph.
- If the idea is too ambiguous or incomplete to determine the intended feature scope, ask one concise clarifying question rather than guessing.

### 2. Understand the project context

Before drafting the specification, inspect enough of the available project context to make the specification consistent with the project.

Look for relevant sources such as:

- Project overview or README files
- Existing architecture or design documentation
- Coding conventions or standards
- Existing plans, specifications, or feature documentation
- Relevant source modules and similar existing functionality
- Existing tests and validation patterns
- Existing database/schema conventions
- Existing API, UI, service, or integration patterns

Use the project's actual terminology and conventions where they are available.

Do not perform an exhaustive codebase audit. Research only enough to understand:

- Where the feature belongs
- Which existing components or modules are relevant
- What implementation patterns already exist
- What constraints or conventions the feature should follow
- What related documentation should be referenced

Do not invent technologies, architecture, files, modules, or conventions that are not supported by the project context or the feature idea.

### 3. Determine the implementation scope

Translate the idea into concrete, implementation-oriented requirements.

The requirements should describe:

- What needs to be created or changed
- Important domain or business rules
- Data/model/schema changes when applicable
- API, service, UI, background-job, integration, or infrastructure changes when applicable
- Validation and integrity rules
- Important operational considerations
- Testing or verification expectations when relevant
- Relevant project conventions that the implementation should follow

Be specific enough that another developer or coding agent can use the specification as an implementation guide.

Avoid prescribing a technology when the project does not already establish one.

### 4. Create the feature specification

Create a concise Markdown feature specification.

Use the following structure exactly:

```markdown
# Phase/Feature Name

## Overview

2-4 sentences describing what this phase or feature establishes, why it is needed, and the high-level implementation direction.

## Requirements

- Concrete, testable implementation requirements.
- Group related requirements logically.
- Include relevant implementation details and constraints.
- Use project-specific paths, modules, technologies, or conventions only when supported by the project context.

## References

- Relevant project documents
- Relevant existing source files/modules
- Related plans or specifications
- External documentation when it is directly relevant

## Notes

- Important assumptions
- Scope boundaries
- Edge cases
- Validation expectations
- Design considerations
- Items intentionally deferred to later work
```

### Output style

The specification should resemble a practical implementation phase/specification document rather than a generic product brief.

Prefer:

- Concrete implementation requirements
- Short, scannable bullets
- Explicit constraints
- Existing project terminology
- References to real project artifacts
- Clear scope boundaries
- Useful validation or migration considerations where applicable

Avoid:

- Long narrative explanations
- Generic filler
- Unsupported technology choices
- Agent-specific instructions
- Assumptions about a particular programming language or framework
- Repeating information already obvious from the feature title

The specification should normally be understandable and scannable within a few minutes.

### 5. References

Only include references that are actually relevant to the specification.

References may include:

- Project documentation
- Existing implementation files
- Related feature specifications
- Related plans
- Architecture/design documents
- Official technology documentation

Do not require or automatically include the generated plan/specification itself as a reference.

Do not invent external links. If a relevant external documentation URL is already available from the project context or source material, it may be included.

### 6. Completion

After creating the specification:

- Notify the user that the feature specification has been created.
- Mention the created file/path.
- If there are important assumptions or unresolved questions, surface them briefly.
- If the project has an established command or workflow for loading/reviewing the specification, suggest it only when that workflow is actually present in the project context.
