# Licensed under the Apache License: http://www.apache.org/licenses/LICENSE-2.0
# For details: https://github.com/nedbat/coverage_pytest_plugin/blob/master/NOTICE.txt

"""A pytest plugin to define dynamic contexts"""

import coverage
import pytest


class ContextPlugin(object):
    def __init__(self, config):
        self.config = config
        self.active = config.getoption("pytest-contexts")

    def pytest_runtest_setup(self, item):
        self.doit(item, "setup")

    def pytest_runtest_teardown(self, item):
        self.doit(item, "teardown")

    def pytest_runtest_call(self, item):
        self.doit(item, "call")

    def doit(self, item, when):
        if self.active:
            current = coverage.Coverage.current()
            if current is not None:
                context = "{item.nodeid}|{when}".format(item=item, when=when)
                current.switch_context(context)


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    config.pluginmanager.register(ContextPlugin(config), "contextplugin")


def pytest_addoption(parser):
    group = parser.getgroup("general")
    group.addoption(
        "--pytest-contexts",
        action="store_true",
        dest="pytest-contexts",
        help="Capture the pytest contexts that coverage is being captured in",
    )
