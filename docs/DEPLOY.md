# Deploy & Submit

Everything is wired; these are the only steps that need your accounts. Copy-paste.

## 1 · Push to GitHub

```bash
cd "/Users/admin/ATUL /assignment"

# one-time GitHub auth (interactive — run it in your terminal with: ! gh auth login)
gh auth login

# create the repo and push (public so reviewers can read it without an invite)
gh repo create plum-claims-system --public --source=. --remote=origin --push
```

Or manually if you prefer an existing remote:

```bash
git remote add origin https://github.com/<you>/plum-claims-system.git
git push -u origin main
```

## 2 · Deploy for a live URL (Render — free, reads `render.yaml`)

1. Go to <https://dashboard.render.com> → **New** → **Blueprint**.
2. Connect the GitHub repo you just pushed. Render auto-detects `render.yaml`.
3. Click **Apply**. First build takes ~2 minutes. You get a URL like
   `https://plum-claims.onrender.com`.
4. Health check: open `https://<your-url>/api/health` — should return `{"status":"ok",...}`.
   The UI is at the root `/`.

> No environment variables are required. (Optional: set `GEMINI_API_KEY` in the
> Render dashboard to enable LLM extraction of raw/unstructured documents — not
> needed for the eval cases.)

Alternatives that also work out of the box: **Railway** (detects the `Dockerfile`),
**Fly.io** (`fly launch`), or any Docker host — `docker build -t plum-claims . &&
docker run -p 8000:8000 plum-claims`.

## 3 · Reply to the email

Send Vaibhavi:
- the GitHub repo URL (confirm it's public / access enabled),
- the deployed URL,
- a one-line pointer to `docs/EVAL_REPORT.md` (12/12 cases pass).

Record the walkthrough using `docs/DEMO_SCRIPT.md`.
```
