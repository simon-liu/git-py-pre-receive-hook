import pkgutil
import subprocess
import sys
import tempfile
from collections import OrderedDict, namedtuple

import yaml

from git_py_pre_receive_hook.utils import CommandMixin, get_exe_path

ChangedFile = namedtuple("ChangedFile", ["filename", "revision", "ref"])


class Config(object):
    DEFAULT_YML_CONTENT = pkgutil.get_data("git_py_pre_receive_hook", "py-pre-receive-hook.yml")

    def __init__(self, yml_content):
        self.settings = yaml.full_load(yml_content or self.DEFAULT_YML_CONTENT)

    @property
    def black_command_args(self):
        return self.settings.get("black_cmd_args", [])

    @property
    def flake8_cmd_args(self):
        return self.settings.get("flake8_cmd_args", [])

    @property
    def check_only(self):
        return self.settings.get("check_only", False)

    @property
    def ignore_files(self):
        return set(self.settings.get("ignore_files", []))

    @property
    def check_master_only(self):
        return self.settings.get("check_master_only", True)


class Commit(object):
    def __init__(self, old_sha1, new_sha1, ref):
        self.old_sha1 = old_sha1
        self.new_sha1 = new_sha1
        self.ref = ref

    @property
    def old_is_null(self):
        return self.old_sha1 == "0000000000000000000000000000000000000000"

    @property
    def is_deleting(self):
        return self.new_sha1 == "0000000000000000000000000000000000000000"

    @property
    def revisions(self):
        return "%s...%s" % (self.old_sha1, self.new_sha1)


class DefaultChecker(CommandMixin):
    BLACK_EXE_PATH = get_exe_path("black")
    FLAKE8_EXE_PATH = get_exe_path("flake8")

    BLACK_COMMAND_FORMAT_ERROR_CODE = 123
    BLACK_FORMAT_ERROR_MESSAGE = "can not format, maybe syntax error!"

    FLAKE8_COMMAND_ERROR_CODE = 1

    DIFFERENCE_HIDE_MORE_LINES = 20

    def __init__(self, config):
        if self.BLACK_EXE_PATH is None:
            raise RuntimeError('can not find "black" command.')

        if self.FLAKE8_EXE_PATH is None:
            raise RuntimeError('can not find "flake8" command.')

        self.config = config
        self.black_version = self.run_command([self.BLACK_EXE_PATH, "--version"]).stdout
        self.flake8_version = self.run_command([self.FLAKE8_EXE_PATH, "--version"]).stdout

    def check(self, filename, content):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf8") as fp:
            fp.write(content)
            fp.flush()

            r = self.run_command([self.FLAKE8_EXE_PATH] + self.config.flake8_cmd_args + [fp.name])
            if r.return_code == self.FLAKE8_COMMAND_ERROR_CODE:
                return self._format_flake8_output(fp.name, filename, r.stdout)

            r = self.run_command([self.BLACK_EXE_PATH] + self.config.black_command_args + [fp.name])
            if r.return_code == self.BLACK_COMMAND_FORMAT_ERROR_CODE:
                return self.BLACK_FORMAT_ERROR_MESSAGE

            self.check_command_result(r)
            if r.stdout:
                return self._format_black_output(
                    " ".join(["black"] + self.config.black_command_args + [filename]), r.stdout
                )

            return None

    def _format_black_output(self, black_cmd, stdout):
        diff = stdout.split("\n")[2:]
        if len(diff) > self.DIFFERENCE_HIDE_MORE_LINES:
            diff = diff[: self.DIFFERENCE_HIDE_MORE_LINES]
            diff.append("")
            diff.append("Omit more ......")

        return "\n".join(
            self._black_version() + ["black format command: " + black_cmd] + ["Please apply patch:\n"] + diff
        )

    def _format_flake8_output(self, temp_filename, filename, output):
        lines = self._flake8_version() + output.strip().split("\n")
        return "\n".join([line.replace("%s:" % temp_filename, "%s:" % filename) for line in lines])

    def _flake8_version(self):
        return ["flake8"] + self.flake8_version.split("\n")

    def _black_version(self):
        return self.black_version.split("\n")


class Hook(CommandMixin):
    SKIP_MORE_ERRORS = 3

    GIT_EXE_PATH = get_exe_path("git")

    GIT_FILE_DOES_NOT_EXISTS_ERROR = 128

    CONF_FILE = ".py-pre-receive-hook.yml"

    def __init__(self, commits):
        if self.GIT_EXE_PATH is None:
            raise RuntimeError('can not find "git" command.')

        self.config = Config(self._load_config_content())
        self.changed_files = self._collect_changed_files(commits)
        self.checker = DefaultChecker(self.config)

    def run(self):
        errors = 0
        for changed_file in self.changed_files.values():
            if self.config.check_master_only and not self._is_master(changed_file.ref):
                continue

            if not self._file_exists(changed_file.filename, changed_file.revision):
                continue

            content = self._file_content(changed_file.filename, changed_file.revision)
            if not self._is_py_file(changed_file.filename, content):
                continue

            error = self._check_file(changed_file.filename, content)
            if not error:
                continue

            self._print_error(changed_file.filename, error)

            errors += 0 if self._ignore(changed_file.filename) else 1
            if errors >= self.SKIP_MORE_ERRORS:
                return 0 if self.config.check_only else 1

        if errors:
            sys.stderr.write("\n")
            sys.stderr.flush()

        return (0 if self.config.check_only else 1) if errors > 0 else 0

    def _ignore(self, filename):
        if filename in self.config.ignore_files:
            return True

        for v in self.config.ignore_files:
            if v.endswith("/") and filename.startswith(v):
                return True

        return False

    def _print_error(self, filename, error):
        lines = [
            "\n" + "-" * 60,
            f'bad format for file "{filename}".',
            f"\n{error.strip()}",
        ]
        sys.stderr.write("\n".join(lines))
        sys.stderr.flush()

    def _check_file(self, filename, content):
        return self.checker.check(filename, content)

    def _collect_changed_files(self, commits):
        ret = OrderedDict()
        for commit in commits:
            if commit.is_deleting:
                continue

            for filename, revision in self._changed_files(commit).items():
                if filename not in ret:
                    ret[filename] = ChangedFile(filename=filename, revision=revision, ref=commit.ref)
        return ret

    def _is_py_file(self, filename, content):
        if filename.endswith(".py"):
            return True

        if not content.strip():
            return False

        first_line = content.splitlines()[0]
        return first_line.startswith("#!") and first_line.find("python") > -1

    def _file_exists(self, filename, revision):
        try:
            r = self.run_command([self.GIT_EXE_PATH, "show", revision + ":" + filename])
        except UnicodeDecodeError:
            return False

        return r.return_code != self.GIT_FILE_DOES_NOT_EXISTS_ERROR

    def _file_content(self, filename, revision):
        r = self.run_command([self.GIT_EXE_PATH, "show", revision + ":" + filename])
        self.check_command_result(r)
        return r.stdout

    def _is_master(self, ref):
        return ref == "refs/heads/master"

    def _load_config_content(self):
        if not self._file_exists(self.CONF_FILE, "HEAD"):
            return ""

        return self._file_content(self.CONF_FILE, "HEAD")

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
