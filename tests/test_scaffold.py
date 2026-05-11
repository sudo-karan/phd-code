"""
Module 1 smoke test.

This is the most basic sanity check: can we import the package and is the
expected version string set? If this fails, the install or path setup is wrong.
"""


def test_package_imports():
    import fmu  # noqa: F401


def test_package_has_version():
    import fmu

    assert hasattr(fmu, "__version__")
    assert isinstance(fmu.__version__, str)
    assert len(fmu.__version__) > 0


def test_subpackages_import():
    """All subpackages should be importable, even if mostly empty for now."""
    import fmu.metrics  # noqa: F401
    import fmu.stages  # noqa: F401
    import fmu.utils  # noqa: F401
