---
name: studio-analysis
description: Produce or revise Studio's four-part HTML requirements document with reviewable business flows, API sequences, and database diagrams; no application code.
---

# Studio analysis

Read the task input, existing design, and requested revision. Use the adjacent create-prd skill for product scope, api-design-principles for backend interfaces, and mermaid-diagrams for diagrams. Read API references/details.md only when the requested interface needs its detailed patterns. For frontend design, use frontend-design while preserving the user's reference screenshots, established visual identity, and confirmed requirements.

The task prompt owns the output protocol: return exactly four JSON string fields, prd, frontend, backend, database, to the supplied result file. Each string is an HTML fragment using headings, paragraphs, lists, and tables, not a complete executable page. Use <pre class="mermaid"> for diagram source, escaping HTML-sensitive characters. Do not add scripts, event handlers, inline styles, external resources, embedded pages, images, or forms. Studio supplies rendering and typography. The editor and revision history retain the source strings.

The PRD covers problem, intended users, scope and non-goals, functional requirements, permissions, acceptance criteria, and explicitly marked assumptions/open questions. Include a business flow with at least one meaningful decision or failure path when the requirements contain one. Describe unresolved requirements as open questions; this unattended task must still write a reviewable proposal rather than wait for chat input. Do not fabricate research, named stakeholders, success metrics, or completed verification.

Frontend design identifies pages, navigation, interactive states, form validation, loading/empty/error states, accessibility, and references. Backend design documents each core API with method/path or GraphQL operation, authorization, request and response fields, validation, error responses, and pagination or idempotency where applicable, plus a key request sequence when backend interaction exists. Choose the API paradigm from confirmed requirements; do not introduce both REST and GraphQL without a need. Database design includes entities, fields, keys, constraints, migrations, and an ER diagram when persistent entities exist. Explain explicitly when no backend or persistent data is needed rather than inventing tables. Link core requirements to the pages, API operations, and persistent entities that implement them; use consistent names and fields across the four sections. Every diagram must agree with its accompanying text. Use the renderer's Mermaid 11.17.2 syntax, with short labels, stable node IDs, no directives, no frontmatter, no external links, and no HTML labels. Keep each diagram below 20,000 characters and 200 edges.

For revisions, preserve unaffected requirements and diagrams. Update related sections when a confirmed change affects their consistency. Do not implement the application or change acceptance rules to conceal a conflict.
