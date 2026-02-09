# Agent Skills

This repository contains a collection of specialized skills designed to enhance the capabilities of the AI agent. Each skill provides specific instructions, guidelines, and best practices for particular tasks.

## Available Skills

### 1. Copilot Commit Style
**Directory:** `copilot-commit-style/`

This skill enforces a strict commit message format based on the [Conventional Commits](https://www.conventionalcommits.org/) specification. It ensures that all commit messages are consistent, descriptive, and include relevant emojis.

**Format:**
```
<emoji> <type>(<scope>): <description>
```

**Examples:**
* `✨ feat(auth): add OAuth2 login flow`
* `🐛 fix(api): resolve memory leak in worker`
* `📝 docs(readme): update installation guide`

### 2. Odoo Code Reviewer
**Directory:** `odoo-reviewer/`

This skill acts as an expert reviewer for Odoo development projects. It provides comprehensive guidelines for auditing Python models, controllers, and XML views/data files.

**Key Focus Areas:**
* **Python:** PEP8 compliance, Odoo ORM best practices (using `filtered`, `mapped`, avoiding direct SQL), and proper field naming conventions.
* **XML:** concise XPath expressions, correct attribute usage, and data file structure.
* **Manifest:** dependency management and file ordering.
* **Security & Performance:** checks for access rights and N+1 query issues.

## Usage

These skills are intended to be loaded by the agent when specific tasks are requested. The `SKILL.md` file in each directory contains the detailed prompt and instructions for that specific skill.
