import inspect
import logging
import os
import pkgutil
from pathlib import Path

# A dictionary to hold all discovered strategy classes
STRATEGIES = {}
_logger = logging.getLogger(__name__)

def _log(msg: str) -> None:
    if _logger.handlers:
        _logger.info(msg)
    else:
        print(msg)

def _discover_strategies():
    """
    Dynamically discovers and imports all strategy classes in this directory.
    """
    # Local import to avoid circular dependency at module level
    from .strategy import Strategy

    package_path = Path(__file__).parent
    package_name = package_path.name

    for _, name, _ in pkgutil.iter_modules([str(package_path)]):
        try:
            module = __import__(f"{package_name}.{name}", fromlist=["*"])
            for item_name, item in inspect.getmembers(module, inspect.isclass):
                if issubclass(item, Strategy) and item is not Strategy:
                    strategy_key = item.__name__.lower()
                    STRATEGIES[strategy_key] = item
                    _log(f"Discovered and registered strategy: '{strategy_key}'")
        except Exception as e:
            _log(f"Could not import or inspect module {name}: {e}")

# 1. Run the automatic discovery process first
_discover_strategies()

# 2. Optional manual registration for the legacy test strategy.
ENABLE_TEST_OVERRIDE = os.environ.get("ENABLE_TEST_STRATEGY_OVERRIDE", "").lower() in ("1", "true", "yes")
if ENABLE_TEST_OVERRIDE:
    try:
        from .test_signal_generator import TestSignalGenerator
        STRATEGIES['testsignalgenerator'] = TestSignalGenerator
        _log("Manually overrode/registered test strategy: 'testsignalgenerator'")
    except ImportError:
        pass
else:
    _log("Test strategy override disabled; set ENABLE_TEST_STRATEGY_OVERRIDE=1 to re-enable.")

if STRATEGIES:
    _log(f"Strategy registry initialized with: {', '.join(sorted(STRATEGIES.keys()))}")
