#!/usr/bin/env python3
"""Build a frontal, circular Corpus Clock dial texture from the photo master.

The source photograph sees the dial as a tall ellipse.  This script samples a
calibrated ellipse into a square, masks everything outside the fixed face and
keeps the outer escapement teeth out of the bitmap.  The browser therefore
remains responsible for the moving 60-tooth wheel and all LED states.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


OUTPUT_SIZE = 1024
# Calibrated against Chronophage_pol.jpg (1027 x 1600).  The ellipse ends just
# outside the outer fixed aperture row and before the moving escapement teeth.
DIAL_CENTER = (500.0, 789.0)
DIAL_RADII = (270.0, 329.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source = cv2.imread(str(args.source), cv2.IMREAD_COLOR)
    if source is None:
        raise FileNotFoundError(args.source)

    axis = np.linspace(-1.0, 1.0, OUTPUT_SIZE, dtype=np.float32)
    normalized_x, normalized_y = np.meshgrid(axis, axis)
    map_x = DIAL_CENTER[0] + normalized_x * DIAL_RADII[0]
    map_y = DIAL_CENTER[1] + normalized_y * DIAL_RADII[1]
    rectified = cv2.remap(
        source,
        map_x,
        map_y,
        interpolation=cv2.INTER_LANCZOS4,
        borderMode=cv2.BORDER_REFLECT_101,
    )

    # The reference happened to be photographed while a few blue apertures
    # were lit.  They belong to the moving shutter/LED layer, not to the fixed
    # gold face, so remove them before the browser renders the live positions.
    hsv = cv2.cvtColor(rectified, cv2.COLOR_BGR2HSV)
    blue_light = (
        (hsv[:, :, 0] >= 84)
        & (hsv[:, :, 0] <= 142)
        & (hsv[:, :, 1] >= 72)
        & (hsv[:, :, 2] >= 48)
    ).astype(np.uint8) * 255
    blue_light = cv2.dilate(blue_light, np.ones((5, 5), np.uint8), iterations=1)
    rectified = cv2.inpaint(rectified, blue_light, 5, cv2.INPAINT_TELEA)

    # Preserve the photographed metal but restore some relief lost through the
    # museum glass.  A restrained local-contrast blend avoids a processed HDR
    # look at the final 160 px display size.
    lab = cv2.cvtColor(rectified, cv2.COLOR_BGR2LAB)
    luminance, channel_a, channel_b = cv2.split(lab)
    enhanced = cv2.createCLAHE(clipLimit=1.35, tileGridSize=(10, 10)).apply(luminance)
    luminance = cv2.addWeighted(luminance, 0.72, enhanced, 0.28, 0)
    rectified = cv2.cvtColor(
        cv2.cvtColor(
            cv2.merge((luminance, channel_a, channel_b)),
            cv2.COLOR_LAB2BGR,
        ),
        cv2.COLOR_BGR2BGRA,
    )

    radius = np.sqrt(normalized_x**2 + normalized_y**2)
    # The extreme photographed edge contains the surrounding glass and a few
    # perspective errors.  Fade it before the browser's vector outer rim so
    # only genuine face metal contributes to the runtime texture.
    alpha = np.clip((0.93 - radius) / 0.08, 0.0, 1.0)
    rectified[:, :, 3] = np.rint(alpha * 255).astype(np.uint8)
    rectified[rectified[:, :, 3] == 0, :3] = 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    rgba = cv2.cvtColor(rectified, cv2.COLOR_BGRA2RGBA)
    Image.fromarray(rgba, "RGBA").save(
        args.output,
        "WEBP",
        lossless=True,
        quality=100,
        method=6,
    )


if __name__ == "__main__":
    main()
