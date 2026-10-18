"""Opt-in offline comparison. Does not change the running app or its settings.

Use a separate environment with onnxruntime-directml, numpy and Pillow.
Album-cover inputs/results should stay outside the source/release archives.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np
import onnxruntime as ort
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--input', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--provider', choices=['DmlExecutionProvider', 'CPUExecutionProvider'],
                        default='DmlExecutionProvider')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.provider not in ort.get_available_providers():
        raise RuntimeError(f'Requested provider unavailable: {args.provider}')
    options = ort.SessionOptions()
    options.enable_mem_pattern = False
    options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    started = time.perf_counter()
    session = ort.InferenceSession(str(args.model), sess_options=options,
        providers=[args.provider] if args.provider == 'CPUExecutionProvider'
        else [args.provider, 'CPUExecutionProvider'])
    session.disable_fallback()
    load_seconds = time.perf_counter() - started
    print(f'Model session initialized in {load_seconds:.3f}s', flush=True)
    report = {'model': args.model.name,
        'model_sha256': hashlib.sha256(args.model.read_bytes()).hexdigest(),
        'onnxruntime': ort.__version__, 'providers': session.get_providers(),
        'session_load_seconds': round(load_seconds, 4),
        'preprocessing': 'RGB float32 [0,1]; reflect-pad bottom/right to multiple of 32; crop 4x output',
        'cases': []}
    native = ROOT / 'vendor' / 'realesrgan'
    for index, source in enumerate(args.input):
        case_dir = args.output / f'case-{index + 1}'
        case_dir.mkdir(exist_ok=True)
        with Image.open(source) as opened:
            image = opened.convert('RGB')
        w, h = image.size
        if w * h > 512 * 512:
            raise ValueError('This trial is intended for thumbnail-size inputs.')
        image.save(case_dir / 'source.png')
        image.resize((w * 4, h * 4), Image.Resampling.NEAREST).save(case_dir / 'original-4x.png')
        started = time.perf_counter()
        with (case_dir / 'realesrgan.log').open('w', encoding='utf-8') as log:
            subprocess.run([str(native / 'realesrgan-ncnn-vulkan.exe'),
                '-i', str(case_dir / 'source.png'), '-o', str(case_dir / 'realesrgan.png'),
                '-m', str(native / 'models'), '-n', 'realesrgan-x4plus',
                '-s', '4', '-t', '128', '-j', '1:1:1', '-f', 'png'],
                check=True, timeout=120, stdout=log, stderr=log,
                creationflags=0x08000000)
        baseline_seconds = time.perf_counter() - started
        array = np.asarray(image, dtype=np.float32) / 255.0
        array = np.pad(array, ((0, (-h) % 32), (0, (-w) % 32), (0, 0)), mode='reflect')
        tensor = np.ascontiguousarray(array.transpose(2, 0, 1)[None])
        times = []
        for repeat in range(2):
            started = time.perf_counter()
            output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
            times.append(time.perf_counter() - started)
            if output.shape != (1, 3, tensor.shape[2] * 4, tensor.shape[3] * 4):
                raise ValueError(f'Unexpected model output shape: {output.shape}')
            if not np.isfinite(output).all():
                raise ValueError('Non-finite model output')
            print(f'Case {index+1}, Nomos run {repeat+1}: {times[-1]:.3f}s', flush=True)
        result = np.rint(np.clip(output[0, :, :h * 4, :w * 4], 0, 1) * 255).astype(np.uint8)
        Image.fromarray(result.transpose(1, 2, 0)).save(case_dir / 'nomos.png')
        case = {'name': source.stem, 'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'input': [w, h], 'output': [w * 4, h * 4],
            'realesrgan_child_seconds': round(baseline_seconds, 4),
            'nomos_first_run_seconds': round(times[0], 4),
            'nomos_repeat_run_seconds': round(times[1], 4),
            'nomos_session_plus_first_run_seconds': round(load_seconds + times[0], 4)}
        report['cases'].append(case)
        (args.output / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(case), flush=True)


if __name__ == '__main__':
    main()
