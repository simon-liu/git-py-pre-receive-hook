from git_py_pre_receive_hook import VERSION
from setuptools import setup


def readfile_as_string(fn):
    with open(fn, "r", encoding="utf8") as fin:
        return fin.read()


REQUIRED = readfile_as_string("requirements.txt").split("\n")
README = readfile_as_string("README.rst")

setup(
    name="git_py_pre_receive_hook",
    version=".".join(str(v) for v in VERSION),
    url="https://github.com/simon-liu/git-py-pre-receive-hook",
    packages=["git_py_pre_receive_hook"],
    python_requires=">=3.6",
    install_requires=REQUIRED,
    author="LiuZenglu",
    author_email="zenglu.liu@gmail.com",
    license="MIT",
    platforms="POSIX",
    description="Git pre-receive hook to check commits and code style",
    long_description=README,
    entry_points={
        "console_scripts": [
            "git-py-pre-receive=git_py_pre_receive_hook.pre_receive:main"
        ]
    },
)
