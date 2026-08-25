# Phase 0 — Scaffolding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up empty-but-working backend and frontend project skeletons that every later phase plugs into — no feature logic yet.

**Architecture:** Two independent packages at the repo root: `backend/` (a `uv`-managed Python package, FastAPI + pytest, src layout) and `frontend/` (a Vite-scaffolded React + TypeScript app with Tailwind CSS wired in). No communication between them yet — that starts in Phase 3/7.

**Tech Stack:** Python 3.11+ (uv-managed), FastAPI, pytest. React 18 + TypeScript, Vite, Tailwind CSS.

**Spec:** `vault-fcc-dashboard/plans/PHASE-0-SCAFFOLDING.md` (scope), `vault-fcc-dashboard/features/BACKEND/BACKEND--technologies.md`, `vault-fcc-dashboard/features/FRONTEND/FRONTEND--technologies.md` (tech decisions this plan implements).

## Global Constraints

- Backend: Python >=3.11 (needed for `datetime.fromisoformat`'s full ISO-8601 parsing, per DATE-TIME--technologies, used starting Phase 1) — pin via `uv`.
- Backend: no ORM — stdlib `sqlite3` only, starting Phase 2 (nothing to enforce yet in Phase 0, noted for later tasks' awareness).
- Backend package name: `fcc_dashboard`.
- Frontend: TypeScript strict mode on (Vite's default React-TS template already enables this — verify, don't disable it).
- No feature logic (log parsing, DB, API routes beyond FastAPI's default, UI pages) in this phase — placeholders/blank shells only.

---

### Task 1: Backend package skeleton

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/fcc_dashboard/__init__.py`
- Create: `backend/tests/test_placeholder.py`
- Create: `backend/.gitignore` (or add backend-specific ignores to the root `.gitignore` — use the root one, see Task 4)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: the `fcc_dashboard` package import path (`import fcc_dashboard`), used by every later backend task. Package root: `backend/src/fcc_dashboard/`. Test root: `backend/tests/`.

- [ ] **Step 1: Initialize the uv project**

Run from `backend/`:
```bash
cd backend
uv init --app --package --name fcc-dashboard --python 3.14
```
This creates `backend/pyproject.toml`, `backend/src/fcc_dashboard/__init__.py`, and `backend/src/fcc_dashboard/__main__.py` (delete `__main__.py` if created — not needed yet, FastAPI app entry point comes in Phase 3).

- [ ] **Step 2: Add dependencies**

```bash
uv add fastapi "uvicorn[standard]"
uv add --dev pytest httpx
```
(`httpx` is required by FastAPI's `TestClient`, used starting Phase 3 — adding it now avoids a second dependency-install round trip.)

- [ ] **Step 3: Write the placeholder test**

`backend/tests/test_placeholder.py`:
```python
"""Placeholder test confirming the test runner and package import path work."""

import fcc_dashboard


def test_package_importable():
    assert fcc_dashboard is not None
```

- [ ] **Step 4: Configure pytest to find the src-layout package**

Add to `backend/pyproject.toml` (append, don't replace what `uv init` generated):
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 5: Run the test**

```bash
cd backend
uv run pytest -v
```
Expected: `test_placeholder.py::test_package_importable PASSED`, 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/
git commit -m "chore(backend): scaffold Python package with pytest"
```

---

### Task 2: Frontend package skeleton

**Files:**
- Create: `frontend/` (entire Vite-scaffolded tree: `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, etc.)

**Interfaces:**
- Consumes: nothing (independent of Task 1).
- Produces: a dev server reachable at `http://localhost:5173` (Vite's default port) via `npm run dev`, and a `npm run build` command producing `frontend/dist/` (consumed by Phase 7's single-process serving).

- [ ] **Step 1: Scaffold via Vite's official template**

Run from the repo root:
```bash
npm create vite@latest frontend -- --template react-ts
```

- [ ] **Step 2: Install dependencies**

```bash
cd frontend
npm install
```

- [ ] **Step 3: Verify TypeScript strict mode is on**

Open `frontend/tsconfig.app.json` (or `tsconfig.json` depending on the template's exact layout) and confirm `"strict": true` is present under `compilerOptions`. The Vite react-ts template sets this by default — if for any reason it's missing, add it.

- [ ] **Step 4: Trim the default template content**

Replace `frontend/src/App.tsx` with a minimal placeholder (removes the Vite/React demo counter boilerplate, which isn't part of this project):
```tsx
function App() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <h1 className="text-2xl font-semibold">FCC Dashboard</h1>
    </div>
  )
}

export default App
```

- [ ] **Step 5: Run the dev server and verify it boots**

```bash
npm run dev
```
Expected: Vite prints a local URL (e.g. `http://localhost:5173/`); loading it in a browser shows "FCC Dashboard" centered on a blank page. Stop the dev server (Ctrl+C) once confirmed.

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/
git commit -m "chore(frontend): scaffold Vite + React + TypeScript app"
```

---

### Task 3: Tailwind CSS integration

**Files:**
- Modify: `frontend/package.json` (new devDependencies, added by the install commands below)
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Consumes: the frontend scaffold from Task 2 (`frontend/src/index.css` must already exist).
- Produces: Tailwind utility classes usable in any component via className (already used speculatively in Task 2 Step 4 — this task makes those classes actually work).

- [ ] **Step 1: Install Tailwind and its peer dependencies**

```bash
cd frontend
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```
This creates `frontend/tailwind.config.js` and `frontend/postcss.config.js`.

- [ ] **Step 2: Configure Tailwind's content paths**

`frontend/tailwind.config.js`:
```js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

- [ ] **Step 3: Add Tailwind directives to the stylesheet**

Replace the contents of `frontend/src/index.css` with:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 4: Verify Tailwind classes actually apply**

```bash
npm run dev
```
Open the dev server URL in a browser. Expected: the "FCC Dashboard" heading from Task 2 is visually centered (both axes) and uses a larger, semi-bold font — confirming `min-h-screen flex items-center justify-center` and `text-2xl font-semibold` are being applied, not just present as inert class names. Stop the dev server once confirmed.

- [ ] **Step 5: Commit**

```bash
cd ..
git add frontend/
git commit -m "chore(frontend): wire up Tailwind CSS"
```

---

### Task 4: Root .gitignore updates and final verification

**Files:**
- Modify: `.gitignore` (repo root — already exists with `.claude/`, `vault-fcc-dashboard/`, and generic Python/Node ignores from earlier project setup)

**Interfaces:**
- Consumes: Tasks 1–3's output (both packages must exist).
- Produces: nothing further — this is the phase's final checkpoint.

- [ ] **Step 1: Confirm the existing root .gitignore already covers the new packages**

Read `.gitignore` and confirm it already ignores `__pycache__/`, `.venv/`, `node_modules/`, `dist/`, `build/` (these were added generically during the vault-setup step, before `backend/`/`frontend/` existed) — these patterns are unanchored so they already match inside `backend/` and `frontend/` too. Add `backend/.venv/` explicitly only if `uv init` created a venv that isn't already caught by the generic `.venv/` pattern.

- [ ] **Step 2: Confirm nothing unwanted is staged**

```bash
git status
```
Expected: no `node_modules/`, `.venv/`, `dist/`, or `__pycache__/` entries appear as untracked/staged — only source files.

- [ ] **Step 3: Run both verification commands one more time from a clean checkout state**

```bash
cd backend && uv run pytest -v && cd ..
cd frontend && npm run build && cd ..
```
Expected: pytest passes (1 passed), and `npm run build` completes without errors, producing `frontend/dist/`.

- [ ] **Step 4: Update PROGRESS.md and commit**

Append one line to `PROGRESS.md`: `- 2026-08-25 — PHASE-0-SCAFFOLDING: implementation phase complete`.

```bash
git add PROGRESS.md
git commit -m "PHASE-0-SCAFFOLDING complete: backend + frontend skeletons verified"
git push origin main
```

## Self-Review Notes

- Spec coverage: PHASE-0-SCAFFOLDING.md's two bullets (Python/FastAPI/pytest backend, Vite/React/TS/Tailwind frontend) are covered by Tasks 1–3; both "Verifiable" criteria (pytest passes, `npm run dev` boots a blank page) are exercised in Task 1 Step 5, Task 2 Step 5, and Task 3 Step 4/Task 4 Step 3.
- No placeholders: every step has real, runnable commands or complete file contents, no "TBD"/"add appropriate X".
- Type consistency: package name `fcc_dashboard` (Python, underscore) vs `fcc-dashboard` (uv project name / npm dir, hyphen) is intentional — Python import names can't contain hyphens, this is the standard convention, not an inconsistency.
