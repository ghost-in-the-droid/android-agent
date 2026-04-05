---
title: "🎯 Elements & Locators"
description: UI locator chains, fallback priority, finding elements on screen, and elements.yaml format reference.
---

Elements are named UI locators that identify interactive controls on the screen. They are the foundation of the skill system -- every action that interacts with the UI uses elements to find where to tap, type, or swipe.

## Why Elements?

App updates change resource IDs, rearrange layouts, and rename buttons. Hardcoded coordinates break immediately. Elements solve this with **fallback chains** -- multiple locator strategies tried in priority order:

```
content_desc -> text -> resource_id -> class_name -> absolute coords (x, y)
```

If `content_desc` fails, the system tries `text`. If that fails, it tries `resource_id`, and so on. This makes skills resilient to minor app updates.

## elements.yaml Format

```yaml
# gitd/skills/tiktok/elements.yaml
package: com.zhiliaoapp.musically
app_version: "44.3.3"

elements:
  search_icon:
    resource_id: "com.zhiliaoapp.musically:id/j4d"
    content_desc: "Search"
    description: "Home screen search magnifier"

  search_box:
    resource_id: "com.zhiliaoapp.musically:id/gti"
    class_name: "android.widget.EditText"
    description: "Search text input field"

  profile_tab:
    resource_id: "com.zhiliaoapp.musically:id/n19"
    text: "Profile"
    content_desc: "Profile"
    description: "Bottom nav Profile icon"

  follow_button:
    text: "Follow"
    content_desc: "Follow"
    description: "Follow button on user profile"
    x: 540
    y: 650
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `resource_id` | string | Android resource ID (e.g., `com.app:id/btn1`) |
| `content_desc` | string | Accessibility content description |
| `text` | string | Visible text label |
| `class_name` | string | Android widget class (e.g., `android.widget.Button`) |
| `x`, `y` | int | Absolute coordinates (last resort fallback) |
| `description` | string | Human-readable description (not used for finding) |

## How Element.find() Works

```python
element = skill.elements["search_icon"]
coords = element.find(device, xml)
# Returns (cx, cy) tuple or None
```

The `find()` method tries each locator in priority order:

1. **content_desc** -- `find_bounds(xml, content_desc="Search")`
2. **text** -- `find_bounds(xml, text="Search")`
3. **resource_id** -- `find_bounds(xml, resource_id="com.app:id/j4d")`
4. **class_name** -- `find_bounds(xml, resource_id="android.widget.EditText")` (uses same lookup)
5. **Absolute coords** -- returns `(x, y)` directly if defined

The first match wins. Bounds are converted to center coordinates automatically.

## Finding Elements on Screen

### Method 1: Skill Creator Overlay

The fastest way. Open the **Skill Creator** tab in the dashboard, start the WebRTC stream, and the element overlay will show numbered labels on every interactive element. Click a number to copy its locator info.

### Method 2: XML Dump

```python
from gitd.bots.common.adb import Device
dev = Device()
xml = dev.dump_xml()

# Print all elements with identifying info
for node in dev.nodes(xml):
    rid = dev.node_rid(node)
    text = dev.node_text(node)
    desc = dev.node_content_desc(node)
    bounds = dev.node_bounds(node)
    if rid or text or desc:
        print(f"RID: {rid:40s}  text: {text:20s}  desc: {desc:20s}  bounds: {bounds}")
```

### Method 3: Interactive Element Endpoint

```bash
curl -s http://localhost:5055/api/phone/elements/YOUR_DEVICE_SERIAL | python3 -m json.tool
```

Returns a numbered list of interactive elements currently on screen, including bounds, text, resource_id, and content_desc.

### Method 4: RID Discovery Tool

For systematic RID extraction after an app update:

```python
from gitd.bots.common.discover_rids import discover
discover(device_serial="YOUR_DEVICE_SERIAL", package="com.zhiliaoapp.musically")
```

This saves a JSON map of all RIDs found on each screen to `bots/common/rid_maps/`.

## Element Resolution in the TikTok Skill

The TikTok skill has **41 defined elements** covering:

- Bottom navigation (Home, Discover, Camera, Inbox, Profile)
- Search UI (icon, input box, tabs, filters)
- Video player (like, comment, share, follow)
- Profile page (followers, following, edit, message)
- Upload flow (next button, caption input, hashtag area, post/draft buttons)
- DM interface (message input, send button)
- Popups and overlays (10+ known patterns)

## RID Maps

Version-specific resource ID maps are stored in `bots/common/rid_maps/`:

```
rid_maps/
  tiktok_44.3.3.json
```

When TikTok updates, RIDs change. The `discover_rids.py` tool helps extract new RIDs by comparing XML dumps against known patterns. The Skill Creator's element overlay is also useful for this.

## Best Practices

1. **Always provide multiple locators** -- at minimum, `resource_id` + one of `content_desc`/`text`
2. **Add absolute coords as last resort** -- useful for elements that have no stable identifiers
3. **Use description for documentation** -- helps other developers understand what the element is
4. **Test on multiple devices** -- resource IDs are consistent across devices for the same app version, but screen coordinates differ
5. **Version your elements.yaml** -- include the `app_version` field to track which version the RIDs were extracted from

## Related

- [Creating Skills](/skills/creating-skills/) -- full skill creation walkthrough
- [Skill System](/features/skill-system/) -- Action/Workflow/Element class APIs
- [ADB Device](/features/adb-device/) -- dump_xml, find_bounds, and other XML methods
