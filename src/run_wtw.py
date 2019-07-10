from _pytest.pathlib import Path
from unidiff import PatchSet
import os
import pytest
import sqlite3
import sys


class WTWPlugin:
    """ Plugin which implements the --wtw (run only tests that cover changed lines) option """

    def __init__(self, config):
        self.config = config
        self.active = all(config.getoption(opt) for opt in ("wtw", "wtwdb"))
        if self.active:
            wtw_path = config.getoption("wtw")
            with open(wtw_path) as wtw_file:
                self.diff = PatchSet(wtw_file)
            self.baseline = sqlite3.connect(config.getoption("wtwdb"))
        self._skipped_files = 0
        self._report_status = None

    def who_tested_what(self):
        """
        Returns a nested dict of files -> classes -> functions.

        If the file maps to None, then the whole file should be run.
        """
        try:
            return self._who_tested_what
        except AttributeError:
            rootpath = Path(self.config.rootdir)
            files_changed = set()
            source_lines_changed = set()

            for file in self.diff:
                files_changed.add(rootpath / file.path)
                for hunk in file:
                    for line in hunk:
                        if line.source_line_no is not None:
                            source_lines_changed.add((file.path, line.source_line_no))

            with self.baseline as cursor:
                cursor.execute("""DROP TABLE IF EXISTS diff_lines""")
                cursor.execute(
                    """
                    CREATE TABLE diff_lines(
                        path TEXT,
                        line INTEGER
                    )
                    """
                )
                cursor.executemany(
                    "INSERT INTO diff_lines VALUES (?, ?)", source_lines_changed
                )

            with self.baseline as cursor:
                all_files = []
                for (abspath,) in cursor.execute(
                    """
                    SELECT DISTINCT f.path
                    FROM file f
                    """
                ):
                    all_files.append(abspath)
                common_prefix = os.path.commonprefix(all_files)
                if not common_prefix.endswith("/"):
                    common_prefix = os.path.dirname(common_prefix)

            contexts = set()
            context_files = set()
            with self.baseline as cursor:
                for (context,) in cursor.execute(
                    """
                    SELECT DISTINCT c.context
                    FROM diff_lines dl
                    JOIN file f
                    ON ? || dl.path = f.path
                    JOIN line l
                    ON dl.line = l.lineno
                    AND l.file_id = f.id
                    JOIN context c
                    ON l.context_id = c.id
                    WHERE
                        c.context <> ''
                    """,
                    [common_prefix],
                ):
                    specifier, _, calltype = context.rpartition("|")
                    filepath, _, _ = specifier.partition("::")
                    context_files.add(rootpath / filepath)
                    contexts.add(specifier)

            self._who_tested_what = (files_changed, context_files, contexts)
        return self._who_tested_what

    def pytest_ignore_collect(self, path):
        """
        Ignore this file path if we are in --wtw mode and it is not in the list of
        files to test.
        """
        if self.active and self.config.getoption("wtw") and path.isfile():
            (files_changed, context_files, _) = self.who_tested_what()
            if Path(path) not in (files_changed | context_files):
                self._skipped_files += 1
                return True
            else:
                return False

    def pytest_report_collectionfinish(self):
        if self.active and self.config.getoption("verbose") >= 0:
            return "run-last-failure: %s" % self._report_status

    def pytest_collection_modifyitems(self, session, config, items):
        if not self.active:
            return

        (files_changed, _, contexts) = self.who_tested_what()

        selected_items = [
            item
            for item in items
            if item.nodeid in contexts
            or any(
                Path(item.nodeid.rpartition("::")[0]) for changed_file in files_changed
            )
        ]
        selected_set = set(selected_items)
        skipped_items = [item for item in items if item not in selected_set]

        items[:] = selected_items
        config.hook.pytest_deselected(items=skipped_items)

        noun = "tests" if len(selected_items) else "test"
        self._report_status = "{} {} cover the changed lines ({} deselected)".format(
            len(selected_items), noun, len(skipped_items)
        )

        if self._skipped_files > 0:
            files_noun = "file" if self._skipped_files == 1 else "files"
            self._report_status += " (skipped {files} {files_noun})".format(
                files=self._skipped_files, files_noun=files_noun
            )


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    config.pluginmanager.register(WTWPlugin(config), "wtwplugin")


def pytest_addoption(parser):
    group = parser.getgroup("general")
    group.addoption(
        "--wtw",
        "--who-tests-what",
        action="store",
        dest="wtw",
        help="Run the tests that cover the supplied diff",
    )
    group.addoption(
        "--wtwdb",
        "--who-tests-what-db",
        action="store",
        dest="wtwdb",
        help="Use this coverage file as a who-tests-what baseline",
    )
