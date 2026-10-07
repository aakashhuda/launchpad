# Launchpad

A product launch and discovery platform where founders schedule launches, members vote and discuss products, and staff moderates quality and trust.

## Context Files

Read the following to get the full context of the project:

- @context/project-overview.md
- @context/coding-standards.md
- @context/ai-interaction.md
- @context/backend-architecture-playbook.md
- @context/docs/plans/01-client-brief.md

## Commands

- **Backend dev server**: `cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
- **Backend tests**: `cd backend && python3 -m pytest`
- **Backend lint**: `cd backend && python3 -m ruff check .`
- **Backend format**: `cd backend && python3 -m black .`

**IMPORTANT:** Do not add Claude to any commit messages
