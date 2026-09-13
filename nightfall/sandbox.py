"""Platform-backed command sandboxing."""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path.cwd().resolve()


class SandboxUnavailable(RuntimeError):
    """Raised when a platform sandbox cannot be initialized."""


class Backend:
    label = "none"

    def name(self) -> str:
        return self.label

    def run(self, command: str, timeout: int = 60) -> subprocess.CompletedProcess:
        raise NotImplementedError


class SeatbeltBackend(Backend):
    label = "seatbelt"

    def __init__(self, project: Path):
        self.project = project

    def wrap(self, command: str) -> list[str]:
        profile = Path(tempfile.gettempdir()) / "nightfall.sb"
        profile.write_text(
            "(version 1)\n"
            "(deny default)\n"
            "(allow process-exec process-fork signal)\n"
            "(allow file-read*)\n"
            "(allow sysctl-read)\n"
            "(deny network*)\n"
            f'(allow file-write* (subpath "{self.project}") '
            '(literal "/dev/null"))\n'
            f'(deny file-write* (subpath "{self.project / ".git"}"))\n'
        )
        return ["sandbox-exec", "-f", str(profile), "/bin/sh", "-c", command]

    def run(self, command: str, timeout: int = 60) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.wrap(command), capture_output=True, text=True, timeout=timeout
        )


class BubblewrapBackend(Backend):
    label = "bubblewrap"

    def __init__(self, project: Path):
        self.project = project

    def wrap(self, command: str) -> list[str]:
        return [
            "bwrap", "--ro-bind", "/", "/", "--bind", str(self.project), str(self.project),
            "--dev", "/dev", "--proc", "/proc", "--unshare-net", "--die-with-parent",
            "/bin/sh", "-c", command,
        ]

    def run(self, command: str, timeout: int = 60) -> subprocess.CompletedProcess:
        return subprocess.run(
            self.wrap(command), capture_output=True, text=True, timeout=timeout
        )


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [("value", ctypes.c_ulonglong) for _ in range(6)]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class WindowsBackend(Backend):
    """Native Windows process containment using Job Objects."""

    label = "windows-appcontainer"
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_NO_WINDOW = 0x08000000

    def __init__(self, project: Path):
        if sys.platform != "win32":
            raise SandboxUnavailable("Windows sandbox requested on a non-Windows host")
        self.project = project
        try:
            self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            self._configure_api()
        except (AttributeError, OSError) as error:
            raise SandboxUnavailable(
                "Windows native sandbox APIs are unavailable; use a supported Windows runtime."
            ) from error

    def _configure_api(self):
        self.kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        self.kernel32.SetInformationJobObject.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32
        ]
        self.kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.kernel32.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        self.kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    def wrap(self, command: str) -> list[str]:
        return ["cmd.exe", "/d", "/s", "/c", command]

    def _job(self):
        handle = self.kernel32.CreateJobObjectW(None, None)
        if not handle:
            raise SandboxUnavailable(f"CreateJobObjectW failed: {ctypes.get_last_error()}")
        limits = _ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = self.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel32.SetInformationJobObject(
            handle, self.JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            self.kernel32.CloseHandle(handle)
            raise SandboxUnavailable(
                f"SetInformationJobObject failed: {ctypes.get_last_error()}"
            )
        return handle

    def run(self, command: str, timeout: int = 60) -> subprocess.CompletedProcess:
        job = self._job()
        argv = self.wrap(command)
        try:
            process = subprocess.Popen(
                argv, cwd=str(self.project), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, creationflags=self.CREATE_NEW_PROCESS_GROUP | self.CREATE_NO_WINDOW,
            )
            if not self.kernel32.AssignProcessToJobObject(job, ctypes.c_void_p(process._handle)):
                process.kill()
                raise SandboxUnavailable(
                    f"AssignProcessToJobObject failed: {ctypes.get_last_error()}"
                )
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.kernel32.TerminateJobObject(job, 1)
                stdout, stderr = process.communicate()
                raise subprocess.TimeoutExpired(timeout, argv, stdout, stderr)
            return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
        finally:
            self.kernel32.CloseHandle(job)


class UnavailableBackend(Backend):
    label = "unavailable"

    def run(self, command: str, timeout: int = 60) -> subprocess.CompletedProcess:
        raise SandboxUnavailable(
            "No supported OS sandbox is available. Install Bubblewrap on Linux "
            "or use a supported macOS/Windows runtime."
        )


def _select_backend() -> Backend:
    if sys.platform == "darwin":
        return SeatbeltBackend(PROJECT)
    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        return BubblewrapBackend(PROJECT)
    if sys.platform == "win32":
        return WindowsBackend(PROJECT)
    return UnavailableBackend()


BACKEND = _select_backend()


def name() -> str:
    return BACKEND.name()


def wrap(command: str):
    wrapper = getattr(BACKEND, "wrap", None)
    return wrapper(command) if wrapper else None


def run(command: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return BACKEND.run(command, timeout)
