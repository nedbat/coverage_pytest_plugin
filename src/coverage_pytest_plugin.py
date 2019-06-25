# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/nedbat/coverage_pytest_plugin/blob/master/NOTICE.txt

"""A pytest plugin to define dynamic contexts"""

import coverage

def pytest_runtest_setup(item):
    doit(item, "setup")

def pytest_runtest_teardown(item):
    doit(item, "teardown")

def pytest_runtest_call(item):
    doit(item, "call")

def doit(item, when):
    current = coverage.Coverage.current()
    if current is not None:
        context = "{item.nodeid}|{when}".format(item=item, when=when)
        current.switch_context(context)
