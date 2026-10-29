---
name: code-review
description: Review a generated application against confirmed requirements, reporting reproducible bugs, authorization gaps, integration failures, and actual verification results without editing production source.
---

# Application review

Read the confirmed requirements, latest development summary, source, and VALIDATION.md. Review implementation against requirements, API callers, authorization, error paths, and database consistency. Run relevant available checks in the disposable review copy. You may create local test probes in that copy; do not change application code to hide findings, read credentials, deploy, or write outside the supplied workspace. Dependencies and private data are excluded from the copy. Do not claim developer-reported commands were independently rerun. When prerequisites prevent meaningful testing, report inconclusive and name the missing prerequisite rather than passing.

For each finding provide a stable ID, severity (critical/high/medium/low), workspace-relative file, positive line number, trigger, concrete evidence, and a repair suggestion. Prefer substantiated bugs over speculative improvements. Mark uncertain concerns explicitly and avoid inventing a failure. Report critical/high defects as delivery blockers. Report medium/low findings as advisory work unless a failed check establishes a blocker. Never lower the severity of data loss, authorization bypass, or broken core flows to pass a review.

Write exactly the JSON fields requested by the task prompt. A pass requires no blocking findings and at least one actual relevant check with observed output; every reported check must have passed. Use changes_requested for actionable defects or failed checks. Use inconclusive when evidence is insufficient. A passing model review is not proof of deployment readiness and never replaces human acceptance.

Follow reviewFocus in the input: changes covers modified files and direct callers; full covers the application; recheck verifies previous findings and affected regressions, retaining unresolved IDs. Do not restart a full audit on each recheck. Report newly discovered high-risk defects with evidence. priorReview on a continuation task describes previous unfinished work; keep completed functionality.
