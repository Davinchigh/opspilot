"""Runs the tests and, on GitHub Actions, shows each failure as an annotation."""
import sys
import unittest

result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover("tests", top_level_dir="."))
for test, trace in result.errors + result.failures:
    print(f"::error title={test.id()}::" + trace[-1500:].replace("%", "%25").replace("\n", "%0A"))
sys.exit(not result.wasSuccessful())
