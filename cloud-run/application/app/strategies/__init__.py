import pkgutil
import inspect
from pathlib import Path

# A dictionary to hold all discovered strategy classes
STRATEGIES = {}

def _discover_strategies():
    """
    Dynamically discovers and imports all strategy classes in this directory.
    Strategies are identified by being subclasses of the 'Strategy' base class.
    The key in the STRATEGIES dictionary is the lowercase class name.
    """
    from .strategy import Strategy  # Local import to avoid circular dependency

    package_path = Path(__file__).parent
    package_name = package_path.name

    for _, name, _ in pkgutil.iter_modules([str(package_path)]):
        # Import the module
        module = __import__(f"{package_name}.{name}", fromlist=["*"])

        # Find all classes in the imported module
        for item_name, item in inspect.getmembers(module, inspect.isclass):
            # Check if the class is a subclass of Strategy and not Strategy itself
            if issubclass(item, Strategy) and item is not Strategy:
                # Register the strategy using its lowercase class name as the key
                strategy_key = item.__name__.lower()
                STRATEGIES[strategy_key] = item
                print(f"Discovered and registered strategy: '{strategy_key}'")

# Run the discovery process when the package is imported
_discover_strategies()