---
title: "🚀 Hello World"
description: Four quick-start examples to run your first automation — Python script, macro recording, existing skill, and dashboard.
---

Here are four ways to get started with Ghost in the Droid. Each takes under 5 minutes.

## Option A: Python Script

The most direct way -- import the Device class and send commands.

```python
from gitd.bots.common.adb import Device

# Connect to device (auto-detects if only one connected)
dev = Device()

# Wake screen and go home
dev.adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
dev.adb("shell", "input", "keyevent", "KEYCODE_HOME")

# Open the Settings app
dev.adb("shell", "am", "start", "-n", "com.android.settings/.Settings")
import time; time.sleep(2)

# Read the screen's UI hierarchy
xml = dev.dump_xml()
print(f"Found {len(dev.nodes(xml))} UI elements")

# Find and tap an element by text
nodes = dev.find_nodes(xml, text="Network")
if nodes:
    dev.tap_node(nodes[0])
    print("Tapped!")
```

Save this as `hello.py` and run:

```bash
python3 hello.py
```

You should see the Settings app open on your phone and the "Network" item get tapped.

## Option B: Record and Replay a Macro

Record actions as you go, save to JSON, and replay later at any speed.

```python
from gitd.skills.macro_recorder import MacroRecorder, Macro
from gitd.bots.common.adb import Device

dev = Device()
recorder = MacroRecorder(dev)

# Start recording -- each method both records AND executes
recorder.start()
recorder.tap(540, 1200)                       # tap center-bottom
recorder.wait(1.0)                            # pause 1 second
recorder.swipe(540, 1800, 540, 600)           # swipe up
recorder.type_text("hello world")             # type text
recorder.back()                               # press back
macro = recorder.stop()                       # stop recording

# Save to file
macro.name = "my_first_macro"
macro.save("data/macros/my_first_macro.json")
print(f"Recorded {len(macro.steps)} steps in {macro.duration_s:.1f}s")

# Replay at 2x speed
loaded = Macro.load("data/macros/my_first_macro.json")
recorder.replay(loaded, speed=2.0)
```

The JSON format is human-readable and editable:

```json
{
  "name": "my_first_macro",
  "duration_s": 8.5,
  "step_count": 5,
  "steps": [
    {"action": "tap", "timestamp": 0.0, "params": {"x": 540, "y": 1200}},
    {"action": "wait", "timestamp": 0.5, "params": {"seconds": 1.0}},
    {"action": "swipe", "timestamp": 1.8, "params": {"x1": 540, "y1": 1800, "x2": 540, "y2": 600}},
    {"action": "type", "timestamp": 3.2, "params": {"text": "hello world"}},
    {"action": "back", "timestamp": 4.1, "params": {}}
  ]
}
```

## Option C: Run an Existing Skill

The TikTok skill ships pre-built with 13 actions and 9 workflows.

```python
from gitd.skills.tiktok import load
from gitd.bots.common.adb import Device

dev = Device()
skill = load()

# See what's available
print(skill.list_actions())
# ['open_app', 'navigate_to_profile', 'tap_search', 'type_and_search',
#  'dismiss_popup', 'like_post', 'comment_on_post', 'follow_user',
#  'scroll_feed', 'tap_user', 'tap_message_button', 'type_message', 'tap_send']

print(skill.list_workflows())
# ['upload_video', 'crawl_users', 'publish_draft']

# Run a single action (opens TikTok)
action = skill.get_action("open_app", dev)
result = action.run()
print(f"Success: {result.success}, took {result.duration_ms:.0f}ms")

# Run a workflow (upload a video)
wf = skill.get_workflow("upload_video", dev, video_path="/tmp/video.mp4")
result = wf.run()
print(result.data)  # {'completed_steps': 5}
```

Or run via the REST API:

```bash
# Start the server first
python3 run.py &

# Execute a workflow via curl
curl -X POST http://localhost:5055/api/skills/tiktok/run \
  -H "Content-Type: application/json" \
  -d '{"workflow": "upload_video", "params": {"video_path": "/tmp/video.mp4"}, "device": "YOUR_DEVICE_SERIAL"}'
```

## Option D: Use the Dashboard

The visual way -- no code required.

1. Start the server:
   ```bash
   python3 run.py
   ```

2. Open http://localhost:5055 in your browser

3. Navigate to the **Phone Agent** tab to verify your device shows up and the live stream works

4. Go to the **Skill Hub** tab to browse installed skills, pick a workflow, select your device, and click **Run**

5. Check the **Scheduler** tab to see the job running on the 24-hour timeline

### Dashboard Tabs Overview

| Tab | What You Can Do |
|-----|----------------|
| **Bot** | Quick-launch crawl and post jobs |
| **Scheduler** | View 24h timeline, create scheduled jobs |
| **Phone Agent** | Live device stream, tap/type controls |
| **Skill Hub** | Browse and run skills |
| **Skill Creator** | Build new skills with LLM assistance |
| **Explorer** | Discover app UI states automatically |

## What's Next?

Now that you have automation running, dive deeper:

- [TikTok Upload Guide](/guides/tiktok-upload/) -- the full 43-step video upload pipeline
- [Macros Guide](/guides/macros/) -- advanced macro recording and editing
- [Stealth Mode](/guides/stealth/) -- avoid bot detection
