# Testing Guide

---

## API Smoke Tests (no device needed)

```bash
# Run all 32 API smoke tests
pytest tests/api/test_smoke.py -v --tb=short
```

These test every router with a FastAPI `TestClient` -- no phone required. They verify 200 OK responses and basic JSON shape for all endpoints.

---

## Device Integration Tests (phone required)

```bash
# Run all tests on a specific device
DEVICE=<serial> python3 -m pytest tests/ -v --tb=short

# Run a single test file
DEVICE=<serial> python3 -m pytest tests/test_04_crawl.py -v

# Run a single test function
DEVICE=<serial> python3 -m pytest tests/test_04_crawl.py::test_crawl_top -v
```

Get your device serial from `adb devices`.

### Test Suite

| File | What It Does | Requires |
|------|-------------|----------|
| `test_00_baseline` | Verify correct TikTok account | TikTok logged in |
| `test_01_accounts` | Account switching round-trip | 2+ TikTok accounts |
| `test_02_draft` | Upload video as draft | Video in `data/vertical_videos/` |
| `test_03_post` | Post publicly (skipped by default) | Video + willingness to post |
| `test_04_crawl` | Scrape profiles by hashtag | TikTok search access |
| `test_08_draft_publish` | Draft to published transition | Existing draft |

Parallel execution across different phones is safe (separate terminals, different `DEVICE` values). Do NOT run multiple tests on the same phone -- they share app state.

---

## Frontend Checks

```bash
cd frontend
npx vue-tsc --noEmit       # TypeScript type checking
npx vite build              # Production build (catches import errors)
```

---

## Linting

```bash
ruff check gitd/routers/ gitd/schemas/ gitd/services/ gitd/models/ gitd/app.py
ruff format --check gitd/routers/ gitd/schemas/ gitd/services/ gitd/models/ gitd/app.py
```

---

## CI (GitHub Actions)

The `.github/workflows/ci.yml` pipeline runs on every push and PR to `main`:

1. **lint** -- `ruff check` + `ruff format --check` on routers, schemas, services, models, app.py
2. **test** -- `pytest tests/api/test_smoke.py` (32 API smoke tests, no device)
3. **build-frontend** -- `npm ci` + `vue-tsc --noEmit` + `vite build`
4. **type-check** -- verify all FastAPI routes load without import errors

---

## Dashboard Test Runner

The **Tests** tab in the Vue dashboard provides a GUI for device tests:

1. Open `http://localhost:6175` > Tests tab
2. Select device from dropdown
3. Check tests to run
4. Click **Run** -- live log streaming shows progress
5. View screen recordings in the Recordings library

---

## Writing Tests

```python
def test_something(dev):
    # Start from known state
    dev.restart_tiktok()

    # Act
    xml = dev.dump_xml()
    dev.tap_text(xml, "Search")

    # Assert
    xml = dev.dump_xml()
    assert dev.screen_type(xml) == "search_input"
```

Tips:
- Use `dev.wait_for(text, timeout=12)` instead of `time.sleep()`
- Call `dev.dismiss_popups()` after navigation
- Resource IDs change between app versions -- use text matching as fallback
