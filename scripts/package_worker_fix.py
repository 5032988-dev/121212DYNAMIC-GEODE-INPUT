"""CodeRabbit-generated: rebuild the supplied bundle with the Python fixes and configurable CPU isolation.

Does not compile or certify either native DLL. Original artifacts remain byte-identical.
"""
import argparse
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def package(output):
    original = ROOT / 'InputAlignExternal-windows.zip'
    source_archive = ROOT / 'InputAlignExternal-v0.3-source.zip'
    for input_archive in (original, source_archive):
        require(output.resolve() != input_archive.resolve()
                and not (output.exists() and output.samefile(input_archive)),
                'Output must not overwrite an original archive')
    with zipfile.ZipFile(original) as outer:
        require(outer.testzip() is None, 'Invalid outer ZIP CRC')
        with zipfile.ZipFile(io.BytesIO(outer.read('InputAlignExternal-windows.zip'))) as source:
            require(source.testzip() is None, 'Invalid inner ZIP CRC')
            files = {name: source.read(name) for name in source.namelist()}
            require(len(files) == len(source.namelist()), 'Duplicate ZIP entries')
    provenance = json.loads(files['build-provenance.json'])
    require(set(provenance['sha256']) == set(files) - {'build-provenance.json'}, 'Incomplete manifest')
    for name, expected in provenance['sha256'].items():
        require(sha(files[name]) == expected, f'Original hash mismatch: {name}')
    replacements = {
        'InputAlignWorker/main.py': ROOT / 'InputAlignExternal/worker/main.py',
        'InputAlignWorker/predictor.py': ROOT / 'InputAlignExternal/worker/predictor.py',
        'InputAlignWorker/cpu_isolation.py': ROOT / 'InputAlignExternal/worker/cpu_isolation.py',
        'InputAlignWorker/cpu-isolation.json': ROOT / 'InputAlignExternal/worker/cpu-isolation.json',
        'InputAlignWorker/obstacles.py': ROOT / 'InputAlignExternal/worker/obstacles.py',
        'InputAlignWorker/obstacle-sensor.json': ROOT / 'InputAlignExternal/worker/obstacle-sensor.json',
        'GUIA-INSTALACION.md': ROOT / 'InputAlignExternal/GUIA-INSTALACION.md',
        'README.md': ROOT / 'InputAlignExternal/README.md',
    }
    before = {name: sha(files[name]) if name in files else None for name in replacements}
    for name, path in replacements.items():
        files[name] = path.read_bytes()
        provenance['sha256'][name] = sha(files[name])
    provenance['workerPatch'] = {
        'generatedBy': 'CodeRabbit Coding Agent',
        'id': 'restart-status-recovery-7',
        'originalArchiveSha256': sha(original.read_bytes()),
        'originalFileSha256': before,
        'changes': ['Reject the attempt after initialization or replay errors; keep the worker running.',
                    'Discard older attempts and prefer the newer input epoch for packets at the same tick.',
                    'Reuse one exact successful prediction after fresh state validation; retry incomplete searches.',
                    'Reject Stop/Pause/Resume levels before constructing an unverified model.',
                    'Optionally reserve one physical CPU core for the worker, verify masks and restore on normal exit; GPU unchanged.',
                    'Report nearby modeled hitboxes; optionally suppress out-of-range searches without reducing verification horizon.',
                    'Order bounded telemetry batches before replay; recover observed history from reordered UDP packets.',
                    'Send fresh status for each attempt without waiting for the periodic status interval.'],
        'nativeBinariesRebuilt': False,
        'validation': 'Python regression tests on Linux; Windows and gameplay not tested.',
        'sourceArchive': 'InputAlignExternal-v0.3-source.zip',
        'sourceArchiveSha256': sha(source_archive.read_bytes()),
    }
    files['build-provenance.json'] = (json.dumps(provenance, indent=2) + '\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=output.name + '.', suffix='.tmp', dir=output.parent)
    os.close(fd)
    temporary = Path(name)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as dest:
            for name, data in files.items():
                dest.writestr(name, data)
        with zipfile.ZipFile(temporary) as result:
            require(result.testzip() is None, 'Invalid output ZIP CRC')
            for name, expected in provenance['sha256'].items():
                require(sha(result.read(name)) == expected, f'Output hash mismatch: {name}')
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'Validated {len(files)} entries; replaced {list(replacements)} and build-provenance.json')
    print(f'SHA256 {sha(output.read_bytes())}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    package(parser.parse_args().output.resolve())
