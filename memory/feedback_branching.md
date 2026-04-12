---
name: Release branching convention
description: All release implementations must be done on a feature branch, not directly on main
type: feedback
---

Each release is implemented on a dedicated branch before merging to main.

**Why:** User wants clean separation between planning (main) and implementation work.

**How to apply:** When starting implementation of a release (e.g. v0.2.0), create a branch (e.g. `release/v0.2.0` or `feat/transcription`) before writing any code. Never implement release features directly on main.
