"""Pluggable firmware build backends.

nff can drive more than one underlying build tool. The default ``arduino`` backend
(arduino-cli) lives in :mod:`nff.tools.toolchain`; the ``platformio`` backend lives
here. :mod:`nff.tools.toolchain` is the single dispatcher that picks the active
backend (via ``NFF_BUILD_BACKEND`` env / config) and delegates to it, so every
caller keeps using the stable ``toolchain.*`` surface.
"""
