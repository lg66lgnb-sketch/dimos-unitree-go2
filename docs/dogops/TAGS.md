# DogOps Demo Tags

DogOps uses AprilTag 36h11 IDs with `marker_length_m: 0.14`.

| Tag ID | Entity | Type | Demo role |
|---:|---|---|---|
| 10 | HOME | zone | Home / NOC start |
| 20 | INBOUND_DOCK | zone | Receiving scan |
| 30 | QA_HOLD | zone | Corrective package zone |
| 40 | RACK_ROW_A | zone | Rack row / SiteOps area |
| 41 | COOLING_1 | asset | P1 cooling clearance |
| 42 | AISLE_1 | asset | Aisle clearance |
| 43 | TEMP_1 | asset | Optional manual temperature station |
| 50 | NO_GO_1 | zone | No-go maintenance area |
| 60 | DOCK_1 | dock | Dock-alignment stretch |
| 70 | PORTAL_1 | portal | Portal/elevator-entry stretch |
| 101 | PKG-101 | package | Expected inbound package |
| 102 | PKG-102 | package | Expected inbound package |
| 103 | PKG-103 | package | Missing/open package |
| 104 | PKG-104 | package | Wrong-zone package blocking `COOLING_1` |

Print large, flat, high-contrast tags. Keep a white margin around each marker; the generated-marker detector smoke test also requires a white border for reliable detection.

For the real Go2, mount tags vertically near camera height or slightly angled toward the robot. Avoid floor-only tags, glossy tape, and small labels. If detection is weak, reduce distance before increasing mission complexity.
