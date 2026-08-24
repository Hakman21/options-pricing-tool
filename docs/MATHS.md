# The mathematics

Every formula the library implements, with the conventions it assumes and the
numerical decisions that are not obvious from the formulae alone.

## Notation and conventions

| Symbol | Meaning |
|---|---|
| `S` | Current price of the underlying |
| `K` | Strike |
| `T` | Time to expiry, **in years** |
| `r` | Risk-free rate, **continuously compounded** |
| `q` | Dividend yield, continuously compounded |
| `σ` | Annualised volatility |
| `Φ` | Standard normal CDF |
| `φ` | Standard normal PDF |

Three conventions worth stating explicitly, because they are the usual source of
"why doesn't this match my spreadsheet":

- **Vega** is `∂V/∂σ` for a **1.00** absolute change in volatility (100 vol points).
  Traders quote it per point, so divide by 100.
- **Theta** is `∂V/∂t` in **years**, so it is normally negative. Divide by 365 for
  the per-day figure.
- **Rho** is `∂V/∂r` for a **1.00** absolute change in the rate. Divide by 100 for
  the per-percentage-point figure.

The library returns raw derivatives throughout and converts only at the presentation
layer. That keeps the finite-difference cross-checks in the test suite honest: a
scaled Greek would need the scaling replicated in the differentiator too.

---

## 1 · Black-Scholes-Merton

With a continuous dividend yield:

```
d₁ = [ln(S/K) + (r - q + σ²/2)·T] / (σ√T)
d₂ = d₁ - σ√T

Call  =  S·e^(-qT)·Φ(d₁)  -  K·e^(-rT)·Φ(d₂)
Put   =  K·e^(-rT)·Φ(-d₂) -  S·e^(-qT)·Φ(-d₁)
```

Carrying `q` costs nothing and makes the tool correct for index options. Setting
`q = 0` recovers the textbook formulae exactly.

### Greeks

All five come from the same `d₁`, `d₂` and `φ(d₁)` the price already computes.

|  | Call | Put |
|---|---|---|
| **Δ** | `e^(-qT)·Φ(d₁)` | `-e^(-qT)·Φ(-d₁)` |
| **Γ** | `e^(-qT)·φ(d₁) / (S·σ√T)` | same |
| **ν** | `S·e^(-qT)·φ(d₁)·√T` | same |
| **Θ** | `-S·φ(d₁)·σ·e^(-qT)/(2√T) + q·S·e^(-qT)·Φ(d₁) - r·K·e^(-rT)·Φ(d₂)` | `-S·φ(d₁)·σ·e^(-qT)/(2√T) - q·S·e^(-qT)·Φ(-d₁) + r·K·e^(-rT)·Φ(-d₂)` |
| **ρ** | `K·T·e^(-rT)·Φ(d₂)` | `-K·T·e^(-rT)·Φ(-d₂)` |

Gamma and vega are identical for calls and puts on the same contract - a direct
consequence of put-call parity, since the parity terms are linear in `S` and
independent of `σ`. The test suite asserts both.

### Put-call parity

```
C - P = S·e^(-qT) - K·e^(-rT)
```

Asserted to 1e-8 over thousands of Hypothesis-generated contracts. This one identity
catches almost any error in `d₁`, `d₂`, the discounting or the dividend adjustment,
which is why it is the single most valuable test in the suite.

### Implied volatility

Brent's method on the bracket `σ ∈ (10⁻⁶, 5)`, not Newton-Raphson.

Newton converges faster where vega is healthy and becomes unstable exactly where it
is not - deep in or out of the money, or close to expiry. Brent needs a bracket but
cannot diverge, and if no root exists in the bracket the quoted price violates the
no-arbitrage bounds, which is worth reporting rather than iterating on.

**Implied volatility is not always identifiable.** For `S=28, K=20, T=0.125, σ=0.125`
vega is about `8.6 × 10⁻¹³`: the option is worth its intrinsic value to within double
precision, and a whole range of volatilities reproduces the same price. No solver can
distinguish between them. This is a property of the problem, not a defect - the
property test skips contracts with negligible vega, and says why.

---

## 2 · Cox-Ross-Rubinstein binomial lattice

With `Δt = T/N`:

```
u = e^(σ√Δt)          d = 1/u          (so u·d = 1, the tree recombines)
p = (e^((r-q)Δt) - d) / (u - d)        risk-neutral probability
```

A node at level `ℓ` with `j` up-moves sits at `S·u^j·d^(ℓ-j)`, which collapses to
`S·u^(2j-ℓ)` because `d = 1/u`.

Terminal payoffs are built as one array; each backward step is

```
V_ℓ = e^(-rΔt) · [ p·V_{ℓ+1}[1:] + (1-p)·V_{ℓ+1}[:-1] ]
```

which shrinks the array by one element per step. No Python loop over nodes - at
`N = 2000` that is the difference between roughly 200 ms and half a minute.

For American exercise, one extra line per level:

```
V_ℓ = max(V_ℓ, intrinsic(S_ℓ))
```

### Greeks from the lattice

Three of the five are free, because the tree already contains the option value at
spots either side of today's.

```
Δ = (V_u - V_d) / (S·u - S·d)                                  level 1

Γ = [ (V_uu - V_ud)/(S·u² - S)  -  (V_ud - V_dd)/(S - S·d²) ]  level 2
    ─────────────────────────────────────────────────────────
                      (S·u² - S·d²) / 2

Θ = (V_ud - V₀) / (2Δt)                                        centre node, level 2
```

The middle node at level 2 sits at today's spot two time steps later, so the change
from the root is a clean time derivative. Vega and rho need re-pricing, because `σ`
and `r` change the lattice geometry itself.

### Numerical guards

Two failure modes that produce numbers rather than errors, so both are checked:

1. **`p ∉ (0,1)`** - the lattice admits arbitrage. Happens when `Δt` is too large for
   the given `σ`. Raises `LatticeStabilityError`.
2. **Overflow** - the extreme node sits at `S·e^(σ√(T·N))`, and `e^x` overflows a
   float64 above ~709. Guarded before it can produce an `inf` that propagates
   silently into an infinite option price.

### Convergence

The error is `O(1/N)` but **not monotone**: it alternates sign as `N` changes,
because adding a step moves the strike relative to the terminal nodes. Consecutive
step counts straddle the true value, and the amplitude decays.

```
N:      20      21      22      23      24      25
error: -0.099  +0.084  -0.090  +0.077  -0.083  +0.070
```

A monotone sequence here would mean the lattice was not centred. The convergence
chart exists to show this, and a test asserts the sign changes.

---

## 3 · Monte Carlo

For a vanilla European the payoff depends only on the terminal price, so `S_T` is
sampled directly from its lognormal distribution rather than stepping paths:

```
S_T = S·exp[ (r - q - σ²/2)·T  +  σ√T·Z ],     Z ~ N(0,1)

V = e^(-rT) · E[ max(±(S_T - K), 0) ]
```

Path stepping would add discretisation error on top of the sampling error for no
benefit. Paths *are* simulated, but only to draw the illustration in the UI.

### Variance reduction

**Antithetic variates.** Each `Z` is paired with `-Z`. The pair average is unbiased
with lower variance. Critically, the standard error is then computed **across pairs**,
not across all samples - the two halves are not independent, and treating them as
such understates the error by roughly √2.

**Control variate.** The discounted terminal price has a known mean under the
risk-neutral measure:

```
E[e^(-rT)·S_T] = S·e^(-qT)
```

and correlates strongly with the payoff, so regressing one on the other removes most
of the remaining variance:

```
β  = Cov(payoff, control) / Var(control)
V' = payoff - β·(control - S·e^(-qT))
```

Estimating `β` from the same sample introduces an `O(1/n)` bias, far smaller than the
variance it removes. Measured together, the two techniques roughly halve the standard
error at the same path count.

### Reporting the error

```
SE = s / √n                  CI₉₅ = V ± 1.96·SE
```

Every simulated result carries both. **A Monte Carlo price quoted to four decimal
places with no error estimate is misleading precision**, and the UI displays
`12.34 ± 0.07` rather than a bare number.

### Greeks by common random numbers

Bumped revaluations reuse the *identical* draws:

```
Δ ≈ [V(S+h; Z) - V(S-h; Z)] / 2h        h = 1% of spot
Γ ≈ [V(S+h; Z) - 2V(S; Z) + V(S-h; Z)] / h²    h = 5% of spot
```

Without common random numbers, the difference between two independently simulated
prices is dominated by simulation noise rather than by the sensitivity being
measured - the most common mistake in Monte Carlo Greeks. With them, delta matches
the analytic value to about 0.02% at 500k paths.

Gamma gets a wider bump because a second difference divides by `h²`, amplifying
whatever noise survives.

---

## What this model does not capture

Constant volatility. Real markets show a **volatility smile**: implied volatilities
backed out from traded prices vary systematically with strike and expiry, because the
true return distribution has fatter tails and more negative skew than a lognormal.

The consequence for this tool is worth being explicit about: prices for
far-from-the-money options will differ from market quotes, and the implied volatility
solver will return a different number for each strike. That is the model being
honest about its assumptions, not a bug.

Fitting a smile - SVI, or a stochastic volatility model like Heston - is the natural
next step, and is listed in the roadmap rather than pretended away.

---

## References

- Hull, J. *Options, Futures and Other Derivatives*, 11th ed. - the golden values in
  `tests/unit/test_black_scholes.py` cite chapter 15.
- Cox, J., Ross, S., Rubinstein, M. (1979). "Option pricing: a simplified approach."
  *Journal of Financial Economics* 7(3).
- Glasserman, P. *Monte Carlo Methods in Financial Engineering* - variance reduction
  and the common-random-numbers argument for bumped Greeks.
- Boyle, P. (1977). "Options: a Monte Carlo approach." *Journal of Financial
  Economics* 4(3).
