import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.repo_resolver import RepoResolutionBlocked, RepoResolutionFailed, resolve_runtime_repo


class RepoResolverTests(unittest.TestCase):
    def setUp(self):
        self.tempdirs = []

    def tearDown(self):
        os.environ.pop("XYN_RUNTIME_REPO_MAP", None)
        for tmpdir in self.tempdirs:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _temp_repo(self) -> Path:
        tmpdir = tempfile.mkdtemp(prefix="repo-resolver-")
        self.tempdirs.append(tmpdir)
        repo_path = Path(tmpdir)
        subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, check=True, capture_output=True, text=True)
        return repo_path

    def test_known_repo_resolves_correctly(self):
        repo = self._temp_repo()
        os.environ["XYN_RUNTIME_REPO_MAP"] = f'{{"xyn":["{repo}"]}}'
        resolved = resolve_runtime_repo("xyn")
        self.assertEqual(resolved.repo_key, "xyn")
        self.assertEqual(resolved.path, repo.resolve())

    def test_unknown_repo_fails_cleanly(self):
        os.environ["XYN_RUNTIME_REPO_MAP"] = "{}"
        with self.assertRaises(RepoResolutionFailed):
            resolve_runtime_repo("xyn-platform")

    def test_missing_unmounted_repo_fails_cleanly(self):
        os.environ["XYN_RUNTIME_REPO_MAP"] = '{"xyn":["/definitely/missing/path"]}'
        with self.assertRaises(RepoResolutionFailed):
            resolve_runtime_repo("xyn")

    def test_non_git_path_fails_cleanly(self):
        tmpdir = tempfile.mkdtemp(prefix="repo-resolver-nongit-")
        self.tempdirs.append(tmpdir)
        os.environ["XYN_RUNTIME_REPO_MAP"] = f'{{"xyn":["{tmpdir}"]}}'
        with self.assertRaises(RepoResolutionFailed):
            resolve_runtime_repo("xyn")

    def test_ambiguous_mapping_blocks(self):
        repo1 = self._temp_repo()
        repo2 = self._temp_repo()
        os.environ["XYN_RUNTIME_REPO_MAP"] = f'{{"xyn":["{repo1}","{repo2}"]}}'
        with self.assertRaises(RepoResolutionBlocked):
            resolve_runtime_repo("xyn")

    def test_absolute_path_override_resolves(self):
        repo = self._temp_repo()
        resolved = resolve_runtime_repo(str(repo))
        self.assertEqual(resolved.path, repo.resolve())


if __name__ == "__main__":
    unittest.main()
