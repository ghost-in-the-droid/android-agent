---
title: "🥷 Stealth Mode"
description: Three stealth methods on the Device class — Gaussian tap jitter, variable-speed swipes, and character-by-character typing.
---

Stealth mode provides human-like interaction simulation to reduce bot detection risk. It adds randomization to the three most detectable ADB operations: taps, swipes, and typing.

## The Three Methods

### stealth_tap(x, y, delay=0.6)

Adds Gaussian jitter to tap coordinates. With sigma=8, 68% of taps land within +/-8px and 95% within +/-16px of the target.

```python
def stealth_tap(self, x, y, delay=0.6):
    jx = x + random.gauss(0, 8)   # sigma=8
    jy = y + random.gauss(0, 8)
    self.tap(int(jx), int(jy), delay=delay)
```

### stealth_swipe(x1, y1, x2, y2, ms=None, delay=0.5)

Variable swipe speed (300-700ms instead of fixed 500ms) with smaller endpoint jitter (sigma=5).

```python
def stealth_swipe(self, x1, y1, x2, y2, ms=None, delay=0.5):
    ms = ms or random.randint(300, 700)
    jx1 = x1 + random.gauss(0, 5)
    jy1 = y1 + random.gauss(0, 5)
    jx2 = x2 + random.gauss(0, 5)
    jy2 = y2 + random.gauss(0, 5)
    self.swipe(int(jx1), int(jy1), int(jx2), int(jy2), ms=ms, delay=delay)
```

### stealth_type(text, delay_range=(0.05, 0.2))

Types each character individually with random inter-keystroke delays of 50-200ms.

```python
def stealth_type(self, text, delay_range=(0.05, 0.2)):
    for char in text:
        self.adb("shell", "input", "text", char)
        time.sleep(random.uniform(*delay_range))
```

## How They Work

The stealth methods are thin wrappers that add noise, then delegate to the standard Device methods. No state is maintained between calls -- each invocation independently samples from the random distribution.

```
Caller: d.stealth_tap(540, 1200)
    |
    v
Apply Gaussian jitter: x += gauss(0, 8), y += gauss(0, 8)
    |
    v
d.tap(jittered_x, jittered_y)
    |
    v
adb shell input tap <x> <y>
```

## Additional Stealth in the Codebase

Beyond the three explicit methods, other components apply their own randomization:

| Component | Technique |
|-----------|-----------|
| Outreach bot | Random DM delay: `uniform(45, 75)` seconds |
| Engage bot | Randomized watch times (3-15s), jittered coordinates |
| Upload bot | Strips non-ASCII to avoid IME detection |
| All bots | Variable `time.sleep()` between actions |

## Detection Vectors

| Vector | Addressed | Risk |
|--------|-----------|------|
| Pixel-perfect coordinates | Yes (Gaussian jitter) | Low |
| Uniform tap timing | Partially (delay param is per-call) | Medium |
| Linear swipe paths | No (endpoints jittered but path is linear) | High |
| IME switching detection | Mitigated (quick switch-back) | Medium |
| `Settings.Secure.DEFAULT_INPUT_METHOD` | Known risk, deferred | Medium |
| USB debugging enabled | Cannot address in software | Low |

## Limitations

- Not auto-applied -- you must explicitly call `stealth_*` methods
- No Bezier curve swipe paths
- No per-session randomization profiles (same parameters every run)
- The engage bot has its own jitter logic rather than using these methods

## Related

- [Stealth Guide](/guides/stealth/) -- practical usage, daily limits, best practices
- [ADB Device](/features/adb-device/) -- all 47+ Device methods
