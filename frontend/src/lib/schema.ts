/**
 * Client-side validation, mirroring the backend's Pydantic constraints.
 *
 * The duplication is deliberate and one-directional: these bounds exist so the user
 * gets feedback as they type rather than after a round trip. The server re-checks
 * everything regardless - client validation is a convenience, never a security
 * boundary, and the pricing library validates a third time so it stays safe when
 * used without the API.
 *
 * The bounds themselves are asserted against the generated OpenAPI types in the
 * test suite, so if the backend loosens or tightens a limit, the mismatch surfaces.
 */

import { z } from "zod";

export const MAX_PRICE = 1e7;
export const MAX_YEARS = 30;
export const MAX_VOL = 5;
export const MIN_RATE = -0.05;
export const MAX_RATE = 1;

export const optionSchema = z.object({
  spot: z.coerce
    .number({ invalid_type_error: "Enter a number" })
    .positive("Spot must be greater than 0")
    .max(MAX_PRICE, "Spot is unrealistically large"),
  strike: z.coerce
    .number({ invalid_type_error: "Enter a number" })
    .positive("Strike must be greater than 0")
    .max(MAX_PRICE, "Strike is unrealistically large"),
  time_to_expiry: z.coerce
    .number({ invalid_type_error: "Enter a number" })
    .positive("Time to expiry must be greater than 0")
    .max(MAX_YEARS, `At most ${MAX_YEARS} years`),
  risk_free_rate: z.coerce
    .number({ invalid_type_error: "Enter a number" })
    .min(MIN_RATE, "Rates below -5% are not supported")
    .max(MAX_RATE, "Rates above 100% are not supported"),
  volatility: z.coerce
    .number({ invalid_type_error: "Enter a number" })
    .positive("Volatility must be greater than 0")
    .max(MAX_VOL, "Volatility above 500% is not supported"),
  dividend_yield: z.coerce
    .number({ invalid_type_error: "Enter a number" })
    .min(0, "Dividend yield cannot be negative")
    .max(MAX_RATE, "Dividend yield above 100% is not supported"),
  option_type: z.enum(["call", "put"]),
  exercise: z.enum(["european", "american"]),
});

export type OptionFormValues = z.infer<typeof optionSchema>;

export const DEFAULT_OPTION: OptionFormValues = {
  spot: 100,
  strike: 100,
  time_to_expiry: 1,
  risk_free_rate: 0.05,
  volatility: 0.2,
  dividend_yield: 0,
  option_type: "call",
  exercise: "european",
};
