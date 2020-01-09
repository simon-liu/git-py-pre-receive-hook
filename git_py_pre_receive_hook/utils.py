import os
import subprocess
from collections import namedtuple

CommandResult = namedtuple(
    "CommandResult", ["command", "return_code", "stdout", "stderr"]
)


def get_exe_path(exe):
    for dir_path in os.environ["PATH"].split(":"):
        path = dir_path.strip('"') + "/" + exe
        if os.access(path, os.X_OK):
            return path


class CommandMixin(object):
    def run_command(self, cmd):
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate()
        if out and out[-1] == b"\n":
            out = out[:-1]

        return CommandResult(
            command=cmd,
            return_code=proc.returncode,
            stdout=None if out is None else out.decode("utf8"),
            stderr=None if err is None else err.decode("utf8"),
        )

    def check_command_result(self, r):
        if r.return_code:
            raise RuntimeError("run command error: %s" % str(r))
