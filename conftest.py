"""Root configuration for StockTake's own suite.

`pytest_plugins` has to be declared in the root conftest, which is the only reason this file exists. `pytester` runs a real pytest inside a
scratch directory, which is how the plugin in `stocktake.pytest_plugin` is tested: asserting on what a project's suite actually sees is worth
far more than asserting on the plugin's internals.
"""

pytest_plugins = ["pytester"]
