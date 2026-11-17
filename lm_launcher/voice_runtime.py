"""Runtime recipes shared by the managed voice service and its worker guardian."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KINDS = frozenset({'media', 'analyze', 'dataset', 'train', 'render', 'evaluate', 'stitch', 'extract'})
GPU_KINDS = KINDS - {'media', 'dataset', 'stitch'}
TRAINER = 'qwen-tts @ git+https://github.com/hewliyang/qwen-tts@6c674c28c0426021df2d459f2b08de1b77b0813c'


def runtime_command(kind: str, directory: Path) -> list[str]:
    if kind not in KINDS:
        raise ValueError('unknown voice job kind')
    args = ['uv', 'run', '--no-project', '--python', '3.12' if kind == 'train' else '3.13']
    if kind == 'stitch':
        args += ['--with', 'imageio-ffmpeg==0.6.0']
    elif kind != 'dataset':
        args += ['--with', 'mlx-audio==0.3.1' if kind == 'train' else 'mlx-audio==0.6.6',
                 '--with', 'imageio-ffmpeg==0.6.0', '--with', 'soundfile==0.13.1']
    if kind in {'analyze', 'evaluate', 'extract'}:
        args += ['--with', 'mlx-whisper==0.4.3']
    if kind in {'media', 'extract'}:
        args += ['--with', 'yt-dlp[default]==2026.10.26']
    if kind == 'train':
        args += ['--prerelease', 'allow', '--with', TRAINER, '--with', 'mlx-lm==0.30.5']
    return args + ['python', '-u', '-m', 'lm_launcher.voice_workbench', '--job', str(directory)]
