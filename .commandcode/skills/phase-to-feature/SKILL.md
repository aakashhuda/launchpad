---
name: phase-to-feature
description: Generate a feature spec file for a given phase number from context/phases.md. Validates that all prior phases are complete (via git tags) before allowing the spec to be written. The spec is grounded in project context and written as a concrete, implementation-ready document.
argument-hint: <phase-number>
---

# Phase Feature Spec Generator

Generates a feature spec file in `@context/features/` for a single development
phase from `@context/phases.md`. A phase is treated as a feature: the spec
file captures the phase's goal, tasks, and done-when criteria so the work can
be picked up and tracked via the existing `feature` skill workflow.

## Harness compatibility

This skill is harness-agnostic and works with any coding agent (Claude Code,
Codex, Cursor, Gemini CLI, etc.).

- **Agent instruction file:** wherever this skill says "the agent
  instruction file", use whichever of these exists at the repository root,
  in this order: `AGENTS.md`, then `CLAUDE.md`. If both exist, read both
  (one is often a pointer to the other). If neither exists, note this in
  the spec's **Notes** and continue; do not create or modify either file.
- **Path notation:** paths written with a leading `@` (e.g.
  `@context/phases.md`) are project-relative; the `@` is notation only and
  can be dropped if the harness doesn't use it.
- **Arguments:** the phase number comes from `$ARGUMENTS` where the harness
  supports it, otherwise from the user's message.
- **Invoking the `feature` skill:** use the harness's own mechanism (a slash
  command, skill call, or plain-language request).

## When to use

Invoke this skill when you want to start the next unit of work in the phased
build plan (see `context/phases.md`). It produces the input that the
`feature` skill (load/start/review/complete) operates on.

## Argument

A single integer, passed as the skill argument: the phase number to start (e.g. `0`, `2`, `7`).

If no argument is given, or it isn't a non-negative integer, explain the
expected usage and stop.

## Workflow

1. **Parse the phase number** from the skill argument (`$ARGUMENTS`).
   Validate it's a non-negative integer.

2. **Read `@context/phases.md`** and locate the section whose heading is
   `## Phase N — <title>` (matching the requested number). Extract:
   - The phase title (after the em dash)
   - The **Goal** paragraph(s)
   - The bullet list under **Tasks**
   - The bullet list under **Done when** (treat these as the testable
     acceptance criteria)

   If no matching phase section exists, stop with an error listing the valid
   phase numbers found in the file.

3. **Validate prior-phase completion.** For each phase number `0` through
   `N-1`, the corresponding git tag `phase-N-complete` (per
   `context/git-conventions.md`) must exist on the current repository:
   - If any prior phase is missing its tag, stop with a clear message:
     `Phase {X} is not marked complete (missing tag phase-X-complete).`
     List every missing prior phase so the user can see the full gap.
   - **Exception — Phase 0:** if no git repository exists yet (`.git`
     absent), treat Phase 0 as the implicit starting point and skip the tag
     check. This matches the project's intent that Phase 0 is the scaffold
     commit that initializes git (see `git-conventions.md` → "Repository
     setup").

4. **Derive a kebab-case slug** from the phase title. Lowercase, replace
   any run of non-alphanumeric characters with a single hyphen, trim
   leading/trailing hyphens. Example: `Data layer in mock mode` →
   `data-layer-in-mock-mode`.

5. **Generate the spec file** at
   `@context/features/phase-{N}-{slug}-spec.md`.

   Before drafting, apply the **Output reasoning** rules below (project
   context grounding, scope translation, style, and reference selection).
   Then write the file using this structure **exactly**, in this section
   order (consistent with `@context/docs/plans/how-feature-spec-made.md`):

   ```markdown
   # Phase N — {title}

   ## Overview

   {2–4 sentences: what this phase establishes, why it is needed, and the
   high-level implementation direction. Condensed from the Goal in
   phases.md.}

   ## Requirements

   - {Concrete, testable implementation requirements.}
   - {Every task from phases.md is covered, grouped logically.}
   - {Relevant implementation details and constraints.}
   - {Project-specific paths, modules, and conventions only when supported
     by project context.}

   ### Acceptance criteria

   - {Each "Done when" bullet from phases.md, framed as a verifiable
     criterion.}

   ## References

   - {Relevant project documents}
   - {Relevant existing source files/modules}
   - {Related plans or specifications}

   ## Notes

   - {Assumptions, scope boundaries, edge cases, validation expectations,
     design considerations, and items intentionally deferred to later
     phases.}
   - Reference to the five business rules in the agent instruction file
     (`AGENTS.md` or `CLAUDE.md`, whichever the project has) — any phase
     touching session/order data must preserve them.
   - Expected git workflow: branch `phase-N-{slug}`, tag
     `phase-N-complete` on merge.
   - Any phase-specific caveats surfaced from the surrounding docs.
   ```

6. **Report** what was created and the next step for the user: load this
   spec into `@context/current-feature.md` via the existing `feature load`
   skill (via the harness's own invocation mechanism) to start the
   implementation. Briefly surface any important
   assumptions or unresolved questions that ended up in **Notes**.

## Output reasoning

These rules govern _how_ the spec content in step 5 is produced. They do not
change the workflow above.

### 1. Ground the spec in project context

Before drafting, inspect just enough of the project to make the spec
consistent with it. Look for, as relevant:

- The agent instruction file (`AGENTS.md` or `CLAUDE.md`), README, and
  other project overview docs
- Architecture or design docs and coding conventions
- `context/phases.md` neighbors (prior phase specs in `@context/features/`,
  the next phase's goals) to understand what already exists and what is
  deferred
- Existing source modules and similar functionality the phase builds on
- Existing tests and validation patterns
- Existing schema, API, UI, or service conventions

Do not perform an exhaustive codebase audit. Research only enough to know:

- Where the phase's work belongs
- Which existing modules or components are relevant
- Which implementation patterns and conventions already exist
- What related documentation should be referenced

Use the project's actual terminology. Never invent technologies,
architecture, files, modules, or conventions that are not supported by the
project context or `phases.md`.

### 2. Translate the phase into implementation scope

Turn the tasks into concrete, implementation-oriented requirements. Where
applicable, cover:

- What needs to be created or changed
- Important domain and business rules
- Data/model/schema changes
- API, service, UI, background-job, integration, or infrastructure changes
- Validation and integrity rules
- Operational considerations
- Testing or verification expectations
- Project conventions the implementation must follow

Be specific enough that another developer or coding agent can use the spec
as an implementation guide. Do not prescribe a technology the project does
not already establish. Do not drop or rewrite the meaning of any task or
"Done when" item from `phases.md`; refine and clarify them, don't replace
them.

### 3. Style

Prefer:

- Concrete implementation requirements
- Short, scannable bullets
- Explicit constraints
- Existing project terminology
- References to real project artifacts
- Clear scope boundaries
- Useful validation or migration considerations

Avoid:

- Long narrative explanations
- Generic filler
- Unsupported technology choices
- Repeating information already obvious from the phase title

The spec should be understandable and scannable within a few minutes.

### 4. References

Include only references that are actually relevant to this phase: project
docs, existing implementation files, related feature specs or plans,
architecture docs, or official documentation. Do not invent external links;
include a URL only if it already appears in the project context. Do not
list the generated spec itself as a reference.

## Stop conditions

Stop and surface a clear error (do **not** silently create a spec) when:

- The phase number argument is missing or not a non-negative integer.
- No matching `## Phase N — ...` section exists in `phases.md`.
- One or more prior phases are missing their `phase-X-complete` tag.
- The target spec file already exists (refuse to overwrite — tell the user
  to delete or rename the existing file first).

## Output

On success, end with a single line:

```
Created @context/features/{serial-number-prefix}phase-{N}-{slug}-spec.md — load it with the feature skill's load step (e.g. /feature load)
```
