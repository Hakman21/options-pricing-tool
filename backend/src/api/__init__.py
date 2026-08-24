"""HTTP adapter over the :mod:`option_pricing` library.

This package knows about HTTP; the pricing library knows about mathematics. Nothing
in ``option_pricing`` imports anything from here, and that direction is enforced by
convention and checked by the fact that every pricing test runs without a server.
"""
