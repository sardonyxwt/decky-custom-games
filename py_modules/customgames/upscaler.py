"""AI upscaling on the GPU with upscayl-bin (Real-ESRGAN, ncnn + Vulkan; works on AMD, Intel and NVIDIA).

One binary does the whole job: AI x4, resize to the exact size Steam wants, encode JPEG/PNG.
Downloaded once into the plugin's runtime folder, every file pinned by SHA-256.
"""

import os
import subprocess
import tempfile
import zipfile
from typing import Optional

from . import images, net

BIN_URL = "https://github.com/upscayl/upscayl-ncnn/releases/download/20251207-174704/upscayl-bin-20251207-174704-linux.zip"
BIN_SHA256 = "a9fab3c770b62f2b7a35d8d6d61eb4e8b3aef79128b665c919d080b85a2292f2"
MODEL_BASE = "https://raw.githubusercontent.com/upscayl/upscayl/e1aeaf1217b6061b4212b87c9fd421984f73e437/resources/models/"
MODELS = {
    # Real-ESRGAN x4plus as shipped by Upscayl: photos, renders, most game art
    "upscayl-standard-4x": {
        "param": "35330ececcea33b6c397a72548e788d5d53becee4734c50b7fada36e89f10a86",
        "bin": "713ee713b0353afaa27976f0563a64a5043bd70b9bd8936c2e26e25ebcdbcddf",
    },
    # flat illustration, pixel art, anime-style covers
    "digital-art-4x": {
        "param": "2b8fb6e0ae4d2d85704ca08c119a2f5ea40add4f2ecd512eb7f4cd44b6127ed4",
        "bin": "fe01c269cfd10cdef8e018ab66ebe750cf79c7af4d1f9c16c737e1295229bacc",
    },
}
DEFAULT_MODEL = "upscayl-standard-4x"


class UpscaleError(Exception):
    pass


def clean_env() -> dict:
    # Decky runs from a PyInstaller bundle; its LD_LIBRARY_PATH breaks system libraries such as the Vulkan loader.
    env = dict(os.environ)
    for k in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH"):
        orig = env.pop(k + "_ORIG", None)
        env.pop(k, None)
        if orig:
            env[k] = orig
    return env


class Upscaler:
    def __init__(self, runtime_dir: str):
        self.dir = os.path.join(runtime_dir, "upscayl")
        self.exe = os.path.join(self.dir, "upscayl-bin")
        self.models = os.path.join(self.dir, "models")

    def installed(self) -> bool:
        return os.path.isfile(self.exe) and all(
            os.path.isfile(os.path.join(self.models, f"{m}.{ext}")) for m in MODELS for ext in ("param", "bin"))

    def install(self) -> None:
        os.makedirs(self.models, exist_ok=True)
        if not os.path.isfile(self.exe):
            with tempfile.TemporaryDirectory(dir=self.dir) as tmp:
                z = net.download(BIN_URL, os.path.join(tmp, "u.zip"), timeout=300)
                if images.sha256(z) != BIN_SHA256:
                    raise UpscaleError("upscayl-bin: checksum mismatch, not installed")
                with zipfile.ZipFile(z) as zf:
                    name = next(n for n in zf.namelist() if n.endswith("/upscayl-bin"))
                    with zf.open(name) as src, open(self.exe + ".part", "wb") as dst:
                        dst.write(src.read())
                os.chmod(self.exe + ".part", 0o755)
                os.replace(self.exe + ".part", self.exe)
        for model, sums in MODELS.items():
            for ext, want in sums.items():
                dest = os.path.join(self.models, f"{model}.{ext}")
                if os.path.isfile(dest) and images.sha256(dest) == want:
                    continue
                net.download(MODEL_BASE + f"{model}.{ext}", dest + ".dl", timeout=600)
                if images.sha256(dest + ".dl") != want:
                    os.remove(dest + ".dl")
                    raise UpscaleError(f"{model}.{ext}: checksum mismatch, not installed")
                os.replace(dest + ".dl", dest)

    def run(self, src: str, dest: str, width: int, height: Optional[int] = None, fmt: str = "jpg",
            quality: int = 90, model: str = DEFAULT_MODEL, timeout: int = 900) -> str:
        """AI x4 of src, then resized to width x height (or width only, keeping the shape), saved as fmt."""
        if not self.installed():
            raise UpscaleError("upscaler is not installed")
        size = f"{width}x{height}" if height else None
        # No "-s": with an output scale upscayl-bin ignores -r/-w and saves the plain x4 result.
        cmd = [self.exe, "-i", src, "-o", dest, "-m", self.models, "-n", model, "-z", "4", "-f", fmt]
        cmd += ["-r", size] if size else ["-w", str(width)]
        if fmt == "jpg":
            cmd += ["-c", str(100 - quality)]  # upscayl's "compression" is 100 - JPEG quality
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=clean_env(),
                               cwd=self.dir)
        except subprocess.TimeoutExpired as e:
            raise UpscaleError("upscale timed out") from e
        if r.returncode != 0 or not os.path.isfile(dest) or os.path.getsize(dest) < 1000:
            raise UpscaleError(f"upscayl-bin exit {r.returncode}: {(r.stderr or r.stdout)[-400:]}")
        return dest
