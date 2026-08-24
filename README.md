# Options Pricing Tool

Prices European and American vanilla options three independent ways - closed form,
binomial lattice and Monte Carlo simulation - reports all five Greeks from each, and
shows the two numerical methods converging on the exact answer.

Python and FastAPI on the backend, React and TypeScript on the front. Runs locally
with two commands; ships as a container if you want one.

<!--
  Screenshots go here. Drop the images into docs/screenshots/ and uncomment:

  ![The pricing screen](docs/screenshots/main.png)
  ![Convergence view](docs/screenshots/convergence.png)
-->

---

## Why three models

Anyone can implement Black-Scholes. The reason this project implements three
methods is that **they check each other**.

Black-Scholes is a closed form, so it is exact. The binomial lattice and the Monte
Carlo simulation are approximations that should converge on it. If all three agree,
that is strong evidence every one of them is correct - far stronger than any single
implementation matching a textbook example.

The *Convergence* view makes that visible. Both approximations approach the exact
price, and they do it in visibly different ways:

- the **lattice oscillates**, its error flipping sign with each extra step and the
  swings decaying. That is not noise. Adding a step moves the strike relative to the
  tree's terminal nodes, so consecutive step counts straddle the true value. A
  smooth curve here would mean the lattice was not centred.
- **simulation converges stochastically**, its confidence band narrowing as
  1/sqrt(n). Quadrupling the paths halves the error, which is exactly why simulation
  is the expensive way to price something that has a closed form.

| Model | Method | Handles American | Reports error |
|---|---|---|---|
| Black-Scholes-Merton | Closed form with continuous dividend yield | No | Exact |
| Binomial lattice (CRR) | Vectorised backward induction | Yes | Deterministic |
| Monte Carlo | Terminal-value GBM simulation | No | Standard error + 95% CI |

---

## Features

- **Three pricing models** from identical inputs, with each one's error measured
  against the closed form.
- **All five Greeks** - delta, gamma, vega, theta, rho - computed analytically for
  Black-Scholes, read directly off the lattice nodes for the binomial model, and by
  bumped revaluation with common random numbers for Monte Carlo. The table tints any
  disagreement above a tenth of a percent.
- **American exercise** via the lattice, with the other two models declining and
  explaining why rather than returning a European price.
- **Implied volatility** solved with Brent's method on a bracket.
- **Live market data** - ticker lookup fills spot and 30-day realised volatility,
  cached for 15 minutes, with manual entry always available.
- **Four charts**: payoff and profit, Greek sensitivity against spot, convergence,
  and sample GBM paths.
- **Shareable URLs** - every input is serialised to the query string.
- **Interactive API docs** generated from the code at `/api/docs`.

---

## Running it

Requires [Python 3.12+](https://www.python.org/downloads/) and
[Node.js 20+](https://nodejs.org/). Nothing else.

```bash
git clone https://github.com/Hakman21/options-pricing-tool.git
cd options-pricing-tool

python scripts/setup.py     # once
python scripts/dev.py       # every time after
```

On Windows, `scripts\setup.cmd` and `scripts\dev.cmd` do the same thing.

|---|---|
| App | <http://127.0.0.1:5173> |
| API docs | <http://127.0.0.1:5173/api/docs> |

`dev.py` starts both processes, streams their logs into one terminal tagged `[api]`
and `[web]`, waits for the API to answer, then opens a browser. Ctrl-C stops both.
If an API is already running on port 8000 - a container, say - it reuses that and
starts only the web app.

**Sanity check:** the default contract should price at **10.4506**. That is the
canonical Black-Scholes value for a one-year at-the-money call with `S = K = 100`,
`r = 5%`, `sigma = 20%`.

> Python 3.12 is the floor because NumPy's current type stubs use syntax that
> earlier interpreters cannot parse, so `mypy` will not run on 3.11. The pricing
> code itself is happy on 3.11.

### The checks

```bash
python scripts/check.py            # everything, with full output on failure
python scripts/check.py --verbose  # full output for everything
```

Runs ruff, `mypy --strict`, the backend suite behind a 90% coverage gate, eslint,
prettier, `tsc --noEmit`, the frontend tests, and a production build.

---

## Architecture

```
  Browser  --->  Vite dev server (:5173)  --/api-->  FastAPI (:8000)
                 serves the React app                    |
                 proxies /api                            +-- TTL cache (15 min)
                                                         +-- Yahoo Finance
```

The proxy is what puts both halves on one origin, which is why there is no CORS
configuration anywhere in this project.

### The dependency rule

```
  api/routers, schemas.py     HTTP verbs, status codes, OpenAPI    <-- tests/api
        |  imports
        v
  api/services, market_data   Orchestration, caching, timeouts
        |  imports
        v
  option_pricing/             NumPy + SciPy only, zero web imports <-- tests/unit
```

**The pricing library does not import FastAPI, and never will.** Everything in
`option_pricing/` takes numbers and returns numbers. The API is a thin adapter that
translates HTTP into function calls.

That constraint buys three things: the pricing tests run in milliseconds with no
server, no fixtures and no mocking; the library is usable on its own; and the
mathematics can be reviewed without wading through web plumbing.

```python
from option_pricing import OptionSpec, binomial, black_scholes, monte_carlo

spec = OptionSpec(spot=100, strike=100, time_to_expiry=1.0,
                  risk_free_rate=0.05, volatility=0.2)

black_scholes.price(spec)                    # 10.450583572185565
binomial.price(spec, steps=2000)             # 10.449916...
monte_carlo.price_with_greeks(spec).price    # 10.46 +/- 0.02
```

---

## Numerical detail

The choices below are the ones that separate a working implementation from a
correct one. [`docs/MATHS.md`](docs/MATHS.md) has every formula and its derivation.

**The lattice is vectorised.** Each time level is one NumPy array that shrinks by a
single element per backward step, so there is no Python loop over nodes. At 2000
steps that is roughly 200 ms rather than half a minute.

**Three Greeks come free from the lattice.** The tree already holds the option value
at spots either side of today's, so delta, gamma and theta are read off levels 1 and
2 directly. Only vega and rho need re-pricing, because volatility and the rate
change the tree's geometry.

**Monte Carlo samples terminal values, not paths.** A vanilla European payoff depends
only on `S_T`, so stepping paths would add discretisation error to the sampling error
already present, for nothing. Paths are simulated separately, purely for the chart.

**Variance reduction, and an honest error.** Antithetic variates pair every draw with
its negative; a control variate regresses the payoff on the discounted terminal
price, whose mean is known exactly. Together they roughly halve the standard error at
the same path count. The standard error is computed *across antithetic pairs* rather
than across all samples, because the two halves are not independent - treating them
as independent understates the error by about sqrt(2).

**Common random numbers for simulated Greeks.** Every bumped revaluation reuses the
same underlying draws. Without that, the difference between two independently
simulated prices is dominated by simulation noise rather than by the sensitivity
being measured. It is the most common mistake in Monte Carlo Greeks.

**Two numerical guards.** The lattice refuses to run when the risk-neutral
probability leaves (0, 1), which means the time step is too large for the volatility
and the tree admits arbitrage. It also refuses when the node span would overflow a
float64. Both produce plausible-looking numbers if left unchecked.

---

## Testing

Five tiers, because a pricing engine can be wrong in ways a smoke test never reaches.

**1 - Golden values.** Worked examples from Hull, with the chapter cited in the test
name. Catches sign errors and misplaced square roots by comparing against numbers
computed by someone else.

**2 - Property-based, with Hypothesis.** Rather than asserting specific outputs for
specific inputs, these assert relationships that must hold for *every* input, over
thousands of generated contracts:

- put-call parity, `C - P = S*e^(-qT) - K*e^(-rT)`, to 1e-8
- no-arbitrage bounds, `max(S*e^(-qT) - K*e^(-rT), 0) <= C <= S*e^(-qT)`
- monotonicity in spot, strike and volatility
- Greek signs and ranges: call delta in (0, e^(-qT)], gamma >= 0, vega >= 0
- American >= European for the same contract

Put-call parity is the most valuable single test here. It is a no-arbitrage
identity, so almost any error in `d1`, `d2`, the discounting or the dividend
adjustment breaks it. When a property fails, Hypothesis shrinks the counterexample to
the smallest case that still fails.

**3 - Cross-model convergence.** The lattice agrees with the closed form to 1e-3 at
2000 steps. Seeded Monte Carlo lands within **three** standard errors - three rather
than two, because at 2 sigma a suite this size goes red roughly one run in twenty,
and a pipeline that fails randomly teaches you to ignore it.

**4 - API contract.** Every route, every validation rejection, and a simulated data
outage asserting a clean 503.

**5 - Frontend.** Vitest and Testing Library with MSW. Includes the test that matters
most: a 503 from the market data endpoint renders the manual-entry fallback while
pricing keeps working.

One test worth singling out: implied volatility is only *identifiable* where vega is
meaningful. A deep in-the-money option days from expiry is worth its intrinsic value
to within double precision, so a whole range of volatilities reproduces the same
price and no solver can distinguish between them. The property test excludes that
region and says why, rather than loosening its tolerance.

---

## CI

Every push runs four jobs:

| Job | What it gates |
|---|---|
| `backend` | ruff, format check, `mypy --strict`, pytest on Python 3.12 and 3.13, coverage >= 90% |
| `frontend` | eslint, prettier, `tsc --noEmit`, vitest, production build |
| `contract` | regenerates the client types from the live schema and fails on any diff |
| `image` | builds the container, **starts it**, waits for readiness, prices an option over HTTP, then Trivy-scans for HIGH/CRITICAL |

The `contract` job is the interesting one. `frontend/src/types/api.d.ts` is generated
from the backend's OpenAPI document, so a change to a Pydantic model that breaks the
client becomes a failed build rather than a runtime error in a browser.

The `image` job builds *and boots* the container, because building is not the same as
working.

---

## Docker

Not required for development, but the image is real and CI builds and runs it on
every push:

```bash
docker build -t options-pricing-api:local backend
docker run --rm -p 8000:8000 options-pricing-api:local
```

That serves the API only; run `python scripts/dev.py` alongside it for the web app.
[`docs/DOCKER.md`](docs/DOCKER.md) explains what each decision in the Dockerfile is
for, and how to pin the base image by digest.

---

## Repository layout

```
scripts/                  setup, dev, check - Python, cross-platform
backend/
  src/option_pricing/     the pure library
    types.py                OptionSpec, Greeks, PricingResult; validates on creation
    errors.py               typed failures the API maps onto status codes
    black_scholes.py        closed form, analytic Greeks, implied vol solver
    binomial.py             CRR lattice, vectorised, American exercise
    monte_carlo.py          GBM simulation, variance reduction, CRN Greeks
    greeks.py               independent finite-difference check used by tests
    convergence.py          sweeps behind the comparison charts
  src/api/                the FastAPI adapter
    main.py                 app factory, error-to-status mapping
    schemas.py              request/response contract
    settings.py             environment configuration
    market_data.py          yfinance wrapper, caching, graceful failure
    routers/                pricing, market, health
  tests/                  unit, property, convergence, api
  Dockerfile              multi-stage, non-root, healthchecked
frontend/
  src/components/         InputPanel, ResultCards, GreeksTable, Charts
  src/hooks/              usePricing, useUrlState
  src/lib/                api client, formatting, zod schema
  src/types/api.d.ts      generated from OpenAPI, never hand-edited
docs/
  MATHS.md                every formula, with conventions and derivation notes
  DOCKER.md               the container build, explained
  adr/                    architecture decisions and their trade-offs
```

---

## Configuration

Every setting has a working default; the app starts with nothing configured. See
[`backend/.env.example`](backend/.env.example).

| Variable | Purpose |
|---|---|
| `OPT_MARKET_DATA_ENABLED` | `false` disables live lookups entirely, leaving manual entry |
| `OPT_MARKET_CACHE_TTL_S` | How long quotes are cached (default 900) |
| `OPT_CORS_ORIGINS` | Only needed if the API is called from a different origin |
| `OPT_MAX_BINOMIAL_STEPS` | Guard rail on the expensive endpoints |

---

## Conventions

Time in years. Rates and yields continuously compounded, so `0.05` is 5%.

The API returns **raw derivatives**: vega per 1.00 of volatility, theta per year.
That is what the mathematics produces and what the tests check. Conversion to the
units practitioners quote - per vol point, per day - happens in the UI, at the
presentation layer only, so the finite-difference cross-checks stay honest.

---

## Limitations

Prices assume geometric Brownian motion with constant volatility. Real markets show
a volatility smile: implied volatilities vary systematically with strike and expiry,
because the true return distribution has fatter tails and more negative skew than a
lognormal. Prices for far-from-the-money options will therefore differ from market
quotes, and the implied volatility solver returns a different number per strike.

That is the model being honest about its assumptions rather than a defect. Fitting a
smile, or moving to a stochastic volatility model, is the natural next step.

American options are priced by lattice only - valuing them by simulation needs a
regression method such as Longstaff-Schwartz. No exotics.

Educational project. Not investment advice.

---

## Roadmap

- Implied volatility surface fitting (SVI), against a real options chain
- Longstaff-Schwartz for American Monte Carlo
- A Numba or Rust pricing kernel, benchmarked against the NumPy implementation
- Exotics: barriers, Asians, digitals
- Prometheus metrics and structured request logging

---

## Licence

MIT. See [LICENSE](LICENSE).
