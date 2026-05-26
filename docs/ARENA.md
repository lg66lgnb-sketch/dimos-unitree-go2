# ARENA.md

## Goal

Set up an indoor/office arena that makes DogOps look like a real SiteOps product while remaining safe and reliable for the real Go2. Use 10 m x 10 m if available, but prefer a shorter 3 m x 5 m route if it makes the live run more repeatable.

## Core layout

```text
+------------------------------------------------+
|                                                |
|  [HOME/NOC]                                    |
|      Tag 10                                    |
|                                                |
|           -> route lane                        |
|                                                |
|  [INBOUND_DOCK]          [RACK_ROW_A]          |
|   Tags 20, 101,102       Tag 40                |
|   boxes/packages         [COOLING_1] Tag 41    |
|                          PKG-104 blocks vent   |
|                                                |
|  [QA_HOLD] Tag 30        [NO_GO_1] Tag 50      |
|   correction zone        tape + cones          |
|                                                |
|  Optional: [DOCK_1] Tag 60   [PORTAL_1] Tag 70 |
+------------------------------------------------+
```

## Minimum physical setup

1. HOME/NOC station with Tag 10.
2. INBOUND_DOCK station with Tag 20 and packages Tag 101, 102.
3. RACK_ROW_A / COOLING_1 station with Tag 40/41 and a fake cooling vent.
4. Put `PKG-104` near/on the cooling vent to create the P1 incident.
5. Leave `PKG-103` absent for the missing-package exception.
6. QA_HOLD station with Tag 30 where the human moves `PKG-104`.
7. Optional no-go zone with tape/cones and Tag 50.

## Tag mounting

- Mount tags vertically, not flat on the floor.
- Put tags roughly at Go2 camera height or angled toward camera.
- Use boxes/clamps for adjustable height.
- Use big human-readable labels above tags.
- Keep tag backgrounds plain and high contrast.
- Avoid glossy reflections.

## Route design

- Keep the 90-second route short.
- Use wide lanes.
- Avoid tight turns near boxes.
- Keep robot speed low.
- Start with guided mode if autonomous navigation is not stable yet.
- Keep humans out of robot path except the remediation action.
- Make the human fix obvious: pick up `PKG-104` and move it to `QA_HOLD`.
- Do not make the robot push or nudge props.

## Demo prop labels

Use sticky A4 paper:

```text
HOME / NOC
INBOUND DOCK
QA HOLD
RACK ROW A
COOLING_1 — critical airflow clearance
NO_GO_1 — maintenance zone
PKG-101
PKG-102
PKG-104 — wrong zone
```

## Camera visibility test

Before full demo:

1. Put Go2 at expected inspection distance.
2. Open camera/Rerun if available.
3. Verify tags fill enough pixels.
4. If not visible, raise/tilt tags, increase size, or reduce distance.

## Live fallback setup

Prepare a smaller layout for failure recovery:

```text
HOME -> INBOUND_DOCK -> COOLING_1 -> QA_HOLD
```

This can fit in 3 m × 5 m and still proves the product loop.
