---
title: "🥷 Stealth Mode"
description: Human-like interaction simulation — stealth_tap, stealth_swipe, stealth_type, timing randomization, and detection vectors.
---

Stealth mode adds randomization to ADB interactions so automated actions look more like human input. This reduces the risk of bot detection by apps like TikTok and Instagram.

## Why Stealth Matters

Standard ADB commands produce perfectly uniform input:

- **Taps** always land on exact pixel coordinates
- **Swipes** always take exactly 500ms at constant speed
- **Typing** appears instantly (entire string in one frame)

Apps can detect these patterns by monitoring input event timing, coordinate precision, and keystroke intervals. Stealth mode introduces noise to match human behavior.

## Three Stealth Methods

### stealth_tap(x, y)

Adds Gaussian jitter to tap coordinates.

```python
from gitd.bots.common.adb import Device
dev = Device()

# Standard tap -- always hits (540, 1200) exactly
dev.tap(540, 1200)

# Stealth tap -- hits near (540, 1200) with Gaussian noise
dev.stealth_tap(540, 1200)
```

**How it works:** Both X and Y are offset by `random.gauss(0, 8)`. With sigma=8, 68% of taps land within +/-8px of the target, and 95% within +/-16px.

```python
# Implementation
def stealth_tap(self, x, y, delay=0.6):
    jx = x + random.gauss(0, 8)
    jy = y + random.gauss(0, 8)
    self.tap(int(jx), int(jy), delay=delay)
```

### stealth_swipe(x1, y1, x2, y2)

Adds endpoint jitter and variable swipe speed.

```python
# Standard swipe -- always exactly 500ms
dev.swipe(540, 1400, 540, 800)

# Stealth swipe -- 300-700ms duration, jittered endpoints
dev.stealth_swipe(540, 1400, 540, 800)
```

**How it works:**
- Duration randomized from 300-700ms (vs fixed 500ms)
- Start and end coordinates jittered by `random.gauss(0, 5)` (smaller sigma than taps)

```python
def stealth_swipe(self, x1, y1, x2, y2, ms=None, delay=0.5):
    ms = ms or random.randint(300, 700)
    jx1 = x1 + random.gauss(0, 5)
    jy1 = y1 + random.gauss(0, 5)
    jx2 = x2 + random.gauss(0, 5)
    jy2 = y2 + random.gauss(0, 5)
    self.swipe(int(jx1), int(jy1), int(jx2), int(jy2), ms=ms, delay=delay)
```

### stealth_type(text)

Types each character individually with random delays between keystrokes.

```python
# Standard type -- entire string appears instantly
dev.type_text("hello world")

# Stealth type -- h...e...l...l...o with 50-200ms between each
dev.stealth_type("hello world")

# Custom delay range (slower, more cautious)
dev.stealth_type("important text", delay_range=(0.1, 0.4))
```

**How it works:** Each character is sent via `adb shell input text <char>` with a `random.uniform(0.05, 0.2)` second pause between characters.

## Additional Stealth Behaviors

Beyond the three explicit stealth methods, the system applies randomization in other places:

| Component | Randomization |
|-----------|--------------|
| **Outreach bot** | Random delay between DMs: `uniform(45, 75)` seconds |
| **Engage bot** | Randomized watch times (3-15s per video), jittered tap coordinates |
| **Upload bot** | Strips non-ASCII text to avoid IME detection patterns |
| **All bots** | Variable `time.sleep()` delays between actions |

## Using Stealth in Your Code

Replace standard Device methods with their stealth counterparts:

```python
from gitd.bots.common.adb import Device
dev = Device()

# Before (detectable):
dev.tap(540, 1200)
dev.swipe(540, 1400, 540, 800)
dev.type_text("hello")

# After (stealthy):
dev.stealth_tap(540, 1200)
dev.stealth_swipe(540, 1400, 540, 800)
dev.stealth_type("hello")
```

## Daily Limits

To reduce the risk of account flagging, implement daily limits for all automated actions:

```bash
# Crawling: limit scroll passes to avoid rate limits
python3 -m gitd.bots.tiktok.scraper "#Cat" --passes 5
```

## Detection Vectors

| Vector | Status | Risk Level |
|--------|--------|------------|
| Coordinate precision (pixel-perfect taps) | Mitigated by stealth_tap jitter | Low |
| Uniform tap timing | Not fully addressed (delay param is fixed per call) | Medium |
| Linear swipe paths (no curve) | Endpoints jittered, but path is still linear | High |
| IME switching (ADBKeyboard) | Mitigated by quick switch-back to Gboard | Medium |
| `Settings.Secure.DEFAULT_INPUT_METHOD` readable by apps | Known risk, deferred | Medium |
| USB debugging enabled | Not addressable via software | Low |
| `input` command visible in process list | Not addressable via software | Low |

## Best Practices

1. **Use stealth methods for all production automation** -- never use raw `tap`/`swipe`/`type_text` on live accounts
2. **Vary session duration** -- don't run for exactly the same time every day
3. **Randomize scheduling** -- stagger job start times by +/-15 minutes
4. **Warm up accounts** -- run a few manual sessions before starting automation
5. **Monitor account health** -- check for shadowban indicators regularly
6. **One account per device** -- don't switch accounts rapidly on the same phone

## Related

- [Phone Farm](/guides/phone-farm/) -- multi-device setup for spreading load
- [Scheduler](/features/scheduler/) -- schedule jobs with randomized timing
- [ADB Device](/features/adb-device/) -- all 47+ Device methods
