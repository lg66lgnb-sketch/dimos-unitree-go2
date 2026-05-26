# SAFETY.md

## Demo safety rules

- Treat the real Go2 as available but not disposable. Safety beats autonomy claims.
- Keep route short and open.
- Keep robot speed low.
- Use `Nudge` or `Step` before `Walk`; only use `Walk` when the surrounding area is clear.
- Keep people out of the robot path except the planned remediation moment.
- Do not let barrier tape/cones create trip hazards.
- Do not make the robot push boxes or obstacles.
- Human moves `PKG-104`; robot only observes and verifies.
- Keep cables/power banks away from robot feet.
- Always know how to run `uv run dimos stop --force`.
- Verify base `unitree-go2` before running `unitree-go2-dogops`.
- Treat dashboard motion as verified only when odometry reports observed distance/yaw.
- If navigation becomes unstable, stop, switch to guided mode, and record that fallback honestly.

## Emergency commands

```bash
uv run dimos stop --force || true
```

If robot state is unsafe, use the official Unitree/DimOS stop procedure from event staff.

## Live demo safety copy

> The robot does not manipulate obstacles. It creates work orders, waits for a human to remediate, then verifies closure. This is safer and closer to how industrial facilities actually deploy robots.
