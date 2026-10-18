"""Read-only engine discovery and temporary preview controls for verification."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import winreg

NO_WINDOW = 0x08000000


class ProcessEntry(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD),
        ('pid', wintypes.DWORD), ('heap', ctypes.c_size_t),
        ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
        ('parent', wintypes.DWORD), ('priority', wintypes.LONG),
        ('flags', wintypes.DWORD), ('name', wintypes.WCHAR * 260)]


def engine_running():
    """A cheap process snapshot, avoiding accidental engine launches at login."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ProcessEntry()
        entry.size = ctypes.sizeof(entry)
        valid = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while valid:
            if entry.name.lower() in ('wallpaper64.exe', 'wallpaper32.exe'):
                return True
            valid = kernel.Process32NextW(handle, ctypes.byref(entry))
        return False
    finally:
        kernel.CloseHandle(handle)


def find_engine():
    # Prefer the live process; do not depend on where Steam is installed.
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    processes = (ctypes.c_ulong * 4096)()
    size = ctypes.c_ulong()
    psapi.EnumProcesses(processes, ctypes.sizeof(processes), ctypes.byref(size))
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    for pid in list(processes)[:size.value // ctypes.sizeof(ctypes.c_ulong)]:
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            continue
        try:
            buf = ctypes.create_unicode_buffer(32768)
            n = ctypes.c_ulong(len(buf))
            if kernel.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(n)):
                path = Path(buf.value)
                if path.name.lower() in ('wallpaper64.exe', 'wallpaper32.exe'):
                    return path.parent
        finally:
            kernel.CloseHandle(handle)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as key:
            steam = Path(winreg.QueryValueEx(key, 'SteamPath')[0])
        libraries = [steam]
        import re
        vdf = (steam / 'steamapps' / 'libraryfolders.vdf').read_text('utf-8')
        libraries += [Path(p.replace('\\\\', '\\')) for p in re.findall(r'"path"\s+"([^"]+)"', vdf)]
        for lib in libraries:
            path = lib / 'steamapps' / 'common' / 'wallpaper_engine'
            if (path / 'wallpaper64.exe').exists():
                return path
    except (OSError, ValueError):
        pass
    raise RuntimeError('未找到 Wallpaper Engine。请先启动它，或在界面中选择安装文件夹。')


def selected(engine, monitor=0):
    data = json.loads((Path(engine) / 'config.json').read_text('utf-8'))
    for value in data.values():
        if isinstance(value, dict):
            config = value.get('general', {}).get('wallpaperconfig', {})
            item = config.get('selectedwallpapers', {}).get(f'Monitor{monitor}', {})
            if item.get('file'):
                return Path(item['file'])
    return None


def command(engine, action, monitor=0, **kwargs):
    if not engine_running():
        raise RuntimeError('等待 Wallpaper Engine 启动…')
    exe = Path(engine) / 'wallpaper64.exe'
    if not exe.exists():
        exe = Path(engine) / 'wallpaper32.exe'
    args = [str(exe), '-control', action]
    if 'location' not in kwargs and 'playInWindow' not in kwargs:
        args.extend(['-monitor', str(monitor)])
    raw = kwargs.pop('properties', None)
    for key, value in kwargs.items():
        args.extend(['-' + key, str(value)])
    line = subprocess.list2cmdline(args)
    # WE reads RAW delimiters from GetCommandLineW, before normal argv parsing.
    if raw is not None:
        line += ' -properties RAW~(' + json.dumps(raw, ensure_ascii=False) + ')~END'
    subprocess.run(line, timeout=15, check=True, creationflags=NO_WINDOW)
