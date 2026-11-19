"""CodeRabbit-generated: reversible Windows CPU affinity, without GPU changes.

Only x64 and a single processor group are supported. A forced process kill cannot
restore GD's original affinity; restart GD after killing or crashing the worker.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import ctypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import struct
import sys
import threading


@dataclass(frozen=True)
class Core:
    mask: int
    efficiency: int = 0


def parse_cores(data: bytes) -> list[Core]:
    """Decode SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX/RelationProcessorCore x64."""
    cores = []
    offset = seen = 0
    while offset < len(data):
        if len(data) - offset < 8:
            raise ValueError('Topologia truncada')
        relationship, size = struct.unpack_from('<II', data, offset)
        if size < 48 or offset + size > len(data) or relationship != 0:
            raise ValueError('Topologia no compatible')
        count = struct.unpack_from('<H', data, offset + 30)[0]
        mask, group = struct.unpack_from('<QH', data, offset + 32)
        if count != 1 or group != 0 or not mask or mask & seen:
            raise ValueError('Grupos de CPU no compatibles')
        seen |= mask
        cores.append(Core(mask, data[offset + 9]))
        offset += size
    if not cores:
        raise ValueError('No se encontraron nucleos fisicos')
    return sorted(cores, key=lambda core: core.mask)


def choose_masks(cores: list[Core], game: int, worker: int,
                 index: int | None) -> tuple[int, int]:
    """Reserve a full physical core without expanding either original affinity."""
    if sum(c.mask & game == c.mask for c in cores) < 4:
        raise ValueError('Se requieren al menos 4 nucleos fisicos completos disponibles para GD')
    if index is None:
        if len({c.efficiency for c in cores}) > 1:
            raise ValueError('CPU hibrida: selecciona worker_core explicitamente')
        candidates = [c for c in cores if c.mask & (game & worker) == c.mask]
        if not candidates:
            raise ValueError('No hay un nucleo fisico completo disponible')
        reserved = candidates[-1].mask
    else:
        if type(index) is not int or not 0 <= index < len(cores):
            raise ValueError('worker_core invalido')
        reserved = cores[index].mask
        if reserved & (game & worker) != reserved:
            raise ValueError('El nucleo elegido no esta disponible completo')
    return game & ~reserved, reserved


class AffinityLease:
    """Restore masks only while they still equal the masks applied by this lease."""
    def __init__(self, api, game: int, worker: int):
        self.api = api
        self.targets = {api.worker: worker, api.game: game}
        self.original = {h: api.affinity(h) for h in self.targets}
        if any(not mask or mask & self.original[h] != mask for h, mask in self.targets.items()):
            raise ValueError('La afinidad cambio o la mascara ampliaria los nucleos disponibles')
        self.applied = []
        self.lock = threading.RLock()

    def apply(self) -> None:
        with self.lock:
            try:
                for handle, mask in self.targets.items():
                    if self.api.affinity(handle) != self.original[handle]:
                        raise OSError('La afinidad fue modificada por otro controlador')
                    # Register before the native call: Ctrl+C may arrive just after
                    # Windows changes the mask but before Python resumes.
                    self.applied.append(handle)
                    self.api.set_affinity(handle, mask)
                    if self.api.affinity(handle) != mask:
                        raise OSError('Afinidad no confirmada')
            except (OSError, ValueError):
                self.close()
                raise

    def close(self) -> None:
        with self.lock:
            for handle in reversed(self.applied):
                try:
                    if self.api.affinity(handle) == self.targets[handle]:
                        self.api.set_affinity(handle, self.original[handle])
                except (OSError, ValueError) as error:
                    print(f'CPU: no se pudo restaurar afinidad: {error}', file=sys.stderr, flush=True)
            self.applied.clear()


class WindowsCPU:
    """Typed Win32 adapter. One controller per GD PID, no memory inspection."""
    # Preserve callback lifetime even if Windows refuses to unregister it.
    _retained_handlers = []

    def __init__(self, pid: int):
        from ctypes import wintypes as w
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            raise ValueError('Se requiere Windows x64')
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.game = self.mutex = self.handler = None
        signatures = {
            'GetCurrentProcess': ([], w.HANDLE),
            'GetActiveProcessorGroupCount': ([], w.WORD),
            'OpenProcess': ([w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
            'CloseHandle': ([w.HANDLE], w.BOOL),
            'QueryFullProcessImageNameW': ([w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)], w.BOOL),
            'GetProcessAffinityMask': ([w.HANDLE, ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)], w.BOOL),
            'SetProcessAffinityMask': ([w.HANDLE, ctypes.c_size_t], w.BOOL),
            'GetLogicalProcessorInformationEx': ([ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(w.DWORD)], w.BOOL),
            'CreateMutexW': ([ctypes.c_void_p, w.BOOL, w.LPCWSTR], w.HANDLE),
            'SetConsoleCtrlHandler': ([ctypes.c_void_p, w.BOOL], w.BOOL),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(self.k, name)
            fn.argtypes, fn.restype = args, result
        self.worker = self.k.GetCurrentProcess()
        try:
            if self.k.GetActiveProcessorGroupCount() != 1:
                raise ValueError('Mas de un grupo de procesadores: aislamiento desactivado')
            self.game = self.k.OpenProcess(0x1000 | 0x0200, False, pid)
            if not self.game:
                raise ctypes.WinError(ctypes.get_last_error())
            name = ctypes.create_unicode_buffer(32768)
            length = w.DWORD(len(name))
            if not self.k.QueryFullProcessImageNameW(self.game, 0, name, ctypes.byref(length)):
                raise ctypes.WinError(ctypes.get_last_error())
            if Path(name.value).name.casefold() != 'geometrydash.exe':
                raise ValueError('El proceso no es GeometryDash.exe; usa game_pid si abres el worker manualmente')
            ctypes.set_last_error(0)
            self.mutex = self.k.CreateMutexW(None, False, f'Local\\InputAlignCpuIsolation-{pid}')
            error = ctypes.get_last_error()
            if not self.mutex:
                raise ctypes.WinError(error)
            if error == 183:
                raise ValueError('Otra consola ya gestiona la afinidad de este GD')
        except (OSError, ValueError):
            self.close()
            raise

    def cores(self) -> list[Core]:
        from ctypes import wintypes as w
        length = w.DWORD()
        self.k.GetLogicalProcessorInformationEx(0, None, ctypes.byref(length))
        if not 0 < length.value <= 1024 * 1024:
            raise OSError('No se pudo leer la topologia CPU')
        data = ctypes.create_string_buffer(length.value)
        if not self.k.GetLogicalProcessorInformationEx(0, data, ctypes.byref(length)):
            raise ctypes.WinError(ctypes.get_last_error())
        return parse_cores(data.raw[:length.value])

    def affinity(self, handle) -> int:
        mask, system = ctypes.c_size_t(), ctypes.c_size_t()
        if not self.k.GetProcessAffinityMask(handle, ctypes.byref(mask), ctypes.byref(system)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not mask.value:
            raise ValueError('Afinidad vacia o multigrupo')
        return mask.value

    def set_affinity(self, handle, mask: int) -> None:
        if not self.k.SetProcessAffinityMask(handle, mask):
            raise ctypes.WinError(ctypes.get_last_error())

    def on_close(self, cleanup) -> None:
        def handler(event):
            if event in (2, 5, 6):
                cleanup()
            return False
        self.handler = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)(handler)
        if not self.k.SetConsoleCtrlHandler(self.handler, True):
            self.handler = None
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if self.handler:
            if not self.k.SetConsoleCtrlHandler(self.handler, False):
                self._retained_handlers.append(self.handler)
            self.handler = None
        for name in ('game', 'mutex'):
            handle = getattr(self, name, None)
            if handle:
                self.k.CloseHandle(handle)
                setattr(self, name, None)


@contextmanager
def isolation(directory: Path, mode: str | None = None) -> Iterator[None]:
    """Read cpu-isolation.json once; fall back without blocking the worker."""
    api = lease = None

    def release():
        if lease:
            with lease.lock:
                lease.close()
                if api:
                    api.close()
        elif api:
            api.close()

    # Include setup in the finally: interruption during assignment must undo it.
    try:
        try:
            config_path = directory / 'cpu-isolation.json'
            config = {}
            if config_path.is_file():
                if config_path.stat().st_size > 4096:
                    raise ValueError('Configuracion CPU demasiado grande')
                config = json.loads(config_path.read_text(encoding='utf-8'))
            if not isinstance(config, dict) or set(config) - {'enabled', 'worker_core', 'game_pid'}:
                raise ValueError('Configuracion CPU desconocida')
            enabled = config.get('enabled', True)
            index, pid = config.get('worker_core'), config.get('game_pid')
            if type(enabled) is not bool or (index is not None and (type(index) is not int or index < 0)):
                raise ValueError('enabled/worker_core invalidos')
            if pid is not None and (type(pid) is not int or not 0 < pid < 2**32):
                raise ValueError('game_pid invalido')
            if mode not in (None, 'auto', 'off'):
                raise ValueError('Modo CPU invalido')
            enabled = enabled if mode is None else mode == 'auto'
            if not enabled:
                print('CPU: aislamiento desactivado', flush=True)
            elif os.name != 'nt':
                print('CPU: aislamiento disponible solo en Windows x64', flush=True)
            else:
                api = WindowsCPU(pid or os.getppid())
                cores = api.cores()
                print('CPU: nucleos fisicos (indice, mascara, clase): ' +
                      str([(i, hex(c.mask), c.efficiency) for i, c in enumerate(cores)]), flush=True)
                game, worker = choose_masks(cores, api.affinity(api.game), api.affinity(api.worker), index)
                lease = AffinityLease(api, game, worker)
                api.on_close(lease.close)
                lease.apply()
                print(f'CPU: aislamiento activo; GD={game:#x}; simulador={worker:#x}; GPU sin cambios', flush=True)
        except (OSError, ValueError) as error:
            release()
            api = lease = None
            print(f'CPU: aislamiento no activado: {error}', file=sys.stderr, flush=True)
        yield
    finally:
        release()
