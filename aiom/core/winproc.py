"""Find and stop Minecraft server JVMs left behind by earlier runs.

Why this module exists
----------------------
Paper starts through paperclip: the process we spawn unpacks the real server
and launches it as a *child* JVM. Terminating the parent leaves the child
holding `paper.jar`, `libraries/` and, worst of all, the world lock. The next
benchmark run then fails with `DirectoryLock.create` or "Device or resource
busy", neither of which points at a surviving process.

Two dead ends are recorded here so they are not retried:

* `proc.terminate()` — kills only the parent; the paperclip child survives.
* `taskkill /T` — needs the parent to still exist. Once it has exited, its pid
  no longer identifies the tree.
* `wmic process ... get CommandLine` — `wmic` has been removed from recent
  Windows builds, so the sweep silently reported "killed 0" every time. A
  cleanup helper that reports success while doing nothing is worse than none.

What is left is the Win32 toolhelp API, which needs no subprocess at all, and a
command-line read from PEB for the match. Pure ctypes, no shell, no quoting.
"""
from __future__ import annotations

import ctypes
import os
import struct
from ctypes import wintypes

if os.name != "nt":  # pragma: no cover - the module is a no-op elsewhere
    raise ImportError("winproc is Windows-only")

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll", use_last_error=True)


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE,
                                     ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.argtypes = [wintypes.HANDLE,
                                    ctypes.POINTER(PROCESSENTRY32W)]
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD)]
kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]


def _process_path(pid: int) -> str:
    """Full image path of a process, or '' when it cannot be read."""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf,
                                              ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(h)


def _command_line(pid: int) -> str:
    """Read another process's command line out of its PEB.

    Windows exposes no API for this; the documented-ish route is to open the
    process, walk to its PEB, and follow RTL_USER_PROCESS_PARAMETERS. It is
    the only allocation-free way that does not need a helper process.
    """
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""

    class PROCESS_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("ExitStatus", ctypes.c_void_p),
            ("PebBaseAddress", ctypes.c_void_p),
            ("AffinityMask", ctypes.c_void_p),
            ("BasePriority", ctypes.c_void_p),
            ("UniqueProcessId", ctypes.c_void_p),
            ("InheritedFromUniqueProcessId", ctypes.c_void_p),
        ]

    # The first call is a size probe; ignore its result and only trust the
    # second, which actually fills the struct.
    pbi = PROCESS_BASIC_INFORMATION()
    ntdll.NtQueryInformationProcess.restype = ctypes.c_long
    ntdll.NtQueryInformationProcess.argtypes = [
        wintypes.HANDLE, ctypes.c_ulong, ctypes.c_void_p, wintypes.ULONG,
        ctypes.POINTER(wintypes.ULONG),
    ]
    status = ntdll.NtQueryInformationProcess(
        wintypes.HANDLE(h), 0, ctypes.byref(pbi),
        ctypes.sizeof(PROCESS_BASIC_INFORMATION), None)
    kernel32.CloseHandle(h)
    if status != 0 or not pbi.PebBaseAddress:
        return ""

    # PEB -> ProcessParameters -> CommandLine (UNICODE_STRING: len, max, buf)
    peb = int(pbi.PebBaseAddress)
    kernel32.ReadProcessMemory.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t)]

    def _read(addr: int, size: int) -> bytearray | None:
        buf = (ctypes.c_ubyte * size)()
        got = ctypes.c_size_t(0)
        hh = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION |
                                  PROCESS_VM_READ, False, pid)
        if not hh:
            return None
        try:
            if not kernel32.ReadProcessMemory(
                    wintypes.HANDLE(hh), ctypes.c_void_p(addr), buf, size,
                    ctypes.byref(got)):
                return None
        finally:
            kernel32.CloseHandle(hh)
        return bytearray(buf)

    # PEB.ProcessParameters sits at +0x20 on 64-bit, +0x10 on 32-bit.
    off = 0x20 if ctypes.sizeof(ctypes.c_void_p) == 8 else 0x10
    pp = _read(peb + off, ctypes.sizeof(ctypes.c_void_p))
    if not pp:
        return ""
    params = int.from_bytes(bytes(pp), "little")
    if not params:
        return ""

    # RTL_USER_PROCESS_PARAMETERS.CommandLine is at +0x70 (64-bit) / +0x40.
    cmd_off = 0x70 if ctypes.sizeof(ctypes.c_void_p) == 8 else 0x40
    head = _read(params + cmd_off, 16)
    if not head or len(head) < 16:
        return ""
    length = int.from_bytes(bytes(head[0:2]), "little")
    buf_addr = int.from_bytes(bytes(head[8:16]), "little")
    if not length or length > 65535 or not buf_addr:
        return ""
    raw = _read(buf_addr, length)
    if not raw:
        return ""
    return bytes(raw).decode("utf-16-le", errors="replace").rstrip("\x00")


def java_pids() -> list[int]:
    """All running java.exe process ids."""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == wintypes.HANDLE(-1).value:
        return []
    out: list[int] = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            while True:
                if entry.szExeFile.lower() == "java.exe":
                    out.append(int(entry.th32ProcessID))
                if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                    break
    finally:
        kernel32.CloseHandle(snap)
    return out


def terminate(pid: int) -> bool:
    h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if not h:
        return False
    try:
        return bool(kernel32.TerminateProcess(h, 1))
    finally:
        kernel32.CloseHandle(h)


def kill_servers_under(marker: str) -> list[int]:
    """Terminate every java.exe whose command line contains `marker`.

    Matching on the instance path is what makes this safe to run: a developer
    with three unrelated Java services running keeps all three.
    """
    marker = marker.lower()
    killed: list[int] = []
    self_pid = os.getpid()
    for pid in java_pids():
        if pid == self_pid:
            continue
        try:
            cmd = _command_line(pid).lower()
        except OSError:
            cmd = ""
        if not cmd:
            # No command line: fall back to the image path, which for a
            # workspace run still does not contain the marker, so skip it
            # rather than risk killing unrelated work.
            continue
        if marker in cmd:
            if terminate(pid):
                killed.append(pid)
    return killed
