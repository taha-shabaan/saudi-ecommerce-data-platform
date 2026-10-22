"""
Tests for Seam 2: Generator Registry & Multi-Locale Provider Factory
"""

import pytest
from app.core.registry import GeneratorRegistry, GeneratorContext


def test_registry_has_core_generators():
    """Verify all standard generator types are registered."""
    registered = GeneratorRegistry.list_generators()
    expected = [
        "autoincrement", "uuid", "full_name", "first_name", "last_name",
        "email", "phone", "street_address", "city", "country",
        "date_time", "numeric_range", "categorical", "boolean", "text"
    ]
    for exp in expected:
        assert exp in registered, f"Missing generator: {exp}"


def test_multi_locale_generation():
    """Verify generation across Arabic, English, and German locales."""
    # Egyptian Arabic
    ctx_eg = GeneratorContext(locale="ar_EG", row_index=0)
    name_eg = GeneratorRegistry.generate("full_name", ctx_eg)
    assert isinstance(name_eg, str) and len(name_eg) > 0

    # German
    ctx_de = GeneratorContext(locale="de_DE", row_index=0)
    name_de = GeneratorRegistry.generate("full_name", ctx_de)
    assert isinstance(name_de, str) and len(name_de) > 0

    # US
    ctx_us = GeneratorContext(locale="en_US", row_index=0)
    name_us = GeneratorRegistry.generate("full_name", ctx_us)
    assert isinstance(name_us, str) and len(name_us) > 0


def test_numeric_range_generator():
    """Verify numeric range parameters."""
    ctx = GeneratorContext(
        locale="en_US",
        row_index=0,
        params={"min": 50, "max": 100}
    )
    for _ in range(20):
        val = GeneratorRegistry.generate("numeric_range", ctx)
        assert 50 <= val <= 100


def test_categorical_generator():
    """Verify categorical choices."""
    choices = ["PENDING", "APPROVED", "REJECTED"]
    ctx = GeneratorContext(
        locale="en_US",
        row_index=0,
        params={"choices": choices}
    )
    for _ in range(20):
        val = GeneratorRegistry.generate("categorical", ctx)
        assert val in choices


def test_data_noise_injection():
    """Verify data noise rate generates whitespace, sentinel nulls, or corruptions."""
    ctx = GeneratorContext(
        locale="en_US",
        row_index=0,
        noise_rate=1.0 # 100% noise
    )
    noisy_vals = [GeneratorRegistry.generate("email", ctx) for _ in range(10)]
    
    # At 100% noise, values should contain whitespace, sentinels, or malformed strings
    has_anomaly = any(
        isinstance(v, str) and (v.startswith(" ") or v in ["N/A", "NULL", "-", ""] or "@" not in v)
        for v in noisy_vals
    )
    assert has_anomaly is True
