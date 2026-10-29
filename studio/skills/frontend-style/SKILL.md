---
name: frontend-style
description: Adjust existing CSS or HTML style blocks for appearance-only feedback in the Studio isolated style workspace.
---

# Frontend style adjustment

Read the task input and inspect the supplied style files. Change only the requested color, spacing, typography, border, or similar visual property. Preserve selectors and unrelated declarations where possible. If the runnable frontend and static preview duplicate the selected style, adjust corresponding existing declarations consistently. If the target cannot be mapped, report that limitation instead of changing unrelated styles.

Do not change HTML structure, scripts, event handlers, API calls, permissions, backend code, dependencies, or database migrations. HTML edits are limited to existing style blocks. If the requested outcome needs other files or changes business behavior, stop and return `needsBusiness: true` with a summary explaining that the user must choose business development. Do not implement an approximation or invent verification results.

Use a focused visual or stylesheet check when available. Do not regenerate the PRD, scaffold an application, or run the full backend workflow for a visual adjustment. Report changed files and checks actually performed in the requested result JSON.
