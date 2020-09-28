import subprocess
import sys
import tempfile
from collections import OrderedDict

from git_py_pre_receive_hook.utils import CommandMixin, get_exe_path


class Commit(object):
    def __init__(self, old_sha1, new_sha1, ref):
        self.old_sha1 = old_sha1
        self.new_sha1 = new_sha1
        self.ref = ref

    @property
    def old_is_null(self):
        return self.old_sha1 == "0000000000000000000000000000000000000000"

    @property
    def revisions(self):
        return "%s...%s" % (self.old_sha1, self.new_sha1)


class DefaultChecker(CommandMixin):
    BLACK_EXE_PATH = get_exe_path("black")
    FLAKE8_EXE_PATH = get_exe_path("flake8")

    BLACK_COMMAND_ARGS = [
        "--line-length",
        "120",
        "--diff",
        "-q",
    ]
    FLAKE8_COMMAND_ARGS = ["--max-line-length=120", "--ignore=E203,E731"]

    BLACK_COMMAND_FORMAT_ERROR_CODE = 123
    BLACK_FORMAT_ERROR_MESSAGE = "can not format, maybe syntax error!"

    FLAKE8_COMMAND_ERROR_CODE = 1

    DIFFERENCE_HIDE_MORE_LINES = 20

    def __init__(self):
        if self.BLACK_EXE_PATH is None:
            raise RuntimeError('can not find "black" command.')

    def check(self, filename, content):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf8") as fp:
            fp.write(content)
            fp.flush()

            r = self.run_command([self.FLAKE8_EXE_PATH] + self.FLAKE8_COMMAND_ARGS + [fp.name])
            if r.return_code == self.FLAKE8_COMMAND_ERROR_CODE:
                return self._format_flake8_output(fp.name, filename, r.stdout)

            r = self.run_command([self.BLACK_EXE_PATH] + self.BLACK_COMMAND_ARGS + [fp.name])
            if r.return_code == self.BLACK_COMMAND_FORMAT_ERROR_CODE:
                return self.BLACK_FORMAT_ERROR_MESSAGE

            self.check_command_result(r)

            # black command diff output
            if r.stdout:
                diff = r.stdout.split("\n")[2:]
                if len(diff) > self.DIFFERENCE_HIDE_MORE_LINES:
                    diff = diff[: self.DIFFERENCE_HIDE_MORE_LINES]
                    diff.append("")
                    diff.append("Omit more ......")

                return "\n".join(["difference:"] + diff)

            return None

    def _format_flake8_output(self, temp_filename, filename, output):
        return "\n".join([line.replace("%s:" % temp_filename, "%s:" % filename) for line in output.strip().split("\n")])


class Hook(CommandMixin):
    SKIP_MORE_ERRORS = 3

    GIT_EXE_PATH = get_exe_path("git")

    CHECK_ONLY = True

    def __init__(self, commits):
        if self.GIT_EXE_PATH is None:
            raise RuntimeError('can not find "git" command.')

        self.changed_files = self._collect_changed_files(commits)
        self.checker = DefaultChecker()

    def run(self):
        errors = 0
        for filename, revision in self.changed_files.items():
            content = self._file_content(filename, revision)
            if not self._is_py_file(filename, content):
                continue

            error = self._check_file(filename, content)
            if not error:
                continue

            self._print_error(filename, error)

            errors += 1
            if errors >= self.SKIP_MORE_ERRORS:
                return 0 if self.CHECK_ONLY else 1

        if errors:
            sys.stderr.write("\n")
            sys.stderr.flush()

        return (0 if self.CHECK_ONLY else 1) if errors > 0 else 0

    def _print_error(self, filename, error):
        sys.stderr.write("\n" + "-" * 60 + "\n")
        sys.stderr.write('bad format for file "%s", please format by "black" command.\n' % filename)
        sys.stderr.write("\n" + error.strip() + "\n")
        sys.stderr.flush()

    def _check_file(self, filename, content):
        return self.checker.check(filename, content)

    def _collect_changed_files(self, commits):
        ret = OrderedDict()
        for commit in commits:
            for filename, revision in self._changed_files(commit).items():
                if filename not in ret:
                    ret[filename] = revision
        return ret

    def _is_py_file(self, filename, content):
        if filename.endswith(".py"):
            return True

        first_line = content.splitlines()[0]
        return first_line.startswith("#!") and first_line.find("python") > -1

    def _file_content(self, filename, revision):
        r = self.run_command([self.GIT_EXE_PATH, "show", revision + ":" + filename])
        self.check_command_result(r)
        return r.stdout

    def _changed_files(self, commit):
        if commit.old_is_null:
            cmd = [self.GIT_EXE_PATH, "ls-tree", "-r", commit.new_sha1, "--name-only"]
        else:
            cmd = [
                self.GIT_EXE_PATH,
                "show",
                commit.revisions,
                "--pretty=format:",
                "--name-only",
            ]

        r = self.run_command(cmd)
        self.check_command_result(r)

        return {filename: commit.new_sha1 for filename in r.stdout.strip().split("\n") if filename}


def main():
    commits = []
    for line in sys.stdin:
        try:
            args = line.strip().split()
        except IOError as ex:
            sys.stderr.write(str(ex) + "\n")
            sys.exit(1)

        if len(args) != 3:
            raise ValueError("invalid commit: %s" % line)

        commits.append(Commit(args[0], args[1], args[2]))

    try:
        return Hook(commits).run()
    except subprocess.CalledProcessError as ex:
        sys.stderr.write(str(ex) + "\n")
        sys.exit(ex.returncode)


if __name__ == "__main__":
    main()
