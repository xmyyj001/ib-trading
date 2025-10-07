import pkgutil
import inspect
from pathlib import Path

# A dictionary to hold all discovered strategy classes
STRATEGIES = {}

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
                    print(f"Discovered and registered strategy: '{strategy_key}'")
        except Exception as e:
            print(f"Could not import or inspect module {name}: {e}")

# 1. Run the automatic discovery process first
_discover_strategies()

# 2. Manually register the specific test strategy if it exists.
# This ensures it's available under the correct key for testing.
try:
    from .test_signal_generator import TestSignalGenerator
    STRATEGIES['testsignalgenerator'] = TestSignalGenerator
    print(f"Manually overrode/registered test strategy: 'testsignalgenerator'")
except ImportError:
    # This is not an error; the test file may not always be present.
    pass
