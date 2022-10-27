import datetime
import logging
from pathlib import Path
from shutil import which

from bx_py_utils.path import assert_is_file

from manageprojects.subprocess_utils import verbose_check_call, verbose_check_output


logger = logging.getLogger(__name__)


class GitError(BaseException):
    """Base class for all git errors"""


class NoGitRepoError(GitError):
    def __init__(self, path):
        super().__init__(f'"{path}" is not a git repository')


class GitBinNotFoundError(GitError):
    def __init__(self):
        super().__init__('Git executable not found in PATH')


def get_git_root(path: Path):
    if len(path.parts) == 1 or not path.is_dir():
        return None

    if Path(path / '.git').is_dir():
        return path

    return get_git_root(path=path.parent)


class Git:
    def __init__(self, *, cwd: Path, detect_root: bool = True):
        if detect_root:
            self.cwd = get_git_root(cwd)
            if not self.cwd:
                raise NoGitRepoError(cwd)
        else:
            self.cwd = cwd

        self.git_bin = which('git')
        if not self.git_bin:
            raise GitBinNotFoundError()

    def git_verbose_check_call(self, *popenargs, **kwargs):
        popenargs = [self.git_bin, *popenargs]
        return verbose_check_call(*popenargs, cwd=self.cwd, **kwargs)

    def git_verbose_check_output(self, *popenargs, **kwargs):
        popenargs = [self.git_bin, *popenargs]
        return verbose_check_output(*popenargs, cwd=self.cwd, **kwargs)

    def get_current_hash(self, commit='HEAD', verbose=True) -> str:
        output = self.git_verbose_check_output('rev-parse', '--short', commit, verbose=verbose)
        if git_hash := output.strip():
            assert len(git_hash) == 7, f'No git hash from: {output!r}'
            return git_hash

        raise AssertionError(f'No git hash from: {output!r}')

    def get_commit_date(self, commit='HEAD', verbose=True) -> datetime.datetime:
        output = self.git_verbose_check_output(
            'show', '-s', '--format=%cI', commit, verbose=verbose
        )
        if raw_date := output.strip():
            # e.g.: "2022-10-25 20:43:10 +0200"
            return datetime.datetime.fromisoformat(raw_date)

        raise AssertionError(f'No commit date from: {output!r}')

    def diff(
        self,
        reference1,
        reference2,
        patch=True,
        minimal=True,
        no_prefix=True,
        no_color=True,
        verbose=True,
    ) -> str:
        args = []
        if patch:
            args.append('--patch')
        if minimal:
            args.append('--minimal')
        if no_prefix:
            args.append('--no-prefix')
        if no_color:
            args.append('--no-color')

        output = self.git_verbose_check_output(
            'diff', *args, reference1, reference2, verbose=verbose, exit_on_error=True
        )
        return output

    def init(self, branch_name='main', verbose=True) -> Path:
        output = self.git_verbose_check_output(
            'init', '-b', branch_name, verbose=verbose, exit_on_error=True
        )
        assert 'initialized' in output.lower(), f'Seems there is an error: {output}'
        self.cwd = get_git_root(self.cwd)
        return self.cwd

    def config(self, key, value, verbose=True):
        output = self.git_verbose_check_output(
            'config', key, value, verbose=verbose, exit_on_error=True
        )
        assert not output, f'Seems there is an error: {output}'

    def get_config(self, key, verbose=True):
        output = self.git_verbose_check_output(
            'config', '--get', key, verbose=verbose, exit_on_error=True
        )
        return output.strip()

    def add(self, spec, verbose=True) -> None:
        output = self.git_verbose_check_output('add', spec, verbose=verbose, exit_on_error=True)
        assert not output, f'Seems there is an error: {output}'

    def commit(self, comment, verbose=True) -> str:
        output = self.git_verbose_check_output(
            'commit', '--message', comment, verbose=verbose, exit_on_error=True
        )
        assert comment in output, f'Seems there is an error: {output}'
        return output

    def reflog(self, verbose=True) -> str:
        return self.git_verbose_check_output('reflog', verbose=verbose, exit_on_error=True)

    def ls_files(self, verbose=True) -> list[Path]:
        output = self.git_verbose_check_output('ls-files', verbose=verbose, exit_on_error=True)
        file_paths = []
        for line in output.splitlines():
            file_path = self.cwd / line
            assert_is_file(file_path)
            file_paths.append(file_path)
        return sorted(file_paths)
