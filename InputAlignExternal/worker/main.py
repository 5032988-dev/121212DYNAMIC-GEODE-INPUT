"""Input Align External console worker; standard-library Python + the bundled native simulator."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys
import time

# A frozen Windows build ships the compiled simulator; end users need no compiler or Python.
bundle = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
native = bundle / ('gdsim.dll' if os.name == 'nt' else 'libgdsim.so')
if native.is_file():
    os.environ['GDGEN_SIM_LIB'] = str(native)

from diagnostics import DivergenceJournal, QueryStats
from cpu_isolation import isolation
from obstacles import read_settings as read_sensor_settings
from protocol import Header, HELLO, decode_frame, status
from predictor import Predictor, UnsupportedLevel, load_simulator


def newer_frame(predictor, frame, queued):
    if (queued[0].session, queued[0].tick, queued[0].epoch) < (frame[0].session, frame[0].tick, frame[0].epoch):
        return frame
    if (predictor is not None
            and (predictor.session is None or frame[0].session >= predictor.session)
            and (not predictor.rejected or predictor.session != frame[0].session)):
        known = predictor.tick if predictor.session == queued[0].session else 0
        if queued[0].tick - known > queued[3]:
            # Validate/replay retained history before the newer window discards it.
            try:
                predictor.synchronize(*frame[:4])
            except (ValueError, OverflowError, RuntimeError):
                # Replay may have advanced only part of the retained history.
                # Keep serving telemetry, but never forecast from that partial state.
                # synchronize resets rejection when a new attempt arrives.
                predictor.rejected = True
    return queued



def coalesce_frames(predictor, frames):
    """Replay retained prefixes in tick order, including reordered UDP packets.

    Work stays bounded to the existing 1+64 receive window. Every prefix still
    passes Predictor.synchronize; a missing interval or divergence fails closed.
    """
    if not 1 <= len(frames) <= 65:
        raise ValueError('Lote de telemetria fuera de limites')
    if len(frames) == 1:
        return frames[0]
    session = max(frame[0].session for frame in frames)
    ordered = sorted((frame for frame in frames if frame[0].session == session),
                     key=lambda frame: (frame[0].tick, frame[0].epoch))
    latest = ordered[0]
    for queued in ordered[1:]:
        latest = newer_frame(predictor, latest, queued)
    return latest


def serve(directory: Path, *, stop=None, sensor_settings=None, diagnostics=True):
    config = json.loads((directory / 'bridge.json').read_text(encoding='utf-8'))
    if config.get('version') != 1 or not 1 <= config['port'] <= 65535:
        raise ValueError('Configuracion de puente invalida')
    token = (int(config['tokenHi'], 16), int(config['tokenLo'], 16))
    endpoint = ('127.0.0.1', config['port'])
    predictor = None
    journal = DivergenceJournal(directory / "divergences.jsonl") if diagnostics else None
    statistics = QueryStats()
    stats_since = time.perf_counter()
    failure = None
    last_hello = last_status = 0.
    last_session = None
    last_message = last_display = last_status_session = None
    print('Input Align External | GD 2.2081 | No cierres esta ventana.', flush=True)
    print('Reinicia el intento si el nivel ya estaba en marcha.', flush=True)
    # Keep the game responsive under contention. This changes only this worker's priority.
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x00004000)  # BELOW_NORMAL_PRIORITY_CLASS
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(endpoint)
        sock.settimeout(.05)
        while stop is None or not stop.is_set():
            now = time.monotonic()
            if now - last_hello >= 1:
                sock.send(Header(HELLO, *token).pack())
                last_hello = now
            try:
                packet = sock.recv(2048)
            except socket.timeout:
                continue
            except ConnectionResetError:
                print('El puente se ha cerrado. Abre la consola desde el nuevo nivel.', flush=True)
                return
            try:
                frame = decode_frame(packet, token)
            except (ValueError, OverflowError):
                continue
            header = frame[0]
            if header.session != last_session:
                last_session = header.session
                if predictor is None and failure is None:
                    try:
                        path = directory / 'level.txt'
                        if path.stat().st_size > 32 * 1024 * 1024:
                            raise UnsupportedLevel('Nivel demasiado grande')
                        predictor = Predictor(load_simulator(path.read_text(encoding='utf-8')), sensor_settings=sensor_settings, diagnostics=journal)
                    except (ValueError, OSError, RuntimeError, OverflowError, AttributeError) as error:
                        failure = str(error)
                print('Intento', header.session, failure or 'simulador preparado', flush=True)
            # Coalesce queued telemetry before spending CPU on a forecast. History reconstructs skipped ticks.
            frames = [frame]
            sock.setblocking(False)
            try:
                for _ in range(64):
                    try:
                        queued = decode_frame(sock.recv(2048), token)
                        frames.append(queued)
                    except (ValueError, OverflowError):
                        continue
                    except BlockingIOError:
                        break
            finally:
                sock.settimeout(.05)
            started, cpu_started = time.perf_counter(), time.process_time()
            frame = coalesce_frames(predictor, frames)
            header = frame[0]
            result = None
            message = failure
            query_error = False
            if predictor:
                try:
                    result = predictor.forecast(*frame)
                    message = 'Conectado: prediccion externa' if frame[1][4] & 256 else 'Conectado: modo sin correccion'
                except (ValueError, OverflowError, RuntimeError) as error:
                    message = str(error)
                    query_error = True
                statistics.observe('error' if query_error else predictor.last_outcome,
                                   time.perf_counter()-started, time.process_time()-cpu_started, frame[5])
                finished = time.perf_counter()
                if finished - stats_since >= 5:
                    measured = statistics.report(finished-stats_since)
                    print(f"Consultas {measured['queries']} | propuestas {measured['proposals']} | "
                          f"deadline {measured['deadlines']} | fuera de presupuesto {measured['over_budget']} | media {measured['mean_ms']:.2f}ms | "
                          f"max {measured['max_ms']:.2f}ms | CPU consultas {measured['cpu_percent']:.1f}%", flush=True)
                    statistics, stats_since = QueryStats(), finished
            if result:
                sock.send(result)
            if header.session != last_status_session or message != last_message or now - last_status >= 1:
                display_message = message or 'Esperando'
                if predictor and not query_error and not predictor.rejected and predictor.last_obstacle is not None:
                    display_message += ' | ' + predictor.last_obstacle.label()
                if display_message != last_display:
                    print(display_message, flush=True)
                    last_display = display_message
                sock.send(status(header, 1 if failure or query_error or predictor and predictor.rejected else 0, display_message))
                last_status = now
                last_message = message
                last_status_session = header.session


def main():
    parser = argparse.ArgumentParser(description='Simulador local de Input Align External')
    parser.add_argument('--bridge', type=Path, required=True, help='Carpeta de datos del mod')
    parser.add_argument('--cpu-isolation', choices=('auto', 'off'), default=None,
                        help='Sobrescribe cpu-isolation.json: auto separa CPU; off conserva la afinidad')
    parser.add_argument('--obstacle-distance', type=float, default=None,
                        help='Distancia horizontal del sensor, 0..12000 unidades GD; no cambia el horizonte')
    parser.add_argument("--diagnostics", choices=("on", "off"), default="on",
                        help="Registro acotado de divergencias en la carpeta del mod")
    args = parser.parse_args()
    try:
        if not os.environ.get('GDGEN_SIM_LIB'):
            raise RuntimeError('Falta gdsim.dll. Copia el contenido completo de InputAlignWorker o compila con CMake.')
        try:
            sensor_settings = read_sensor_settings(bundle, args.obstacle_distance)
        except (ValueError, OSError) as error:
            sensor_settings = None
            print(f'Sensor desactivado por configuracion invalida: {error}', file=sys.stderr, flush=True)
        with isolation(bundle, args.cpu_isolation):
            serve(args.bridge.resolve(), sensor_settings=sensor_settings, diagnostics=args.diagnostics == "on")
    except (OSError, ValueError, RuntimeError) as error:
        print(f'No se pudo iniciar: {error}', file=sys.stderr, flush=True)
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
