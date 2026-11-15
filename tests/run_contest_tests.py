"""Build/run STM32 pure-logic tests; keep temporary outputs inside this folder."""
import argparse
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--cc", default="gcc", help="Host GCC executable")
args = parser.parse_args()
tests = Path(__file__).resolve().parent
hardware = tests.parent / "8.目标追踪【闭环】" / "HARDWARE"
with tempfile.TemporaryDirectory(prefix="contest-test-", dir=tests) as directory:
    executable = Path(directory) / "test_contest.exe"
    command = [args.cc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-DCONTEST_HOST_TEST"]
    command += ["-I" + str(hardware / name) for name in ("STABILIZER", "K230", "APP")]
    command += [str(tests / "test_contest.c"), str(hardware / "STABILIZER" / "stabilizer.c"),
                str(hardware / "K230" / "k230.c"), "-o", str(executable)]
    subprocess.run(command, check=True)
    subprocess.run([str(executable)], check=True)
