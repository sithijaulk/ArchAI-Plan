"""
Image preprocessing for CubiCasa5K inference.

The model expects:
  - RGB float tensor in [0, 1] range
  - Normalised with ImageNet mean/std
  - Spatial dimensions divisible by 32 (due to 5 pooling layers)
"""

from typing import Tuple, Union
from pathlib import Path

import numpy as np
import torch
from PIL import Image

# ImageNet statistics (used in original CubiCasa5K training)
MEAN = [0.485, 0.456, 0.406]
STD  = [0.229, 0.224, 0.225]


def _pad_to_multiple(h: int, w: int, multiple: int = 32) -> Tuple[int, int]:
    """Return (new_h, new_w) padded up to the nearest multiple."""
    pad_h = (multiple - h % multiple) % multiple
    pad_w = (multiple - w % multiple) % multiple
    return h + pad_h, w + pad_w


def preprocess_image(
    image: Union[str, Path, np.ndarray, Image.Image],
    fixed_size: Tuple[int, int] = None,
    device: str = "cpu",
) -> Tuple[torch.Tensor, Tuple[int, int]]:
    """
    Load and preprocess a floor plan image.

    Parameters
    ----------
    image      : file path, numpy array (H×W×3, uint8), or PIL Image
    fixed_size : (H, W) to resize to; if None, pads to nearest 32-multiple
    device     : torch device string

    Returns
    -------
    tensor      : (1, 3, H, W) normalised float tensor
    orig_size   : (orig_H, orig_W) for rescaling outputs back
    """
    # --- Load ---
    if isinstance(image, (str, Path)):
        img = Image.open(image).convert("RGB")
    elif isinstance(image, np.ndarray):
        img = Image.fromarray(image.astype(np.uint8)).convert("RGB")
    elif isinstance(image, Image.Image):
        img = image.convert("RGB")
    else:
        raise TypeError(f"Unsupported image type: {type(image)}")

    orig_size = (img.height, img.width)

    # --- Downscale if image is very large (e.g., 3500px+) to ensure fast CPU inference (<10s) ---
    max_dim = 1024
    if max(img.width, img.height) > max_dim:
        scale_ratio = max_dim / float(max(img.width, img.height))
        new_w = int(round(img.width * scale_ratio))
        new_h = int(round(img.height * scale_ratio))
        img = img.resize((new_w, new_h), Image.BILINEAR)

    # --- Resize / pad ---
    if fixed_size is not None:
        img = img.resize((fixed_size[1], fixed_size[0]), Image.BILINEAR)
    else:
        new_h, new_w = _pad_to_multiple(img.height, img.width)
        if (new_h, new_w) != (img.height, img.width):
            padded = Image.new("RGB", (new_w, new_h), (255, 255, 255))
            padded.paste(img, (0, 0))
            img = padded

    # --- To tensor and normalise ---
    arr = np.array(img, dtype=np.float32) / 255.0          # H×W×3, [0,1]
    mean = np.array(MEAN, dtype=np.float32)
    std  = np.array(STD,  dtype=np.float32)
    arr  = (arr - mean) / std                               # normalise
    tensor = torch.from_numpy(arr).permute(2, 0, 1)        # 3×H×W
    tensor = tensor.unsqueeze(0).to(device)                 # 1×3×H×W

    return tensor, orig_size
