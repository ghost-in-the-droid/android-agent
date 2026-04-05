# Stealth Mode — Feature Summary

## What It Does

Human-like interaction simulation to reduce bot detection risk on Android apps. Provides three methods on the `Device` class that add randomization to taps (Gaussian coordinate jitter), swipes (variable speed + endpoint jitter), and typing (character-by-character with random inter-keystroke delays). These methods wrap the standard ADB input commands with noise to avoid the perfectly uniform timing and pixel-perfect coordinates that characterize automated input.

## Current State

**Working (3 methods on Device class):**

| Method | Randomization Applied |
|--------|----------------------|
| `stealth_tap(x, y)` | Gaussian jitter: both X and Y offset by `gauss(0, 8)` (~95% within +/-16px) |
| `stealth_swipe(x1, y1, x2, y2)` | Start/end coords jittered by `gauss(0, 5)`, duration randomized 300-700ms |
| `stealth_type(text)` | Each character typed individually with `uniform(0.05, 0.2)` second delay |

**Additional stealth-related behaviors in the codebase:**
- Bot scripts use randomized watch times and jittered tap coordinates
- Upload bot strips non-ASCII from text to avoid IME detection patterns
- All bots use `time.sleep()` between actions with variable delays

**Limitations:**
- Not auto-applied — caller must explicitly use `stealth_*` instead of `tap`/`swipe`/`type_text`
- No Bezier curve paths for swipes (uses linear movement with jittered endpoints)
- No per-session randomization profiles (same jitter parameters every run)
- Some bot scripts have their own jitter logic, not using these stealth methods
- No scroll speed variation (swipes always use `input swipe` which is linear)

## Architecture

```
Caller code (bot scripts)
    │
    │  d.stealth_tap(540, 1200)
    ▼
Device.stealth_tap()
    │  Apply Gaussian jitter: x += gauss(0, 8), y += gauss(0, 8)
    │  Clamp to int
    ▼
Device.tap(jittered_x, jittered_y)
    │
    ▼
adb shell input tap <x> <y>
```

The stealth methods are thin wrappers — they add noise then delegate to the standard Device methods. No state is maintained between calls (each invocation independently samples from the random distribution).

## Files

| File | Purpose |
|------|---------|
| `gitd/bots/common/adb.py` | `stealth_tap`, `stealth_swipe`, `stealth_type` (lines 174-200) |

## Code Details

```python
def stealth_tap(self, x, y, delay=0.6):
    """Tap with Gaussian jitter on coordinates (+/-5-15px) to appear human."""
    import random
    jx = x + random.gauss(0, 8)   # sigma=8 → 68% within +/-8px, 95% within +/-16px
    jy = y + random.gauss(0, 8)
    self.tap(int(jx), int(jy), delay=delay)

def stealth_swipe(self, x1, y1, x2, y2, ms=None, delay=0.5):
    """Swipe with variable speed and slight endpoint jitter."""
    import random
    ms = ms or random.randint(300, 700)       # 300-700ms duration (vs fixed 500ms)
    jx1 = x1 + random.gauss(0, 5)            # smaller sigma for swipe endpoints
    jy1 = y1 + random.gauss(0, 5)
    jx2 = x2 + random.gauss(0, 5)
    jy2 = y2 + random.gauss(0, 5)
    self.swipe(int(jx1), int(jy1), int(jx2), int(jy2), ms=ms, delay=delay)

def stealth_type(self, text, delay_range=(0.05, 0.2)):
    """Type character-by-character with random delays between keystrokes."""
    import random
    for char in text:
        self.adb("shell", "input", "text", char)
        time.sleep(random.uniform(*delay_range))   # 50-200ms per char
```

## How to Use

```python
from gitd.bots.common.adb import Device
d = Device('YOUR_DEVICE_SERIAL')

# Instead of d.tap(540, 1200):
d.stealth_tap(540, 1200)      # taps near (540, 1200) with Gaussian noise

# Instead of d.swipe(...):
d.stealth_swipe(540, 1400, 540, 800)  # variable speed + jittered coords

# Instead of d.type_text("hello"):
d.stealth_type("hello")       # h...e...l...l...o with 50-200ms between each

# Custom delay range for slower typing
d.stealth_type("careful text", delay_range=(0.1, 0.4))
```

## Detection Vectors Not Yet Addressed

| Vector | Status | Risk Level |
|--------|--------|------------|
| Coordinate precision (always on pixel boundaries) | Jitter applied | Low |
| Uniform tap timing | Not addressed (delay param is fixed per call) | Medium |
| Linear swipe paths (no curve) | Midpoint offset computed but not used | High |
| IME switching (ADBKeyboard detection) | Mitigated by quick switch-back | Medium |
| `Settings.Secure.DEFAULT_INPUT_METHOD` readable by apps | Known risk, deferred | Medium |
| USB/ADB debugging enabled | Not addressable via software | Low |
| `input` command in process list | Not addressable | Low |

## Known Issues & TODOs

- [ ] Bezier curve swipe paths (smooth arcs instead of linear `input swipe`)
- [ ] Perlin noise for more natural coordinate variation over time
- [ ] Auto-stealth mode (monkey-patch Device to route all tap/swipe/type through stealth)
- [ ] Per-session randomization profiles (vary jitter sigma, delay ranges each run)
- [ ] Migrate bot scripts to use Device.stealth_* instead of their own jitter
- [ ] Inter-action timing randomization (vary the `delay` param itself)
- [ ] Touch pressure/size variation (requires `sendevent` instead of `input tap`)
- [ ] Screen-off detection before actions (avoid tapping while screen is locked)
