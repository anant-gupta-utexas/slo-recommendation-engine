# [Your Project Name]

`[Add a one-sentence description of what this project does and for whom.]`

This document is the central "signpost" for our repository. It provides quick setup commands, links to our core documentation library, and explains our development workflow.

## Quick Start: Developer Setup
```bash
# 1. Set up the virtual environment and install dependencies
source .venv/bin/activate
uv sync

# 2. Run the stack locally
docker-compose up --build

# 3. Run local tests
pytest
```

## Directory Structure & Walkthrough

### Core Documentation (`docs/`)
**EVERGREEN DOCS**: The single source of truth for the project.
```
docs/
├── 1_product/      # "Why": Product Requirements (PRD.md)
├── 2_architecture/ # "High-Level How": System Design, TRD, diagrams
├── 3_guides/       # "How-to": Developer guides (getting_started.md, core_concepts.md)
└── 4_testing/      # "Quality": Testing strategy (index.md, unit_tests.md)
```

### Development Documentation (`dev/`)
**WORK-IN-PROGRESS**: Technical designs and planning for features being built.
```
dev/
├── active/   # Active feature development plans (TDS, tasks)
└── archive/  # Historical record of completed features
```

**Dev Workflow:**
1. **Start Planning**: Create `dev/active/[feature-name]/`
2. **Define the Spec**: Create inside your feature folder:
   * `[feature-name]-plan.md` - Technical Design Specification (TDS)
   * `[feature-name]-context.md` - Key decisions, dependencies, files to touch
   * `[feature-name]-tasks.md` - Progress checklist
3. **Build**: Get TDS reviewed, then implement
4. **Update Core Docs**: Update `docs/` to reflect changes (part of Definition of Done)
5. **Archive**: Move folder from `dev/active/` to `dev/archive/` after merge

### Source Code (`src/`)
**Clean Architecture** implementation with three layers:
```
src/
├── application/    # "Use Cases": Orchestrates workflows (e.g., CreateConversation)
├── domain/         # "Business Logic": Pure entities & rules (e.g., Conversation entity)
└── infrastructure/ # "Frameworks": API (FastAPI), DB (SQLAlchemy), etc.
```

**Key Principles:**
* Dependency Inversion: Inner layers define interfaces, outer layers implement
* Single Responsibility: Each component has one reason to change
* Testability: Pure business logic independent of frameworks