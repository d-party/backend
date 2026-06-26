"""Shared pytest configuration.

Channels' ``RedisChannelLayer`` keeps a connection pool whose asyncio locks are
bound to the event loop of the first test that uses them; reusing it across the
fresh event loops that ``TransactionTestCase`` creates per test leads to
non-deterministic "bound to a different event loop" errors. Tests don't need a
real Redis, so we swap in the in-process ``InMemoryChannelLayer`` and clear the
cached backend around every test for full isolation.
"""

import pytest


@pytest.fixture(autouse=True)
def use_in_memory_channel_layer(settings):
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }
    from channels import layers

    layers.channel_layers.backends.clear()
    yield
    layers.channel_layers.backends.clear()


@pytest.fixture(autouse=True)
def use_local_memory_cache(settings):
    """Use an in-process cache so the stats cache needs no real Redis in tests.

    Each test gets its own ``LOCATION`` so cached statistics never leak between
    tests; ``cache.clear()`` keeps a single test's assertions isolated too.
    """
    from django.core.cache import cache

    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "stats-tests",
        },
    }
    cache.clear()
    yield
    cache.clear()
