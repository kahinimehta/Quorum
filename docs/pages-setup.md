---
layout: default
title: Site publishing
nav_order: 13
description: "Deploy docs to neurodiscover.github.io"
---

# Site publishing

This documentation site is built with **Jekyll** and the [Just the Docs](https://github.com/just-the-docs/just-the-docs) theme.

**Target URL:** [https://neurodiscover.github.io](https://neurodiscover.github.io)

---

## Why neurodiscover.github.io

GitHub Pages serves org/user sites from a repository named **`neurodiscover.github.io`** under the **`neurodiscover`** GitHub org (or user account). That yields a root URL without `/Quorum/` in the path.

The application source code stays in [kahinimehta/Quorum](https://github.com/kahinimehta/Quorum); docs are deployed to the org Pages repo.

---

## One-time setup

1. Create GitHub org (or user) **`neurodiscover`**
2. Create repository **`neurodiscover.github.io`** (public)
3. In **kahinimehta/Quorum** → Settings → Secrets → Actions, add:
   - `NEURODISCOVERY_DOCS` — see token options below
4. Enable GitHub Pages on the org repo: **Settings → Pages → Source: Deploy from branch → `main` / root**

{: .important }
**Deploy succeeded but site shows 404?** Pushing files to `neurodiscover.github.io` is not enough — you must enable Pages on that repo (step 4). Wait 2–5 minutes, then hard-refresh or try an incognito window. Use **https://neurodiscover.github.io** (not `kahinimehta.github.io/Quorum/`).

### PAT options (if deploy fails with 403)

**Option A — Classic token (most reliable for cross-repo push)**

1. GitHub → Settings → Developer settings → **Tokens (classic)** → Generate
2. Scope: **`repo`** (full control of private repositories)
3. Save as secret `NEURODISCOVERY_DOCS` in Quorum

**Option B — Fine-grained token**

1. Resource owner: **`neurodiscover`**
2. Repository: **`neurodiscover.github.io`** only
3. **Contents:** Read and write
4. **Metadata:** Read-only (usually auto-included)

The deploy workflow uses `persist-credentials: false` on checkout so the PAT is not overridden by the default `GITHUB_TOKEN`.

---

## Deploy workflow

From **Quorum** repo: **Actions → “Deploy docs to neurodiscover.github.io” → Run workflow**

The workflow:

1. Checks out `docs/`
2. Runs `bundle exec jekyll build` (Just the Docs)
3. Pushes `docs/_site/` to `neurodiscover/neurodiscover.github.io` `main` branch

Workflow file: `.github/workflows/deploy-neurodiscover-org-pages.yml`

---

## Preview on Quorum repo (optional)

**Actions → “Deploy documentation to GitHub Pages”** builds Jekyll and publishes to this repo's GitHub Pages environment (project URL, e.g. `kahinimehta.github.io/Quorum/`). Use for PR previews; the canonical public URL is **neurodiscover.github.io**.

---

## Site shows 404 after a successful deploy

| Check | Action |
|-------|--------|
| **Pages enabled?** | **neurodiscover/neurodiscover.github.io** → **Settings → Pages** → Source: **Deploy from a branch** → **`main`** / **`/ (root)`** → Save |
| **Correct URL?** | **https://neurodiscover.github.io** — not the Quorum project URL |
| **Files on `main`?** | Repo should contain `index.html`, `assets/`, etc. at the root (not a `docs/` subfolder) |
| **Still 404?** | Wait 2–5 min after enabling Pages; hard-refresh (Cmd+Shift+R) or incognito |
| **Custom domain?** | Remove any custom domain under Pages unless DNS is configured |

---

## Build locally

```bash
cd docs
bundle install
bundle exec jekyll serve
```

Open **http://127.0.0.1:4000**

---

## Auto-deploy on push (optional)

Edit `.github/workflows/deploy-neurodiscover-org-pages.yml` to add:

```yaml
on:
  push:
    branches: [main]
    paths:
      - "docs/**"
  workflow_dispatch:
```

after `NEURODISCOVERY_DOCS` is configured.
