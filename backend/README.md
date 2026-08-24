# Backend

Two packages, and the boundary between them is the point.

**`src/option_pricing/`** - the pricing library. NumPy and SciPy only: no web
framework, no I/O, no configuration. It takes numbers and returns numbers, and is
installable and testable on its own.

**`src/api/`** - a FastAPI adapter that translates HTTP into calls on that library.
It contains no financial logic.

Nothing in `option_pricing` imports anything from `api`. That direction is what lets
the whole pricing suite run in milliseconds with no server, no fixtures and no
mocking, and it means the mathematics can be reviewed without reading web plumbing.

```python
from option_pricing import OptionSpec, black_scholes

spec = OptionSpec(spot=100, strike=100, time_to_expiry=1.0,
                  risk_free_rate=0.05, volatility=0.2)
black_scholes.price(spec)   # 10.450583572185565
```

See the [root README](../README.md) for how to run it, [`docs/MATHS.md`](../docs/MATHS.md)
for the formulae and conventions, and [`docs/adr/`](../docs/adr/) for why it is
arranged this way.
