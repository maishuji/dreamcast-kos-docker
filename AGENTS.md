# AGENTS.md

## Purpose

This repository uses lightweight contributor instructions for humans and coding agents.

## Commit Messages

- Use Conventional Commits.
- Preferred format: `<type>(<scope>): <summary>`
- Keep the summary short, imperative, and lowercase unless a proper noun requires otherwise.

Examples:

- `fix(dc-chain): add dcload-serial missing headers`
- `fix(dc-chain): pass dreamcast platform to kos-chain build`
- `ci(github-actions): add lint workflow`
- `docs(readme): update default dc-chain image tag`

Recommended common types:

- `fix`
- `feat`
- `docs`
- `ci`
- `refactor`
- `chore`

Recommended scopes in this repository:

- `dc-chain`
- `kos-ready`
- `kos-alpine`
- `readme`
- `github-actions`

## Branch Naming

- Use descriptive lowercase branch names.
- Separate words with hyphens.
- Prefer the format `<type>/<short-description>`.

Examples:

- `fix/dcload-serial-headers`
- `fix/kos-chain-platform-dreamcast`
- `ci/add-lint-workflow`
- `docs/update-dc-chain-tag`

## Working Rules

- Keep changes focused on one concern per branch when practical.
- Prefer updating existing workflows and scripts over introducing duplicate paths.
- When changing image tags or build paths, update code and documentation together.