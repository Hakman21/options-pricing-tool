# Deploying to Vercel

Two Vercel projects from one repository: a static site for the web app, and a
Python function for the API. They end up on one origin, so the browser never makes
a cross-origin request and there is no CORS configuration anywhere.

Both fit comfortably on the free Hobby plan.

```
  Browser ──▶ options-pricing-tool.vercel.app   (static, served from the CDN)
                       │
                       └── /api/*  ──rewrite──▶  ...-api.vercel.app  (Python function)
```

---

## Why two projects rather than one

Vercel's Python preset routes *every* request to your app once it detects a
framework. That is right for an API-only project, but here it would mean serving
every JavaScript chunk and every image through a serverless function: no CDN, and
a cold start in front of the first page load.

Splitting them keeps the static build on the edge network where it belongs, and
leaves the function handling only what actually needs Python. The rewrite stitches
them back into one origin, so from the browser's point of view it is a single site.

Vercel's Services feature can also run both halves inside one project. It is worth
knowing about, but two projects is the simpler arrangement here: each half builds,
deploys and rolls back on its own, and the only thing joining them is a single
rewrite rule that any hosting platform could express.

---

## 1 · Deploy the API

New Project on Vercel, import the repository, then:

| Setting | Value |
|---|---|
| Project Name | `options-pricing-api` |
| Root Directory | `backend` |
| Framework Preset | Other (Vercel detects FastAPI from `pyproject.toml`) |

Nothing else to configure. `backend/pyproject.toml` already carries what Vercel
needs:

```toml
[tool.vercel]
entrypoint = "app:app"
```

That points at `backend/app.py`, a shim whose only job is to expose the real
application under a name the platform can find.

**Why a shim at all.** Vercel resolves an entrypoint to a *file path relative to
the project root* - `app.py`, `index.py`, `main.py`, or those same names one level
down in `src/` or `app/`. The application actually lives at `src/api/main.py`, so a
module path of `api.main:app` would send Vercel looking for `./api/main.py`, which
does not exist, and the build would fail with nothing found. Six lines in `app.py`
are cheaper than reshaping the package around one deployment target - and
`tests/api/test_entrypoint.py` prices a contract through that file, so if it ever
breaks, CI says so rather than a deployment.

`backend/vercel.json` keys its settings by the same resolved file, excludes the
test suite and caches from the bundle, and caps the function at 60 seconds:

```json
{
  "functions": {
    "app.py": { "maxDuration": 60, "excludeFiles": "..." }
  }
}
```

`backend/.python-version` pins 3.12, matching the CI matrix, `requires-python`, and
the Dockerfile. It is Vercel's default today, but the version the code is tested
against should be stated rather than inherited.

**Check it before moving on.** Take the deployment URL and:

```bash
curl https://YOUR-API.vercel.app/ready
```

You want `"market_data": "ok"`. If it says *client not installed*, the install did
not pick up `yfinance` - everything else still works, and the app falls back to
manual entry.

```bash
curl -X POST https://YOUR-API.vercel.app/api/v1/price \
  -H 'Content-Type: application/json' \
  -d '{"option":{"spot":100,"strike":100,"time_to_expiry":1,
       "risk_free_rate":0.05,"volatility":0.2},"model":"black_scholes"}'
```

That must return `10.450583572185565`. It is the canonical Black-Scholes value for
the standard contract, so if it comes back right, the whole engine is working.

---

## 2 · Point the frontend at it

Edit `frontend/vercel.json` and replace the placeholder host with the URL from
step 1:

```json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://options-pricing-api.vercel.app/api/:path*"
    }
  ]
}
```

This one line is what puts both halves on a single origin. The browser only ever
talks to the frontend deployment; Vercel forwards `/api/*` to the Python service
server-side. Two consequences worth knowing:

- **No CORS anywhere.** Same origin from the browser's perspective, so no preflight
  requests and no allow-list to maintain.
- **The API's hostname never reaches the bundle.** `src/lib/api.ts` builds every URL
  relative to `import.meta.env.BASE_URL`, so moving the backend is a change to this
  one line, with no rebuild.

Commit that change.

---

## 3 · Deploy the web app

Second New Project, same repository:

| Setting | Value |
|---|---|
| Project Name | `options-pricing-tool` |
| Root Directory | `frontend` |
| Framework Preset | Vite |
| Build Command | `npm run build` (the default) |
| Output Directory | `dist` (the default) |

`npm run build` runs `tsc --noEmit` before `vite build`, so a type error fails the
deployment rather than shipping a broken page.

---

## Verifying

```bash
BASE=https://options-pricing-tool.vercel.app

curl -fsS $BASE/api/health
curl -fsS $BASE/api/v1/meta | jq '{version, git_sha}'
curl -fsS -X POST $BASE/api/v1/price \
  -H 'Content-Type: application/json' \
  -d '{"option":{"spot":100,"strike":100,"time_to_expiry":1,
       "risk_free_rate":0.05,"volatility":0.2},"model":"black_scholes"}' | jq .price
```

`10.450583572185565` through your own domain means every hop is working: CDN,
rewrite, function, pricing engine.

Then open the site and check the *Convergence* tab. It is the heaviest endpoint -
several hundred lattices plus a stack of simulations - so if that renders, nothing
is close to the duration limit.

### When it does not work

| Symptom | Cause |
|---|---|
| API calls return HTML | The rewrite is missing or the host is still `REPLACE-ME`. The SPA is answering instead. |
| 404 on `/api/...` | Root Directory on the API project is not `backend`. |
| `FUNCTION_INVOCATION_FAILED` | Check the function logs in the Vercel dashboard. Usually an import error - confirm `backend/app.py` still exists and `[tool.vercel] entrypoint` still points at it. |
| First request slow, rest fast | Cold start. Expected on Hobby, and only affects the first hit after an idle period. |
| 503 from `/api/v1/market/...` | Yahoo is unreachable or rate-limiting the datacentre IP. By design: the tool stays usable on manual input. |
| Bundle size error | Something large got included. Tighten `excludeFiles` in `backend/vercel.json`. |

---

## What this costs

Nothing, on Hobby. For reference, the limits this project runs against:

| Limit | Hobby | This project |
|---|---|---|
| Function bundle (Python) | 500 MB | ~215 MB of dependencies, scipy included |
| Function duration | 300 s | Slowest endpoint is ~3 s |
| Memory | 2 GB / 1 vCPU | Well inside it |

The heaviest dependency is scipy at 132 MB, used for the normal distribution and
Brent's method. If the bundle ever became a problem, both are replaceable with
`math.erf` and a hand-written solver - roughly fifty lines, and it would drop the
bundle to about 80 MB. Not needed at present.

---

## Keeping the container

`backend/Dockerfile` is unchanged and still built, booted and scanned by CI on every
push. Vercel and the container are two independent ways to run the same API, and
the container remains the portable one - it runs anywhere that takes an image, with
no platform-specific configuration at all.
