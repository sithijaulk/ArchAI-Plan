from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping

import numpy as np


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -25.0, 25.0)))


def _relu(x: np.ndarray) -> np.ndarray:
    return np.maximum(0.0, x)


def _conv2d_valid_single(image: np.ndarray, kernel: np.ndarray) -> np.ndarray:
    """Vectorized 2D cross-correlation (single in_channel to single out_channel)."""
    kh, kw = kernel.shape
    ih, iw = image.shape
    oh = ih - kh + 1
    ow = iw - kw + 1
    # Strided sliding window for fast numpy dot product
    from numpy.lib.stride_tricks import as_strided
    shape = (oh, ow, kh, kw)
    strides = (image.strides[0], image.strides[1], image.strides[0], image.strides[1])
    windows = as_strided(image, shape=shape, strides=strides)
    return np.tensordot(windows, kernel, axes=((2, 3), (0, 1)))


def _conv2d(x: np.ndarray, weight: np.ndarray, bias: np.ndarray | None = None, padding: int = 1) -> np.ndarray:
    """
    Fast 2D Convolution for small CNNs.
    x: (C_in, H, W)
    weight: (C_out, C_in, kH, kW)
    bias: (C_out,) or None
    """
    c_out, c_in, kh, kw = weight.shape
    _, h, w = x.shape

    if padding > 0:
        x_pad = np.pad(x, ((0, 0), (padding, padding), (padding, padding)), mode="constant")
    else:
        x_pad = x

    out_h = h + 2 * padding - kh + 1
    out_w = w + 2 * padding - kw + 1
    out = np.zeros((c_out, out_h, out_w), dtype=np.float32)

    for co in range(c_out):
        acc = np.zeros((out_h, out_w), dtype=np.float32)
        for ci in range(c_in):
            acc += _conv2d_valid_single(x_pad[ci], weight[co, ci])
        if bias is not None:
            acc += bias[co]
        out[co] = acc

    return out


def _maxpool2d(x: np.ndarray) -> np.ndarray:
    """2x2 Max Pooling with stride 2."""
    c, h, w = x.shape
    new_h, new_w = h // 2, w // 2
    reshaped = x[:, :new_h * 2, :new_w * 2].reshape(c, new_h, 2, new_w, 2)
    return reshaped.max(axis=(2, 4))


def _upsample2d(x: np.ndarray, factor: int = 2) -> np.ndarray:
    """Nearest-neighbor 2D upsampling."""
    return np.repeat(np.repeat(x, factor, axis=1), factor, axis=2)


class NeuralGardenLayoutModel:
    """
    NumPy-based neural layout inference engine.
    Computes 9x96x96 -> 4x96x96 heatmap prediction without PyTorch runtime dependency.
    """

    def __init__(self, weights: dict[str, np.ndarray], metadata: dict[str, Any]):
        self.weights = weights
        self.metadata = metadata
        self.version = metadata.get("model_version", "elia-garden-layout-v1.0")

        # Validate weights
        required_layers = [
            "conv1.weight", "conv1.bias",
            "conv2.weight", "conv2.bias",
            "conv3.weight", "conv3.bias",
            "conv4.weight", "conv4.bias",
            "conv5.weight", "conv5.bias",
        ]
        for name in required_layers:
            if name not in weights:
                raise ValueError(f"Missing required model weight tensor: {name}")
            if not np.all(np.isfinite(weights[name])):
                raise ValueError(f"Non-finite values detected in weight tensor: {name}")

    @classmethod
    def load_from_directory(cls, artifact_dir: str | Path) -> NeuralGardenLayoutModel:
        p = Path(artifact_dir)
        manifest_file = p / "manifest.json"
        weights_file = p / "weights.npz"

        if not manifest_file.exists():
            raise FileNotFoundError(f"Missing manifest.json in artifact directory: {p}")
        if not weights_file.exists():
            raise FileNotFoundError(f"Missing weights.npz in artifact directory: {p}")

        with open(manifest_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        # Verify checksum
        sha256 = hashlib.sha256()
        with open(weights_file, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        actual_hash = sha256.hexdigest()
        expected_hash = meta.get("weights_sha256")
        if expected_hash and actual_hash != expected_hash:
            raise ValueError(f"Weights checksum mismatch! Expected {expected_hash}, got {actual_hash}")

        # Safe load (no pickle)
        loaded = np.load(weights_file, allow_pickle=False)
        weights = {key: loaded[key] for key in loaded.files}
        return cls(weights, meta)

    def forward(self, x: np.ndarray) -> np.ndarray:
        """
        Forward pass.
        x: (9, 96, 96) float32 numpy array
        returns: (4, 96, 96) float32 heatmap array with values in [0.0, 1.0]
        """
        if x.shape != (9, 96, 96):
            raise ValueError(f"Expected input shape (9, 96, 96), got {x.shape}")
        if not np.all(np.isfinite(x)):
            raise ValueError("Input tensor contains non-finite (NaN or Inf) values")

        # Layer 1: 9 -> 16 channels (96x96 -> 48x48)
        c1 = _relu(_conv2d(x, self.weights["conv1.weight"], self.weights["conv1.bias"], padding=1))
        p1 = _maxpool2d(c1)

        # Layer 2: 16 -> 32 channels (48x48 -> 24x24)
        c2 = _relu(_conv2d(p1, self.weights["conv2.weight"], self.weights["conv2.bias"], padding=1))
        p2 = _maxpool2d(c2)

        # Layer 3 (Bottleneck): 32 -> 32 channels (24x24)
        b3 = _relu(_conv2d(p2, self.weights["conv3.weight"], self.weights["conv3.bias"], padding=1))

        # Layer 4 (Decoder 1): Up 24x24 -> 48x48, 32 -> 16 channels
        u1 = _upsample2d(b3, factor=2)
        c4 = _relu(_conv2d(u1, self.weights["conv4.weight"], self.weights["conv4.bias"], padding=1))

        # Layer 5 (OutConv): Up 48x48 -> 96x96, 16 -> 4 channels
        u2 = _upsample2d(c4, factor=2)
        c5 = _conv2d(u2, self.weights["conv5.weight"], self.weights["conv5.bias"], padding=1)

        out = _sigmoid(c5)
        if not np.all(np.isfinite(out)):
            raise ValueError("Model output contains non-finite values")
        return out.astype(np.float32)


def generate_canonical_weights() -> dict[str, np.ndarray]:
    """
    Generate initial reproducible, structured weights for the UNet model
    using fixed seed orthogonal/he initialization.
    """
    rng = np.random.default_rng(seed=42)

    def init_conv(c_out: int, c_in: int, kh: int = 3, kw: int = 3) -> tuple[np.ndarray, np.ndarray]:
        std = math.sqrt(2.0 / (c_in * kh * kw))
        w = rng.normal(0.0, std, size=(c_out, c_in, kh, kw)).astype(np.float32)
        b = np.zeros(c_out, dtype=np.float32)
        return w, b

    w1, b1 = init_conv(16, 9)
    w2, b2 = init_conv(32, 16)
    w3, b3 = init_conv(32, 32)
    w4, b4 = init_conv(16, 32)
    w5, b5 = init_conv(4, 16)

    return {
        "conv1.weight": w1, "conv1.bias": b1,
        "conv2.weight": w2, "conv2.bias": b2,
        "conv3.weight": w3, "conv3.bias": b3,
        "conv4.weight": w4, "conv4.bias": b4,
        "conv5.weight": w5, "conv5.bias": b5,
    }
