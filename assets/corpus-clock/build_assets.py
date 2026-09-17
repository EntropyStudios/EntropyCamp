#!/usr/bin/env python3
"""Build registered photographic layers for the Corpus Chronophage.

The v3 export is intended for a two-pallet inverse-kinematics rig.  Unlike the
older body/jaw pair, no escape-wheel rim or main escapement leg is baked into
the torso.  Every output layer uses the same transparent 1024 x 861 canvas, so
the browser can share one coordinate system and rotate each pallet about its
own photographed hip.

Layer colours in ``chronophage-mask-preview-v3.webp``:

* amber   -- torso
* cyan/blue/teal -- front upper/lower/pallet pad (patent item 150 / face 172)
* magenta/purple/pink -- rear upper/lower/pallet pad (item 152 / face 194)
* green   -- passive legs and wire wing
* red     -- lower jaw
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


SOURCE_SIZE = (1600, 1346)
CANVAS_SIZE = (1024, 861)

RIG_GEOMETRY = {
    "front": {
        "upper": {"start": (685, 690), "end": (503, 870)},
        "lower": {"start": (503, 870), "end": (353, 1150)},
        "pad": {"center": (353, 1162), "tangentAngleDeg": -12.0},
    },
    "rear": {
        "upper": {"start": (835, 990), "end": (1025, 55)},
        "lower": {"start": (1025, 55), "end": (1040, 1135)},
        "pad": {"center": (1040, 1145), "tangentAngleDeg": 10.0},
    },
}


# v4 treats the photographed cosmetic covers as the rigid members described
# by patent items 196 (front) and 198 (rear).  Coordinates remain in the
# 1600x1346 source frame; ``save_rig_metadata_v4`` publishes their registered
# 1024x861 equivalents for the browser.
RIG_GEOMETRY_V4 = {
    "front": {
        "pivot": (685, 690),
        "footCenter": (353, 1163),
        "contactEdge": ((331, 1168), (375, 1158)),
        "recommendedRotationDeg": (-2.2, 2.2),
    },
    "rear": {
        "pivot": (837, 987),
        "footCenter": (1045, 1158),
        "contactEdge": ((1019, 1154), (1071, 1162)),
        "recommendedRotationDeg": (-3.5, 3.5),
    },
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output_dir", type=Path)
    return parser.parse_args()


def polygon_mask(shape: tuple[int, int], points: list[tuple[int, int]]) -> np.ndarray:
    mask = np.zeros(shape, np.uint8)
    cv2.fillPoly(mask, [np.asarray(points, np.int32)], 255)
    return mask


def stroked_mask(
    shape: tuple[int, int],
    paths: list[tuple[list[tuple[int, int]], int]],
) -> np.ndarray:
    mask = np.zeros(shape, np.uint8)
    for points, width in paths:
        cv2.polylines(
            mask,
            [np.asarray(points, np.int32)],
            False,
            255,
            thickness=width,
            lineType=cv2.LINE_AA,
        )
    return mask


def creature_roi(shape: tuple[int, int]) -> np.ndarray:
    """Keep the Chronophage while excluding the skull and most clock face."""

    return polygon_mask(
        shape,
        [
            (58, 430),
            (176, 348),
            (474, 325),
            (628, 24),
            (1045, 28),
            (1210, 460),
            (1565, 670),
            (1572, 1040),
            (1450, 1288),
            (1240, 1320),
            (1018, 1190),
            (710, 1172),
            (478, 1212),
            (348, 1268),
            (160, 1238),
            (68, 950),
        ],
    )


def initial_foreground_mask(source: np.ndarray) -> np.ndarray:
    """Extract metal from the low-saturation museum-glass background."""

    height, width = source.shape[:2]
    shape = (height, width)
    roi = creature_roi(shape)
    lab = cv2.cvtColor(source, cv2.COLOR_BGR2LAB)
    hsv = cv2.cvtColor(source, cv2.COLOR_BGR2HSV)
    luminance = lab[:, :, 0]
    saturation = hsv[:, :, 1]

    mask = np.full(shape, cv2.GC_PR_BGD, np.uint8)
    mask[roi == 0] = cv2.GC_BGD

    # Dark bronze and saturated copper/gold are reliable foreground seeds.
    confident_metal = (
        (luminance < 84)
        | ((luminance < 126) & (saturation > 45))
        | ((luminance < 176) & (saturation > 92))
    ) & (roi > 0)
    confident_metal[:22, :] = False
    confident_metal[:, :66] = False
    mask[confident_metal] = cv2.GC_FGD

    # The broad grey-blue glass field is a safe probable-background cue.  It
    # remains probable rather than hard background so silver edge highlights
    # can still be recovered by GrabCut.
    glass_like = (saturation < 42) & (luminance > 82)
    mask[glass_like & (roi > 0)] = cv2.GC_PR_BGD
    mask[:12, :] = cv2.GC_BGD
    mask[-5:, :] = cv2.GC_BGD
    mask[:, :8] = cv2.GC_BGD
    mask[:, -8:] = cv2.GC_BGD

    background_model = np.zeros((1, 65), np.float64)
    foreground_model = np.zeros((1, 65), np.float64)
    cv2.grabCut(
        source,
        mask,
        None,
        background_model,
        foreground_model,
        10,
        cv2.GC_INIT_WITH_MASK,
    )

    alpha = np.where(
        (mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD),
        255,
        0,
    ).astype(np.uint8)
    alpha[roi == 0] = 0

    # Remove the remaining glass family.  The threshold deliberately keeps
    # dark, low-saturation iron while eliminating pale reflections.
    background_like = (saturation < 39) & (luminance > 90)
    alpha[background_like] = 0

    # Retain only meaningful connected metal regions.  The wing mesh is
    # connected to the body, while the coloured glass streaks are isolated.
    count, labels, stats, _ = cv2.connectedComponentsWithStats((alpha > 0).astype(np.uint8), 8)
    cleaned = np.zeros_like(alpha)
    for label in range(1, count):
        if stats[label, cv2.CC_STAT_AREA] >= 38:
            cleaned[labels == label] = 255

    cleaned = cv2.morphologyEx(
        cleaned,
        cv2.MORPH_CLOSE,
        np.ones((3, 3), np.uint8),
        iterations=1,
    )
    return cv2.GaussianBlur(cleaned, (0, 0), 0.72)


def jaw_selection(shape: tuple[int, int]) -> np.ndarray:
    return polygon_mask(
        shape,
        [
            (82, 662),
            (104, 738),
            (126, 795),
            (176, 842),
            (229, 857),
            (287, 826),
            (327, 770),
            (322, 711),
            (280, 682),
            (231, 711),
            (180, 728),
            (128, 696),
        ],
    )


def torso_selection(shape: tuple[int, int]) -> np.ndarray:
    """Tight support for the solid head, thorax, body tube and abdomen."""

    head_and_thorax = polygon_mask(
        shape,
        [
            (70, 470),
            (156, 392),
            (340, 350),
            (510, 382),
            (670, 500),
            (790, 650),
            (792, 850),
            (712, 1018),
            (566, 1074),
            (470, 1005),
            (405, 940),
            (330, 892),
            (235, 865),
            (128, 820),
            (72, 690),
        ],
    )
    body_tube = polygon_mask(
        shape,
        [
            (520, 515),
            (790, 520),
            (1030, 556),
            (1302, 586),
            (1458, 654),
            (1450, 776),
            (1284, 824),
            (1080, 842),
            (880, 900),
            (690, 892),
            (560, 790),
        ],
    )
    abdomen = polygon_mask(
        shape,
        [
            (720, 700),
            (955, 692),
            (1142, 738),
            (1298, 820),
            (1404, 1010),
            (1390, 1264),
            (1270, 1232),
            (1160, 1112),
            (1020, 984),
            (850, 930),
            (704, 875),
        ],
    )
    facial_spines = stroked_mask(
        shape,
        [
            ([(320, 500), (470, 450), (598, 470)], 34),
            ([(368, 610), (520, 570), (676, 582)], 30),
            ([(278, 430), (410, 386), (530, 420)], 24),
        ],
    )
    return np.maximum.reduce((head_and_thorax, body_tube, abdomen, facial_spines))


def front_pallet_selections(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    """Split photographed pallet 150 at its visible hip, knee and contact pad."""

    upper = stroked_mask(
        shape,
        [
            (
                [
                    (685, 690),
                    (626, 742),
                    (562, 798),
                    (503, 870),
                ],
                112,
            ),
        ],
    )
    lower = stroked_mask(
        shape,
        [
            (
                [
                    (503, 870),
                    (447, 956),
                    (397, 1055),
                    (353, 1150),
                ],
                112,
            ),
        ],
    )
    pad = np.zeros(shape, np.uint8)
    cv2.fillPoly(
        pad,
        [
            np.asarray(
                [
                    (292, 1152),
                    (341, 1125),
                    (400, 1160),
                    (426, 1219),
                    (360, 1242),
                    (302, 1215),
                ],
                np.int32,
            )
        ],
        255,
    )
    # Shared photographic joint pixels prevent pinholes when the two sprites
    # are transformed by a two-bone IK chain.
    cv2.circle(upper, (503, 870), 54, 255, lineType=cv2.LINE_AA)
    cv2.circle(lower, (503, 870), 54, 255, lineType=cv2.LINE_AA)
    cv2.circle(lower, (353, 1150), 48, 255, lineType=cv2.LINE_AA)
    cv2.circle(pad, (353, 1150), 48, 255, lineType=cv2.LINE_AA)
    return {"front-upper": upper, "front-lower": lower, "front-pallet-pad": pad}


def rear_pallet_selections(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    """Split the inverted-V casing over L-shaped rear pallet 152."""

    # Hip at the body, knee at the high point, then the long rear shank down to
    # contact face 194.  This is the two-bone reading of the FIG. 9 mechanism.
    upper = stroked_mask(
        shape,
        [
            (
                [
                    (835, 990),
                    (844, 790),
                    (864, 590),
                    (900, 374),
                    (954, 174),
                    (1025, 55),
                ],
                92,
            ),
        ],
    )
    lower = stroked_mask(
        shape,
        [
            (
                [
                    (1025, 55),
                    (1045, 178),
                    (1057, 355),
                    (1062, 548),
                    (1068, 752),
                    (1064, 956),
                    (1040, 1135),
                ],
                70,
            ),
        ],
    )
    pad = np.zeros(shape, np.uint8)
    cv2.fillPoly(
        pad,
        [
            np.asarray(
                [
                    (990, 1070),
                    (1058, 1064),
                    (1110, 1124),
                    (1092, 1182),
                    (1024, 1184),
                    (982, 1138),
                ],
                np.int32,
            )
        ],
        255,
    )
    cv2.circle(upper, (1025, 55), 46, 255, lineType=cv2.LINE_AA)
    cv2.circle(lower, (1025, 55), 46, 255, lineType=cv2.LINE_AA)
    cv2.circle(lower, (1040, 1135), 48, 255, lineType=cv2.LINE_AA)
    cv2.circle(pad, (1040, 1135), 48, 255, lineType=cv2.LINE_AA)
    return {"rear-upper": upper, "rear-lower": lower, "rear-pallet-pad": pad}


def passive_selections(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    """Non-escapement appendages: the remaining legs/spines and wire wing."""

    appendages = stroked_mask(
        shape,
        [
            ([(561, 1125), (585, 930), (640, 710), (700, 455), (824, 128)], 96),
            ([(690, 1110), (738, 878), (783, 632), (861, 342), (973, 46)], 76),
            ([(808, 1106), (839, 870), (868, 620), (920, 348), (1024, 46)], 68),
            ([(415, 1000), (476, 892), (541, 812), (606, 758)], 46),
        ],
    )

    # The delicate wing is too porous for a single centreline.  A fitted
    # polygon supplies the semantic region; the photographic foreground alpha
    # below still cuts out every opening in the wire mesh.
    wing = polygon_mask(
        shape,
        [
            # Trace the visible wire lattice itself, staying below the solid
            # horizontal body tube.  The earlier broad quadrilateral started
            # at y=642 and therefore captured opaque rectangular strips of the
            # tube as "wing" pixels.
            (812, 708),
            (930, 708),
            (1080, 725),
            (1260, 760),
            (1455, 800),
            (1570, 840),
            (1550, 1012),
            (1380, 998),
            (1200, 948),
            (1040, 890),
            (900, 824),
            (812, 775),
        ],
    )
    return {"appendages": appendages, "wing": wing}


def front_cover_v4_selection(shape: tuple[int, int]) -> np.ndarray:
    """Tight support for the single rigid front cosmetic pallet cover.

    The v3 split treated this photographed casting as two articulated bones.
    Patent item 196 is instead one rigid cover, so v4 follows the complete
    curved casting from its body pivot to its real tooth-contact shoe.
    """

    return polygon_mask(
        shape,
        [
            (704, 676), (665, 686), (625, 708), (584, 738),
            (540, 773), (500, 811), (462, 850), (427, 894),
            (398, 941), (372, 992), (351, 1043), (332, 1096),
            (317, 1141), (311, 1170), (318, 1188), (337, 1193),
            (354, 1184), (366, 1168), (366, 1148), (350, 1136),
            (355, 1104), (371, 1053), (391, 1004), (416, 955),
            (446, 911), (480, 871), (519, 834), (559, 799),
            (600, 765), (640, 736), (678, 718), (708, 711),
        ],
    )


def front_foot_v4_selection(shape: tuple[int, int]) -> np.ndarray:
    return polygon_mask(
        shape,
        [
            (306, 1120), (326, 1108), (346, 1120), (366, 1120),
            (374, 1138), (366, 1155), (366, 1172), (354, 1186),
            (333, 1192), (315, 1177), (306, 1150),
        ],
    )


def rear_cover_v4_selection(shape: tuple[int, int]) -> np.ndarray:
    """Tight support for the one-piece inverted-V rear cover (patent 198).

    Both the rising spine and descending shank belong to this same rigid
    sprite.  In particular, the high point is not a knee and the tooth-contact
    shoe is not emitted again as a separate ``lower`` or ``pad`` layer.
    """

    rising = polygon_mask(
        shape,
        [
            (786, 1005), (780, 960), (787, 870), (797, 780),
            (810, 680), (824, 580), (843, 470), (866, 360),
            (895, 250), (930, 155), (970, 82), (1010, 38),
            (1062, 16), (1075, 17), (1064, 43), (1038, 78),
            (1020, 119), (1008, 155), (986, 172), (964, 220),
            (942, 290), (922, 375), (906, 465), (892, 560),
            (881, 660), (872, 760), (866, 850), (866, 928),
            (860, 993), (846, 1020), (816, 1020),
        ],
    )
    descending = polygon_mask(
        shape,
        [
            (996, 168), (1012, 190), (1025, 240), (1032, 320),
            (1037, 420), (1040, 520), (1043, 620), (1045, 720),
            (1045, 820), (1043, 920), (1038, 1010), (1025, 1078),
            (1002, 1092), (990, 1115), (995, 1138), (1015, 1155),
            (1040, 1164), (1072, 1165), (1090, 1158), (1180, 1188),
            (1195, 1175), (1120, 1140), (1135, 1125), (1100, 1105),
            (1105, 1085), (1075, 1075), (1084, 1010), (1089, 920),
            (1089, 820), (1087, 720), (1084, 620), (1080, 520),
            (1074, 420), (1068, 320), (1061, 240), (1052, 190),
            (1033, 161), (1005, 150),
        ],
    )

    return cv2.max(rising, descending)


def rear_foot_v4_selection(shape: tuple[int, int]) -> np.ndarray:
    return polygon_mask(
        shape,
        [
            (990, 1110), (1002, 1092), (1025, 1078), (1075, 1075),
            (1105, 1085), (1100, 1105), (1135, 1125), (1120, 1140),
            (1195, 1175), (1180, 1188), (1090, 1158), (1072, 1165),
            (1040, 1164), (1015, 1155), (995, 1138),
        ],
    )


def passive_v4_selections(shape: tuple[int, int]) -> dict[str, np.ndarray]:
    """Static appendages with the rear-cover lookalike removed.

    The former third v3 centreline ran from (808,1106) to (1024,46), directly
    duplicating the rising half of the movable rear cover.  v4 intentionally
    retains only the three genuinely passive families.
    """

    appendages = stroked_mask(
        shape,
        [
            ([(561, 1125), (585, 930), (640, 710), (700, 455), (824, 128)], 96),
            ([(690, 1110), (738, 878), (783, 632), (861, 342), (973, 46)], 76),
            ([(415, 1000), (476, 892), (541, 812), (606, 758)], 46),
        ],
    )
    wing = passive_selections(shape)["wing"]
    return {"appendages": appendages, "wing": wing}


def wheel_region(shape: tuple[int, int]) -> np.ndarray:
    """The photographed rim is replaced by the live 60-tooth SVG wheel."""

    return polygon_mask(
        shape,
        [
            (0, 1288),
            (188, 1238),
            (347, 1162),
            (520, 1112),
            (745, 1092),
            (960, 1106),
            (1190, 1152),
            (1398, 1230),
            (1600, 1320),
            (1600, 1346),
            (0, 1346),
        ],
    )


def live_wheel_clearance_region(
    shape: tuple[int, int],
    lift: int = 84,
) -> np.ndarray:
    """Reserve the live SVG tooth tips plus their filtered shadow clearance.

    The source photograph's visible wheel boundary registers about 15 SVG px
    below the generated 60-tooth rim.  In addition, ``corpusBugShadow`` has an
    8 px blur.  Moving the photographic cutout 84 source pixels upward leaves
    roughly 10 SVG px of clean air above the live tips at the crown.
    """

    wheel = wheel_region(shape)
    shifted = np.zeros_like(wheel)
    if lift <= 0:
        return wheel
    shifted[:-lift] = wheel[lift:]
    return cv2.max(wheel, shifted)


def clearance_multiplier(
    exclusion: np.ndarray,
    feather: int = 30,
) -> np.ndarray:
    """Softly taper a photographic alpha before a hard live-wheel exclusion."""

    outside = (exclusion == 0).astype(np.uint8)
    distance = cv2.distanceTransform(outside, cv2.DIST_L2, 5)
    phase = np.clip(distance / float(feather), 0.0, 1.0)
    return phase * phase * (3.0 - 2.0 * phase)


def rounded_root_support(
    selection: np.ndarray,
    pivot: tuple[int, int],
    forward_point: tuple[int, int],
    cap_radius: float,
    feather: float = 30.0,
    zone_radius: float = 92.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Round and softly bury a rigid cover root into the photographed torso."""

    y_grid, x_grid = np.indices(selection.shape)
    dx = float(forward_point[0] - pivot[0])
    dy = float(forward_point[1] - pivot[1])
    length = float(np.hypot(dx, dy))
    dx /= length
    dy /= length
    offset_x = x_grid - pivot[0]
    offset_y = y_grid - pivot[1]
    projection = offset_x * dx + offset_y * dy
    radial = np.hypot(offset_x, offset_y)
    zone = radial <= zone_radius

    # Replace the source polygon's straight terminal chord with a circular cap.
    keep = (projection >= 0.0) | (radial <= cap_radius)
    rounded = selection.copy()
    rounded[zone & ~keep] = 0

    # The photographed cover reaches full opacity at the pivot and fades over
    # ~30 source pixels (about 9.4 px in the final SVG placement).
    phase = np.clip((projection + cap_radius) / feather, 0.0, 1.0)
    phase = phase * phase * (3.0 - 2.0 * phase)
    matte = np.ones(selection.shape, np.float32)
    matte[zone & (projection < 0.0)] = phase[zone & (projection < 0.0)]
    matte[rounded == 0] = 0.0
    return rounded, matte


def bronze_grade(source: np.ndarray) -> np.ndarray:
    """A restrained warm grade that keeps the source's photographed detail."""

    rgb = cv2.cvtColor(source, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    rgb = np.power(rgb, 0.90)
    rgb *= np.asarray([1.055, 0.985, 0.88], np.float32)
    luminance = rgb.mean(axis=2, keepdims=True)
    bronze = np.asarray([0.33, 0.20, 0.075], np.float32)
    rgb = rgb * 0.91 + bronze * (1.0 - luminance) * 0.16
    return (np.clip(rgb, 0, 1) * 255).astype(np.uint8)


def registered_mask(mask: np.ndarray) -> np.ndarray:
    return np.asarray(
        Image.fromarray(mask, "L").resize(CANVAS_SIZE, Image.Resampling.NEAREST)
    )


def registered_rgba(
    rgb: np.ndarray,
    alpha: np.ndarray,
    source_exclusion: np.ndarray | None = None,
) -> Image.Image:
    clean_rgb = rgb.copy()
    clean_rgb[alpha <= 1] = 0
    rgba = np.dstack([clean_rgb, alpha])
    image = Image.fromarray(rgba, "RGBA").resize(CANVAS_SIZE, Image.Resampling.LANCZOS)

    # Lanczos can interpolate hidden colour into fully transparent pixels even
    # when the source RGB was cleared.  Some WebP viewers display that hidden
    # colour as large rectangular bands.  Clear it *after* the resize as well,
    # so the registered asset is clean in straight- and premultiplied-alpha
    # renderers alike.
    resized = np.asarray(image).copy()
    if source_exclusion is not None:
        exclusion = registered_mask(source_exclusion)
        resized[exclusion > 0] = 0
    resized[resized[:, :, 3] <= 1, :3] = 0
    return Image.fromarray(resized, "RGBA")


def save_registered_layer(
    rgb: np.ndarray,
    alpha: np.ndarray,
    destination: Path,
    source_exclusion: np.ndarray | None = None,
) -> None:
    image = registered_rgba(rgb, alpha, source_exclusion)
    # ``exact=True`` prevents libwebp from substituting arbitrary RGB values
    # beneath alpha=0.  Those substitutions are legal but trigger visible
    # rectangles in a few inspection/rendering pipelines.
    image.save(destination, "WEBP", lossless=True, method=6, exact=True)


def checkerboard(background_a: tuple[int, int, int], background_b: tuple[int, int, int]) -> Image.Image:
    pixels = np.empty((CANVAS_SIZE[1], CANVAS_SIZE[0], 4), np.uint8)
    pixels[:, :, 3] = 255
    y_grid, x_grid = np.indices((CANVAS_SIZE[1], CANVAS_SIZE[0]))
    light = ((x_grid // 32 + y_grid // 32) % 2) == 0
    pixels[:, :, :3] = background_a
    pixels[light, :3] = background_b
    return Image.fromarray(pixels, "RGBA")


def shift_registered_texture(
    rgb: np.ndarray,
    alpha: np.ndarray,
    offset_x: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Translate a neighbouring wire sample without wrapping at the edge."""

    shifted_rgb = np.zeros_like(rgb)
    shifted_alpha = np.zeros_like(alpha)
    if offset_x > 0:
        shifted_rgb[:, offset_x:] = rgb[:, :-offset_x]
        shifted_alpha[:, offset_x:] = alpha[:, :-offset_x]
    elif offset_x < 0:
        amount = -offset_x
        shifted_rgb[:, :-amount] = rgb[:, amount:]
        shifted_alpha[:, :-amount] = alpha[:, amount:]
    else:
        shifted_rgb[:] = rgb
        shifted_alpha[:] = alpha
    return shifted_rgb, shifted_alpha


def horizontal_body_bridge(
    rgb: np.ndarray,
    carved_alpha: np.ndarray,
    carve_mask: np.ndarray,
    semantic_support: np.ndarray,
    search_radius: int = 96,
) -> tuple[np.ndarray, np.ndarray]:
    """Clone horizontally continuous body texture across a removed cover.

    The Chronophage's thorax and body tube run horizontally.  A scanline is
    synthesized only when real opaque torso pixels exist immediately on *both*
    sides of a carved run.  Consequently tall arches over glass stay
    transparent, while the narrow body/cover crossings receive a natural
    left-to-right bridge instead of Telea's conspicuous vertical grey smear.
    """

    output = rgb.copy()
    fill = np.zeros_like(carved_alpha, np.uint8)
    valid = carved_alpha > 64
    candidate = (carve_mask > 0) & semantic_support
    height, width = carved_alpha.shape

    for y in range(height):
        xs = np.flatnonzero(candidate[y])
        if not len(xs):
            continue
        breaks = np.flatnonzero(np.diff(xs) > 1)
        starts = np.r_[0, breaks + 1]
        ends = np.r_[breaks, len(xs) - 1]
        for start_index, end_index in zip(starts, ends):
            x0 = int(xs[start_index])
            x1 = int(xs[end_index])
            left_candidates = np.flatnonzero(valid[y, max(0, x0 - search_radius):x0])
            right_candidates = np.flatnonzero(valid[y, x1 + 1:min(width, x1 + 1 + search_radius)])
            if not len(left_candidates) or not len(right_candidates):
                continue
            left_x = max(0, x0 - search_radius) + int(left_candidates[-1])
            right_x = x1 + 1 + int(right_candidates[0])
            # Do not bridge between unrelated silhouettes separated by glass.
            if x0 - left_x > 34 or right_x - x1 > 34:
                continue

            left_slice = np.arange(max(0, left_x - 11), left_x + 1)
            right_slice = np.arange(right_x, min(width, right_x + 12))
            left_slice = left_slice[valid[y, left_slice]]
            right_slice = right_slice[valid[y, right_slice]]
            if not len(left_slice) or not len(right_slice):
                continue
            left_mean = rgb[y, left_slice].astype(np.float32).mean(axis=0)
            right_mean = rgb[y, right_slice].astype(np.float32).mean(axis=0)
            left_detail = rgb[y, left_slice].astype(np.float32) - left_mean
            right_detail = rgb[y, right_slice].astype(np.float32) - right_mean

            run = np.arange(x0, x1 + 1)
            t = ((run - x0 + 1) / (len(run) + 1)).astype(np.float32)[:, None]
            colour = left_mean[None, :] * (1.0 - t) + right_mean[None, :] * t
            # Reuse restrained neighbouring high-frequency bronze texture so
            # the bridge does not read as a flat painted band.
            left_noise = left_detail[np.arange(len(run)) % len(left_detail)]
            right_noise = right_detail[np.arange(len(run)) % len(right_detail)]
            colour += (left_noise * (1.0 - t) + right_noise * t) * 0.32
            output[y, run] = np.clip(colour, 0, 255).astype(np.uint8)
            fill[y, run] = 255

    # Feather just the source-colour transition.  Alpha remains confined to
    # the exact semantic body support and is never expanded onto glass.
    feather = cv2.GaussianBlur(fill, (0, 0), 3.2).astype(np.float32) / 255.0
    feather *= semantic_support.astype(np.float32)
    blended = (
        output.astype(np.float32) * feather[:, :, None]
        + rgb.astype(np.float32) * (1.0 - feather[:, :, None])
    )
    return np.clip(blended, 0, 255).astype(np.uint8), fill


def motion_exposure_mask(
    support: np.ndarray,
    pivot: tuple[int, int],
    rotation_range: tuple[float, float],
) -> np.ndarray:
    """Pixels of the neutral cover that an allowed rotation can uncover."""

    always_covered = support > 0
    angles = np.arange(rotation_range[0], rotation_range[1] + 0.001, 0.25)
    for angle in angles:
        matrix = cv2.getRotationMatrix2D(pivot, float(angle), 1.0)
        rotated = cv2.warpAffine(
            support,
            matrix,
            (support.shape[1], support.shape[0]),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        always_covered &= rotated > 0
    exposed = (support > 0) & ~always_covered
    # Eight source pixels of safety beyond the analytically exposed edge.
    exposed = cv2.dilate(
        exposed.astype(np.uint8) * 255,
        np.ones((17, 17), np.uint8),
        iterations=1,
    )
    exposed[support == 0] = 0
    return exposed


def vertical_nearest_clone(
    rgb: np.ndarray,
    repair_mask: np.ndarray,
    donor_mask: np.ndarray,
    max_distance: int = 72,
) -> np.ndarray:
    """Replace thin horizontal crossings with nearest vertical limb texture."""

    output = rgb.copy()
    for x in np.flatnonzero(np.any(repair_mask, axis=0)):
        targets = np.flatnonzero(repair_mask[:, x])
        donors = np.flatnonzero(donor_mask[:, x] & ~repair_mask[:, x])
        if not len(donors):
            continue
        insertion = np.searchsorted(donors, targets)
        lower_index = np.clip(insertion - 1, 0, len(donors) - 1)
        upper_index = np.clip(insertion, 0, len(donors) - 1)
        lower = donors[lower_index]
        upper = donors[upper_index]
        use_upper = np.abs(upper - targets) < np.abs(targets - lower)
        nearest = np.where(use_upper, upper, lower)
        valid = np.abs(nearest - targets) <= max_distance
        output[targets[valid], x] = rgb[nearest[valid], x]
    return output


def save_mask_preview(labels: np.ndarray, destination: Path) -> None:
    # RGB values correspond to the layer legend in the module docstring.
    palette = np.asarray(
        [
            (9, 12, 17, 255),
            (224, 162, 54, 255),
            (42, 214, 238, 255),
            (54, 123, 242, 255),
            (38, 196, 170, 255),
            (236, 67, 193, 255),
            (139, 75, 224, 255),
            (255, 116, 171, 255),
            (82, 210, 112, 255),
            (238, 67, 67, 255),
        ],
        np.uint8,
    )
    rgba = palette[labels]
    image = Image.fromarray(rgba, "RGBA").resize(CANVAS_SIZE, Image.Resampling.NEAREST)
    image.save(destination, "WEBP", lossless=True, method=6)


def canvas_point(point: tuple[int, int]) -> list[float]:
    return [
        round(point[0] * CANVAS_SIZE[0] / SOURCE_SIZE[0], 3),
        round(point[1] * CANVAS_SIZE[1] / SOURCE_SIZE[1], 3),
    ]


def save_rig_metadata(destination: Path) -> None:
    metadata: dict[str, object] = {
        "version": 3,
        "coordinateSystem": {
            "canvas": {"width": CANVAS_SIZE[0], "height": CANVAS_SIZE[1]},
            "source": {"width": SOURCE_SIZE[0], "height": SOURCE_SIZE[1]},
            "origin": "top-left",
            "xAxis": "right",
            "yAxis": "down",
            "angleUnit": "degrees",
            "positiveAngle": "clockwise in screen coordinates",
        },
        "legs": {},
    }
    legs = metadata["legs"]
    assert isinstance(legs, dict)
    for leg_name, geometry in RIG_GEOMETRY.items():
        upper = geometry["upper"]
        lower = geometry["lower"]
        pad = geometry["pad"]
        legs[leg_name] = {
            "combinedAsset": f"chronophage-{leg_name}-pallet-v3.webp",
            "upper": {
                "asset": f"chronophage-{leg_name}-upper-v3.webp",
                "sourceStart": list(upper["start"]),
                "sourceEnd": list(upper["end"]),
                "start": canvas_point(upper["start"]),
                "end": canvas_point(upper["end"]),
            },
            "lower": {
                "asset": f"chronophage-{leg_name}-lower-v3.webp",
                "sourceStart": list(lower["start"]),
                "sourceEnd": list(lower["end"]),
                "start": canvas_point(lower["start"]),
                "end": canvas_point(lower["end"]),
            },
            "palletPad": {
                "asset": f"chronophage-{leg_name}-pallet-pad-v3.webp",
                "sourceCenter": list(pad["center"]),
                "center": canvas_point(pad["center"]),
                "tangentAngleDeg": pad["tangentAngleDeg"],
            },
        }
    destination.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _contact_side_mask(
    shape: tuple[int, int],
    edge: tuple[tuple[int, int], tuple[int, int]],
) -> np.ndarray:
    """Return the cover side of a photographed contact edge (above it)."""

    (x1, y1), (x2, y2) = edge
    y_grid, x_grid = np.indices(shape)
    cross = (x_grid - x1) * (y2 - y1) - (y_grid - y1) * (x2 - x1)
    return np.where(cross >= -2, 255, 0).astype(np.uint8)


def _orientation_degrees(start: tuple[int, int], end: tuple[int, int]) -> float:
    return round(float(np.degrees(np.arctan2(end[1] - start[1], end[0] - start[0]))), 3)


def _asset_alpha_info(path: Path) -> dict[str, object]:
    with Image.open(path) as image:
        alpha = np.asarray(image.convert("RGBA"))[:, :, 3]
    ys, xs = np.nonzero(alpha > 8)
    bbox = None if not len(xs) else [int(xs.min()), int(ys.min()), int(xs.max() + 1), int(ys.max() + 1)]
    return {"alphaPixels": int(np.count_nonzero(alpha > 8)), "alphaBBox": bbox}


def save_rig_metadata_v4(
    destination: Path,
    assets: dict[str, Path],
    overlap_pixels: dict[str, int],
    static_live_wheel_overlap: int,
    clean_plate_uncovered: int,
) -> None:
    covers: dict[str, object] = {}
    for name, geometry in RIG_GEOMETRY_V4.items():
        pivot = geometry["pivot"]
        foot = geometry["footCenter"]
        edge = geometry["contactEdge"]
        assert isinstance(pivot, tuple) and isinstance(foot, tuple) and isinstance(edge, tuple)
        asset_name = f"chronophage-{name}-cover-v4.webp"
        covers[name] = {
            "asset": asset_name,
            "rigidity": "single rigid photographic cosmetic cover",
            "sourcePivot": list(pivot),
            "pivot": canvas_point(pivot),
            "sourceFootCenter": list(foot),
            "footCenter": canvas_point(foot),
            "sourceContactEdge": [list(edge[0]), list(edge[1])],
            "contactEdge": [canvas_point(edge[0]), canvas_point(edge[1])],
            "originalOrientationDeg": _orientation_degrees(pivot, foot),
            "contactTangentDeg": _orientation_degrees(edge[0], edge[1]),
            "recommendedRotationDeg": list(geometry["recommendedRotationDeg"]),
            "registeredAssetSize": {"width": CANVAS_SIZE[0], "height": CANVAS_SIZE[1]},
            "assetInspection": _asset_alpha_info(assets[name]),
        }

    metadata: dict[str, object] = {
        "version": 4,
        "coordinateSystem": {
            "canvas": {"width": CANVAS_SIZE[0], "height": CANVAS_SIZE[1]},
            "source": {"width": SOURCE_SIZE[0], "height": SOURCE_SIZE[1]},
            "origin": "top-left",
            "xAxis": "right",
            "yAxis": "down",
            "angleUnit": "degrees",
            "positiveAngle": "clockwise in screen coordinates",
        },
        "recommendedRuntime": {
            "hostViewBox": {"width": 1024, "height": 1180},
            "registeredCanvasPlacement": {
                "x": 242,
                "y": -25,
                "width": 500,
                "height": 420,
                "uniformScale": 0.48828125,
            },
            "note": "Keep every registered v4 layer at this identical placement; rotate covers about their registered pivots.",
        },
        "staticAssets": {
            "torso": assets["torso"].name,
            "passive": assets["passive"].name,
            "jaw": assets["jaw"].name,
        },
        "covers": covers,
        "quality": {
            "activeWheelOverlapPixels": overlap_pixels,
            "staticLiveWheelOverlapPixels": static_live_wheel_overlap,
            "cleanPlateUncoveredTorsoPixels": clean_plate_uncovered,
            "wheelRegionDefinition": "active-cover old-photo wheel exclusion: source wheel support excluding exact foot whitelists, plus a one-source-pixel guard",
            "staticLiveWheelClearance": {
                "sourceLiftPixels": 84,
                "purpose": "keeps torso/passive alpha and its 8 px SVG drop shadow clear of live tooth tips",
            },
            "wheelClearanceFeather": {
                "sourcePixels": 30,
                "finalSvgPixelsApprox": 9.4,
            },
            "coverRootFeather": {
                "sourcePixels": 32,
                "finalSvgPixelsApprox": 10.0,
            },
            "motionExposureFringe": "transparent where no trustworthy same-patina donor exists; no synthetic opaque glass or rectangular inpaint",
            "overlapThreshold": 8,
        },
    }
    destination.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_v4(
    source: np.ndarray,
    subject_alpha: np.ndarray,
    graded: np.ndarray,
    output_dir: Path,
) -> None:
    """Build the rigid-cover v4 rig and deterministic inspection renders."""

    shape = source.shape[:2]
    lab = cv2.cvtColor(source, cv2.COLOR_BGR2LAB)
    hsv = cv2.cvtColor(source, cv2.COLOR_BGR2HSV)
    luminance = lab[:, :, 0]
    saturation = hsv[:, :, 1]
    foreground = subject_alpha > 8

    front_support, front_root_matte = rounded_root_support(
        front_cover_v4_selection(shape),
        RIG_GEOMETRY_V4["front"]["pivot"],
        RIG_GEOMETRY_V4["front"]["footCenter"],
        cap_radius=20.0,
        feather=32.0,
    )
    rear_support, rear_root_matte = rounded_root_support(
        rear_cover_v4_selection(shape),
        RIG_GEOMETRY_V4["rear"]["pivot"],
        (1062, 16),
        cap_radius=28.0,
        feather=32.0,
    )
    root_mattes = {"front": front_root_matte, "rear": rear_root_matte}
    active_support = cv2.max(front_support, rear_support)

    # Classify the visible old wheel itself, not the cover shoe that occludes
    # it.  The broad geometric rim polygon alone would incorrectly amputate
    # both genuine contact shoes.  A two-pixel guard also removes dark antialias
    # fringes around the bright gold teeth and rim.
    wheel_geometry = wheel_region(shape) > 0
    wheel_clearance = live_wheel_clearance_region(shape) > 0
    wheel_matte = clearance_multiplier(wheel_clearance.astype(np.uint8) * 255, feather=30)
    foot_whitelist = cv2.max(
        front_foot_v4_selection(shape),
        rear_foot_v4_selection(shape),
    )
    wheel_exclusion = wheel_geometry & (foot_whitelist == 0)
    visible_wheel = cv2.dilate(
        wheel_exclusion.astype(np.uint8) * 255,
        np.ones((3, 3), np.uint8),
        iterations=1,
    )
    visible_wheel[foot_whitelist > 0] = 0

    cover_material = foreground & (
        (luminance < 105)
        | ((saturation > 52) & (luminance < 168))
    )
    passive_parts = passive_v4_selections(shape)
    wing_wire_material = (
        foreground
        & (passive_parts["wing"] > 0)
        & (saturation > 50)
        & (luminance > 64)
    ).astype(np.uint8) * 255
    horizontal_wire = cv2.morphologyEx(
        wing_wire_material,
        cv2.MORPH_OPEN,
        np.ones((1, 13), np.uint8),
    )
    vertical_solid = cv2.morphologyEx(
        wing_wire_material,
        cv2.MORPH_OPEN,
        np.ones((11, 1), np.uint8),
    )
    wire_contamination = (horizontal_wire > 0) & (vertical_solid == 0)
    wire_contamination = cv2.dilate(
        wire_contamination.astype(np.uint8) * 255,
        np.ones((3, 3), np.uint8),
        iterations=1,
    ) > 0
    bright_wing_wire = (
        (passive_parts["wing"] > 0)
        & (luminance > 92)
        & (saturation > 62)
    )
    wire_contamination |= cv2.dilate(
        bright_wing_wire.astype(np.uint8) * 255,
        np.ones((3, 3), np.uint8),
        iterations=1,
    ) > 0
    rear_wing_core = stroked_mask(
        shape,
        [
            ([(842, 708), (834, 800), (827, 900), (823, 995)], 58),
            ([(1065, 708), (1067, 820), (1066, 920), (1060, 1010)], 34),
        ],
    )
    rear_wing_trim = (
        (passive_parts["wing"] > 0)
        & (rear_support > 0)
        & (rear_wing_core == 0)
        & (foot_whitelist == 0)
    )
    rear_wire_repair = (
        wire_contamination
        & (rear_wing_core > 0)
        & (rear_support > 0)
        & (foot_whitelist == 0)
    )
    rear_wire_remove = rear_wing_trim | (
        wire_contamination
        & (rear_wing_core == 0)
        & (foot_whitelist == 0)
    )
    rear_repaired_rgb = vertical_nearest_clone(
        graded,
        rear_wire_repair,
        (rear_wing_core > 0)
        & (rear_support > 0)
        & cover_material
        & ~wire_contamination,
    )
    active_rgb = {"front": graded, "rear": rear_repaired_rgb}
    active_alpha: dict[str, np.ndarray] = {}
    for name, support in (("front", front_support), ("rear", rear_support)):
        alpha = np.where((support > 0) & cover_material, subject_alpha, 0).astype(np.uint8)
        alpha = (
            alpha.astype(np.float32) * root_mattes[name]
        ).astype(np.uint8)
        alpha[visible_wheel > 0] = 0
        if name == "rear":
            alpha[rear_wire_remove] = 0
            alpha[rear_wire_repair] = 255
        alpha = cv2.GaussianBlur(alpha, (0, 0), 0.30)
        alpha[(support == 0) | (visible_wheel > 0)] = 0
        if name == "rear":
            alpha[rear_wire_remove] = 0
            alpha[rear_wire_repair] = 255
        alpha = (
            alpha.astype(np.float32) * root_mattes[name]
        ).astype(np.uint8)
        alpha[visible_wheel > 0] = 0
        active_alpha[name] = alpha

    front_exposure = motion_exposure_mask(
        front_support,
        RIG_GEOMETRY_V4["front"]["pivot"],
        RIG_GEOMETRY_V4["front"]["recommendedRotationDeg"],
    )
    rear_exposure = motion_exposure_mask(
        rear_support,
        RIG_GEOMETRY_V4["rear"]["pivot"],
        RIG_GEOMETRY_V4["rear"]["recommendedRotationDeg"],
    )
    active_carve = cv2.max(front_exposure, rear_exposure)
    torso_support = torso_selection(shape) > 0
    torso_base = np.where(torso_support & foreground, subject_alpha, 0).astype(np.uint8)
    torso_alpha = torso_base.copy()
    torso_alpha[active_carve > 0] = 0

    # A photographic donor with matching patina does not exist for the two
    # narrow crossings.  Keep their motion-exposure fringe transparent: this
    # is visually honest and, unlike broad inpaint, cannot create an opaque
    # grey/striped column over the museum glass.  The neutral cover hides the
    # fringe in the assembled clock.
    torso_rgb = graded
    torso_fill = np.zeros(shape, dtype=bool)
    torso_alpha = cv2.GaussianBlur(torso_alpha, (0, 0), 0.30)
    torso_alpha = (
        torso_alpha.astype(np.float32) * wheel_matte
    ).astype(np.uint8)
    torso_alpha[wheel_clearance] = 0

    appendage_mask = (
        foreground
        & (passive_parts["appendages"] > 0)
        & ~torso_support
    )
    wing_material = (saturation > 50) & (luminance > 64) & (luminance < 215)
    wing_mask = foreground & (passive_parts["wing"] > 0) & wing_material
    passive_support = appendage_mask | wing_mask
    passive_base_alpha = np.where(passive_support, subject_alpha, 0).astype(np.uint8)
    passive_alpha = passive_base_alpha.copy()
    passive_alpha[active_carve > 0] = 0
    passive_rgb = graded
    bridge_pixels = np.zeros(shape, dtype=bool)
    passive_alpha = cv2.GaussianBlur(passive_alpha, (0, 0), 0.28)
    passive_alpha[(active_carve > 0) & ~bridge_pixels] = 0
    passive_alpha = (
        passive_alpha.astype(np.float32) * wheel_matte
    ).astype(np.uint8)
    passive_alpha[wheel_clearance] = 0

    jaw_support = jaw_selection(shape) > 0
    jaw_alpha = np.where(jaw_support & foreground, subject_alpha, 0).astype(np.uint8)
    jaw_alpha = cv2.GaussianBlur(jaw_alpha, (0, 0), 0.30)
    jaw_alpha = (
        jaw_alpha.astype(np.float32) * wheel_matte
    ).astype(np.uint8)
    jaw_alpha[wheel_clearance] = 0

    paths: dict[str, Path] = {}
    static_specs = {
        "torso": (torso_rgb, torso_alpha),
        "passive": (passive_rgb, passive_alpha),
        "jaw": (graded, jaw_alpha),
    }
    for name, (rgb, alpha) in static_specs.items():
        path = output_dir / f"chronophage-{name}-v4.webp"
        save_registered_layer(
            rgb,
            alpha,
            path,
            wheel_clearance.astype(np.uint8) * 255,
        )
        paths[name] = path
    for name in ("front", "rear"):
        path = output_dir / f"chronophage-{name}-cover-v4.webp"
        save_registered_layer(active_rgb[name], active_alpha[name], path, visible_wheel)
        paths[name] = path

    layers = {name: Image.open(path).convert("RGBA") for name, path in paths.items()}
    complete = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    for name in ("passive", "rear", "torso", "jaw", "front"):
        complete.alpha_composite(layers[name])
    complete.save(
        output_dir / "chronophage-composite-v4.webp",
        "WEBP",
        lossless=True,
        method=6,
        exact=True,
    )

    qa_backgrounds = {
        "composite": checkerboard((20, 24, 30), (58, 65, 75)),
        "black": Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 255)),
        "white": Image.new("RGBA", CANVAS_SIZE, (255, 255, 255, 255)),
    }
    for qa_name, background in qa_backgrounds.items():
        qa = background.copy()
        qa.alpha_composite(complete)
        qa.convert("RGB").save(
            output_dir / f"chronophage-qa-{qa_name}-v4.webp",
            "WEBP",
            lossless=True,
            method=6,
        )

    clean_plate = checkerboard((22, 25, 31), (62, 68, 78))
    for name in ("passive", "torso", "jaw"):
        clean_plate.alpha_composite(layers[name])
    clean_plate.convert("RGB").save(
        output_dir / "chronophage-qa-clean-plate-v4.webp",
        "WEBP",
        lossless=True,
        method=6,
    )

    # Source-mask legend: amber torso, green passive, red jaw, cyan front,
    # magenta rear; pale blue identifies synthesized body clean-plate pixels.
    preview = np.zeros((*shape, 4), np.uint8)
    preview[:, :, :] = (9, 12, 17, 255)
    preview[torso_alpha > 8] = (224, 162, 54, 255)
    preview[passive_alpha > 8] = (82, 210, 112, 255)
    preview[jaw_alpha > 8] = (238, 67, 67, 255)
    preview[active_alpha["rear"] > 8] = (236, 67, 193, 255)
    preview[active_alpha["front"] > 8] = (42, 214, 238, 255)
    preview[torso_fill] = (118, 196, 255, 255)
    Image.fromarray(preview, "RGBA").resize(CANVAS_SIZE, Image.Resampling.NEAREST).save(
        output_dir / "chronophage-mask-preview-v4.webp",
        "WEBP",
        lossless=True,
        method=6,
        exact=True,
    )

    wheel_registered = registered_mask(visible_wheel) > 0
    overlap_pixels: dict[str, int] = {}
    for name in ("front", "rear"):
        layer_alpha = np.asarray(layers[name])[:, :, 3]
        overlap_pixels[name] = int(np.count_nonzero((layer_alpha > 8) & wheel_registered))
    overlap_pixels["total"] = overlap_pixels["front"] + overlap_pixels["rear"]
    if overlap_pixels["total"] > 4:
        raise RuntimeError(f"v4 active cover still contains old wheel pixels: {overlap_pixels}")

    overlap_qa = np.zeros((CANVAS_SIZE[1], CANVAS_SIZE[0], 4), np.uint8)
    overlap_qa[:, :, :] = (13, 16, 22, 255)
    overlap_qa[wheel_registered] = (238, 67, 67, 255)
    active_registered = (
        (np.asarray(layers["front"])[:, :, 3] > 8)
        | (np.asarray(layers["rear"])[:, :, 3] > 8)
    )
    overlap_qa[active_registered] = (64, 224, 126, 255)
    overlap_qa[active_registered & wheel_registered] = (255, 235, 61, 255)
    Image.fromarray(overlap_qa, "RGBA").convert("RGB").save(
        output_dir / "chronophage-qa-wheel-overlap-v4.webp",
        "WEBP",
        lossless=True,
        method=6,
    )

    live_clearance_registered = registered_mask(
        wheel_clearance.astype(np.uint8) * 255
    ) > 0
    static_registered = np.maximum.reduce(
        [np.asarray(layers[name])[:, :, 3] for name in ("torso", "passive", "jaw")]
    ) > 8
    static_live_wheel_overlap = int(
        np.count_nonzero(static_registered & live_clearance_registered)
    )
    if static_live_wheel_overlap:
        raise RuntimeError(
            "v4 static body still crosses the live wheel clearance: "
            f"{static_live_wheel_overlap} pixels"
        )
    live_clearance_qa = np.zeros((CANVAS_SIZE[1], CANVAS_SIZE[0], 4), np.uint8)
    live_clearance_qa[:, :, :] = (13, 16, 22, 255)
    live_clearance_qa[live_clearance_registered] = (238, 67, 67, 255)
    live_clearance_qa[static_registered] = (64, 224, 126, 255)
    live_clearance_qa[static_registered & live_clearance_registered] = (255, 235, 61, 255)
    Image.fromarray(live_clearance_qa, "RGBA").convert("RGB").save(
        output_dir / "chronophage-qa-live-clearance-v4.webp",
        "WEBP",
        lossless=True,
        method=6,
    )

    motion = checkerboard((18, 22, 28), (53, 60, 70))
    for name in ("passive", "torso", "jaw"):
        motion.alpha_composite(layers[name])
    tint_colours = {"front": np.array([40, 218, 238]), "rear": np.array([238, 72, 196])}
    for name in ("rear", "front"):
        pivot = tuple(canvas_point(RIG_GEOMETRY_V4[name]["pivot"]))
        for angle in RIG_GEOMETRY_V4[name]["recommendedRotationDeg"]:
            rotated = layers[name].rotate(
                -float(angle),
                resample=Image.Resampling.BICUBIC,
                center=pivot,
                expand=False,
            )
            tinted = np.asarray(rotated).copy()
            visible = tinted[:, :, 3] > 0
            tinted[visible, :3] = (
                tinted[visible, :3].astype(np.float32) * 0.45
                + tint_colours[name] * 0.55
            ).astype(np.uint8)
            tinted[:, :, 3] = (tinted[:, :, 3].astype(np.float32) * 0.56).astype(np.uint8)
            motion.alpha_composite(Image.fromarray(tinted, "RGBA"))
    motion.alpha_composite(layers["rear"])
    motion.alpha_composite(layers["front"])
    draw = ImageDraw.Draw(motion)
    for name, colour in (("front", (42, 214, 238, 255)), ("rear", (236, 67, 193, 255))):
        pivot = canvas_point(RIG_GEOMETRY_V4[name]["pivot"])
        foot = canvas_point(RIG_GEOMETRY_V4[name]["footCenter"])
        edge = [canvas_point(point) for point in RIG_GEOMETRY_V4[name]["contactEdge"]]
        draw.ellipse((pivot[0] - 6, pivot[1] - 6, pivot[0] + 6, pivot[1] + 6), fill=colour)
        draw.line((edge[0][0], edge[0][1], edge[1][0], edge[1][1]), fill=colour, width=4)
        draw.line((pivot[0], pivot[1], foot[0], foot[1]), fill=colour, width=2)
    motion.convert("RGB").save(
        output_dir / "chronophage-qa-motion-safe-v4.webp",
        "WEBP",
        lossless=True,
        method=6,
    )

    # Inspect the interior of the synthesized clean plate; the one-pixel edge
    # is intentionally antialiased by the registered downscale.
    torso_fill_interior = cv2.erode(
        torso_fill.astype(np.uint8) * 255,
        np.ones((3, 3), np.uint8),
        iterations=1,
    )
    torso_fill_registered = registered_mask(torso_fill_interior) > 0
    torso_registered_alpha = np.asarray(layers["torso"])[:, :, 3]
    clean_plate_uncovered = int(
        np.count_nonzero(torso_fill_registered & (torso_registered_alpha < 128))
    )
    if clean_plate_uncovered:
        raise RuntimeError(f"v4 clean plate has {clean_plate_uncovered} uncovered torso pixels")
    save_rig_metadata_v4(
        output_dir / "chronophage-rig-v4.json",
        paths,
        overlap_pixels,
        static_live_wheel_overlap,
        clean_plate_uncovered,
    )

    for layer in layers.values():
        layer.close()


def main() -> None:
    args = parse_args()
    source = cv2.imread(str(args.source), cv2.IMREAD_COLOR)
    if source is None:
        raise SystemExit(f"Unable to read {args.source}")
    if (source.shape[1], source.shape[0]) != SOURCE_SIZE:
        raise SystemExit(
            f"Expected the {SOURCE_SIZE[0]}x{SOURCE_SIZE[1]} reference, "
            f"got {source.shape[1]}x{source.shape[0]}"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    shape = source.shape[:2]
    subject_alpha = initial_foreground_mask(source)

    front = front_pallet_selections(shape)
    rear = rear_pallet_selections(shape)
    passive_parts = passive_selections(shape)
    passive_union = cv2.max(passive_parts["appendages"], passive_parts["wing"])
    selections = {**front, **rear, "passive": passive_union, "jaw": jaw_selection(shape)}
    front_union = np.maximum.reduce(list(front.values()))
    rear_union = np.maximum.reduce(list(rear.values()))
    wheel = wheel_region(shape)

    # Assign every foreground pixel to exactly one semantic layer.  Priority
    # keeps the two animated pallets intact where they cross passive spines.
    foreground = subject_alpha > 8
    leg_luminance = cv2.cvtColor(source, cv2.COLOR_BGR2LAB)[:, :, 0]
    leg_saturation = cv2.cvtColor(source, cv2.COLOR_BGR2HSV)[:, :, 1]
    leg_material = (leg_luminance < 90) | ((leg_saturation > 74) & (leg_luminance < 134))
    leg_foreground = foreground & leg_material
    wing_material = (leg_saturation > 52) & (leg_luminance > 66)
    torso_support = torso_selection(shape) > 0
    labels = np.zeros(shape, np.uint8)
    labels[foreground & torso_support] = 1

    # Static leg roots disappear naturally into the solid thorax; only keep
    # their narrow support outside the torso.  For the wing, require the warm,
    # luminous wire material so the broad dark body beneath the polygon cannot
    # become rectangular "wing" slabs.
    labels[
        foreground
        & (passive_parts["appendages"] > 0)
        & ~torso_support
    ] = 8
    labels[
        foreground
        & (passive_parts["wing"] > 0)
        & wing_material
    ] = 8

    # Cut both full main-pallet silhouettes out of every static layer first.
    # The stricter metal test below may intentionally omit glass-coloured
    # highlights from a movable sprite; without this unconditional carve those
    # rejected pixels could leave a ghost of the original complete leg baked
    # into the torso or passive layer.
    main_pallet_union = (front_union > 0) | (rear_union > 0)
    labels[main_pallet_union] = 0

    labels[leg_foreground & (selections["rear-upper"] > 0)] = 5
    labels[leg_foreground & (selections["rear-lower"] > 0)] = 6
    labels[leg_foreground & (selections["rear-pallet-pad"] > 0)] = 7
    labels[leg_foreground & (selections["front-upper"] > 0)] = 2
    labels[leg_foreground & (selections["front-lower"] > 0)] = 3
    labels[leg_foreground & (selections["front-pallet-pad"] > 0)] = 4
    labels[foreground & (selections["jaw"] > 0)] = 9

    # Remove the old clock rim from all static photographic parts.  Pallet
    # contact shoes remain because they must visibly meet the generated teeth.
    labels[(wheel > 0) & np.isin(labels, [1, 8, 9])] = 0

    layer_ids = {
        "torso": 1,
        "passive": 8,
        "jaw": 9,
    }
    graded = bronze_grade(source)
    destinations: dict[str, Path] = {}
    for name, layer_id in layer_ids.items():
        alpha = np.where(labels == layer_id, subject_alpha, 0).astype(np.uint8)
        # A tiny matte softening removes colour-fringed one-pixel stair steps
        # without growing one semantic mask back into another.
        alpha = cv2.GaussianBlur(alpha, (0, 0), 0.34)
        if name in {"torso", "passive"}:
            # Gaussian feathering must not leak static pixels back into either
            # animated pallet.  One source-pixel dilation also absorbs the
            # Lanczos fringe created during the registered downscale.
            carve = cv2.dilate(
                main_pallet_union.astype(np.uint8) * 255,
                np.ones((3, 3), np.uint8),
                iterations=1,
            )
            alpha[carve > 0] = 0
        destination = args.output_dir / f"chronophage-{name}-v3.webp"
        save_registered_layer(graded, alpha, destination)
        destinations[name] = destination

    # Bone sprites intentionally share photographed pixels in small circles at
    # the joints.  The torso mask above is still cut by their full union, so no
    # original complete leg can appear behind an animated one.
    for name in (*front.keys(), *rear.keys()):
        alpha = np.where((selections[name] > 0) & leg_material, subject_alpha, 0).astype(np.uint8)
        alpha[(wheel > 0) & (leg_luminance > 90)] = 0
        alpha = cv2.GaussianBlur(alpha, (0, 0), 0.34)
        destination = args.output_dir / f"chronophage-{name}-v3.webp"
        save_registered_layer(graded, alpha, destination)
        destinations[name] = destination

    for name, selection in (("front-pallet", front_union), ("rear-pallet", rear_union)):
        alpha = np.where((selection > 0) & leg_material, subject_alpha, 0).astype(np.uint8)
        alpha[(wheel > 0) & (leg_luminance > 90)] = 0
        alpha = cv2.GaussianBlur(alpha, (0, 0), 0.34)
        destination = args.output_dir / f"chronophage-{name}-v3.webp"
        save_registered_layer(graded, alpha, destination)
        destinations[name] = destination

    # Registered reconstruction: any double leg would be obvious here.
    complete = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    for name in ("passive", "rear-pallet", "torso", "jaw", "front-pallet"):
        with Image.open(destinations[name]) as layer:
            complete.alpha_composite(layer.convert("RGBA"))
    complete.save(
        args.output_dir / "chronophage-composite-v3.webp",
        "WEBP",
        lossless=True,
        method=6,
        exact=True,
    )
    checker = Image.new("RGBA", CANVAS_SIZE, (20, 24, 30, 255))
    tile = 32
    pixels = np.asarray(checker).copy()
    y_grid, x_grid = np.indices((CANVAS_SIZE[1], CANVAS_SIZE[0]))
    light = ((x_grid // tile + y_grid // tile) % 2) == 0
    pixels[light, :3] = (47, 53, 62)
    checker = Image.fromarray(pixels, "RGBA")
    checker.alpha_composite(complete)
    checker.convert("RGB").save(
        args.output_dir / "chronophage-qa-composite-v3.webp",
        "WEBP",
        lossless=True,
        method=6,
    )

    # Opaque extreme-background checks expose pale glass contamination on
    # white and hidden RGB / dark fringes on black.  Keep these deterministic
    # QA renders beside the checkerboard reconstruction.
    for qa_name, background in (
        ("black", (0, 0, 0, 255)),
        ("white", (255, 255, 255, 255)),
    ):
        qa = Image.new("RGBA", CANVAS_SIZE, background)
        qa.alpha_composite(complete)
        qa.convert("RGB").save(
            args.output_dir / f"chronophage-qa-{qa_name}-v3.webp",
            "WEBP",
            lossless=True,
            method=6,
        )
    save_mask_preview(labels, args.output_dir / "chronophage-mask-preview-v3.webp")
    save_rig_metadata(args.output_dir / "chronophage-rig-v3.json")
    build_v4(source, subject_alpha, graded, args.output_dir)


if __name__ == "__main__":
    main()
