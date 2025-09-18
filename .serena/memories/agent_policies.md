# Agent Policies (Repo)

- Keep reusable logic in `dataforge/`; keep `pages/` modules self‑contained; no cross‑module imports between pages.
- Adhere to coding style and testing guidelines.
- Security: never commit secrets; validate uploads; never execute user content.
- Minimal, focused changes; update docs/tests when behavior changes.
- If nested `AGENTS.md` files exist, the deepest one overrides for its subtree.