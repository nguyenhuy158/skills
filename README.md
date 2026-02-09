# Agent Skills

Collection of specialized skills to enhance AI agent capabilities.

```mermaid
graph TD
    Repo[Agent Skills] -->|Loads| Skill1[Copilot Commit Style]
    Repo -->|Loads| Skill2[Odoo Code Reviewer]
    
    Skill1 -->|Action| Enforce[Strict Commit Format]
    Skill2 -->|Action| Audit[Odoo Code Audit]
```

## Available Skills

### 1. Copilot Commit Style
**Directory:** `copilot-commit-style/`

Enforces [Conventional Commits](https://www.conventionalcommits.org/).

```mermaid
graph LR
    Msg["✨ feat(auth): add OAuth2 login flow"]
    
    subgraph Structure
    Emoji((Emoji)) --> Type[Type]
    Type --> Scope[Scope]
    Scope --> Desc[Description]
    end

    style Emoji fill:#ff9,stroke:#333
    style Type fill:#bbf,stroke:#333
    style Scope fill:#dfd,stroke:#333
    style Desc fill:#fdd,stroke:#333
```

**Key Rules:**
*   **Emoji** Required
*   **Lowercase** Type
*   **Max 80** characters

### 2. Odoo Code Reviewer
**Directory:** `odoo-reviewer/`

Expert reviewer for Odoo development projects.

```mermaid
mindmap
  root((Odoo Review))
    Python
      PEP8 & Naming
      ORM Best Practices
      No Direct SQL
    XML
      Concise XPath
      No Hardcoded IDs
      Correct Attributes
    Manifest
      Depends
      Data Order
      License
    Critical Checks
      Security (Access Rights)
      Performance (N+1)
      Idempotency
```

## Usage

Agents load these skills from the `SKILL.md` file in each directory when specific tasks are requested.
