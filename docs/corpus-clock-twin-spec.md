# Corpus Clock digital-twin acceptance spec

This document is the visual and mechanical baseline for the header clock. It is deliberately stricter than “an animated illustration”: the rendered parts must have the same causal relationships as the public mechanism.

## Primary references

- US patent US8218400B2, especially FIG. 2, FIG. 3, FIG. 9-1 and FIG. 9-2.
- University of Cambridge unveiling description.
- `Chronophage pol.jpg` (Rror, CC BY-SA 3.0) as the single photographic texture master.
- `Corpus clock, Cambridge.ogv` (Magnus Manske, CC BY-SA 3.0) as the motion reference.

## Geometry

- One strictly frontal, circular dial. A rectified isolated metal texture is
  allowed, but no perspective, glass cabinet, masonry or visitors may remain
  in the runtime artwork.
- Escape wheel: 60 identical, visibly separated, backward-swept teeth around a fixed pitch circle.
- Fixed time apertures: 60 seconds, 60 minutes and 48 inner positions. Every fourth inner aperture is the longer hour position; the other three are quarter-hour positions.
- The Chronophage faces left. Its body is approximately the wheel width and sits on the top arc, with both pallet faces visibly meeting tooth valleys.
- The photographic layers share one registration canvas. Active pallets must be absent from the torso layer so no baked or ghost limb remains.

## Escapement causality

- The wheel is driven by stored spring torque, not by a free-running CSS rotation.
- A pallet in `locked` state prevents wheel movement.
- During `release`, the releasing pallet clears the tooth and the spring accelerates the wheel clockwise.
- During `follow`, the other pallet face stays near the pitch circle while the wheel advances.
- During `catch`, the receiving pallet collides with the next tooth, stops it and permits a small counter-clockwise recoil.
- The wheel advances exactly one tooth (6 degrees) per elapsed second and completes one carrier cycle every two seconds.
- Pallet pose is solved from its joint and the selected tooth contact point. The wheel and pallet must not merely read the same decorative animation variable.
- Except for the short hand-over overlap, at least one pallet must be engaged. There must never be a visible frame with both feet floating away from the teeth.

## Motion and time display

- All office-facing time indices are derived explicitly from `Asia/Shanghai` (Beijing time), never from the browser's local timezone.
- Dial metal remains physically stationary. Only the escape-wheel teeth and hidden shutter/light states move.
- Normal slit states are dark bronze cavities with a machined gold bevel. Active light is localized ice blue, never a full-disc blue wash.
- The public clock's deliberately irregular five-minute behaviour is represented as a faithful simulation, not described as an unpublished exact reconstruction.
- Jaw, blink, tail and pendulum motion remain secondary to the escapement and cannot obscure the contact point.
- `prefers-reduced-motion` preserves discrete accurate time updates while removing interpolated bounce and flourish.

## Visual QA gates

- Compare at least 20 evenly spaced frames across one two-second escapement cycle against the motion reference.
- At desktop size (160 px wide), a single 6-degree tooth step must be visible without zooming; at mobile size, individual tooth valleys remain separated.
- Review both a full-page screenshot and a 4× clock crop after every material iteration.
- No bright vector guide, contact debug marker, mask seam, old wheel fragment, rectangular photo edge or doubled limb may remain in the user-facing render.
- Reload, background-tab resume and the 59-to-00 second wrap must not reverse or skip the escape wheel.
- Clock changes must not regress the work-session timer, reminders, Codex completion counts or work-log export.
