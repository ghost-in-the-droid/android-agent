"""
Gmail inbox utilities — open Gmail and scrape inbox entries via ADB.

Usage:
    from gitd.skills.gmail_utils import check_gmail_inbox_most_recent

    entries = check_gmail_inbox_most_recent(max_entries=10)
    for e in entries:
        print(f"{e['sender']}  |  {e['subject']}  |  {e['date']}")
"""
from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional


GMAIL_PKG = "com.google.android.gm"

# Gmail resource IDs (verified on Samsung SM-A156B, Gmail 2025+)
RID_SENDERS = f"{GMAIL_PKG}:id/senders"
RID_DATE    = f"{GMAIL_PKG}:id/date"
RID_SUBJECT = f"{GMAIL_PKG}:id/subject"
RID_SNIPPET = f"{GMAIL_PKG}:id/snippet"


@dataclass
class GmailEntry:
    sender: str
    subject: str
    date: str
    snippet: str
    is_unread: bool = False

    def __repr__(self):
        flag = " [UNREAD]" if self.is_unread else ""
        return f"<{self.sender} | {self.subject} | {self.date}{flag}>"


def _adb(serial: str, *args, timeout: int = 15) -> str:
    r = subprocess.run(
        ["adb", "-s", serial, *args],
        capture_output=True, text=True, timeout=timeout,
    )
    return r.stdout.strip()


def _dump_xml(serial: str) -> str:
    """Dump UI XML via uiautomator (reliable on all devices)."""
    _adb(serial, "shell", "uiautomator", "dump", "/sdcard/gmail_dump.xml")
    return _adb(serial, "exec-out", "cat", "/sdcard/gmail_dump.xml")


def _launch_gmail(serial: str, wait: float = 5.0):
    """Force-stop and relaunch Gmail to inbox."""
    _adb(serial, "shell", "am", "force-stop", GMAIL_PKG)
    time.sleep(0.5)
    _adb(serial, "shell", "am", "start",
         "-n", f"{GMAIL_PKG}/.ConversationListActivityGmail",
         "-a", "android.intent.action.MAIN",
         "-c", "android.intent.category.LAUNCHER")
    time.sleep(wait)


def _parse_inbox_entries(xml_str: str, max_entries: int = 20) -> list[GmailEntry]:
    """Parse Gmail inbox XML and extract email entries."""
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return []

    entries = []

    # Collect all nodes by resource-id
    senders = []
    dates = []
    subjects = []
    snippets = []
    conversation_frames = []

    for node in root.iter("node"):
        rid = node.get("resource-id", "")
        text = node.get("text", "")

        if rid == RID_SENDERS and text:
            # Clean up sender (remove non-breaking spaces, message counts)
            clean = text.replace("\xa0", " ").strip()
            senders.append(clean)
        elif rid == RID_DATE and text:
            dates.append(text.strip())
        elif rid == RID_SUBJECT and text:
            subjects.append(text.strip())
        elif rid == RID_SNIPPET and text:
            # Clean up snippet (remove zero-width spaces)
            clean = text.replace("\u200c", "").strip()
            snippets.append(clean)

        # Detect conversation frame containers for unread status
        if node.get("class", "") == "android.widget.FrameLayout":
            frame_text = text or ""
            if "Unread" in frame_text:
                conversation_frames.append(True)
            elif rid == "" and ("," in frame_text) and len(frame_text) > 20:
                conversation_frames.append(False)

    # Zip them together (they appear in order in the XML)
    count = min(len(senders), len(subjects), len(dates), max_entries)

    for i in range(count):
        is_unread = conversation_frames[i] if i < len(conversation_frames) else False
        entries.append(GmailEntry(
            sender=senders[i],
            subject=subjects[i],
            date=dates[i],
            snippet=snippets[i] if i < len(snippets) else "",
            is_unread=is_unread,
        ))

    return entries


def check_gmail_inbox_most_recent(
    device_serial: str = "",
    max_entries: int = 10,
    relaunch: bool = True,
    scroll_passes: int = 0,
) -> list[GmailEntry]:
    """Open Gmail on device and return most recent inbox entries.

    Args:
        device_serial: ADB device serial
        max_entries: Max entries to return
        relaunch: If True, force-restart Gmail to inbox (ensures fresh state)
        scroll_passes: Number of scroll-down passes to load more emails (0 = just visible)

    Returns:
        List of GmailEntry with sender, subject, date, snippet, is_unread
    """
    if relaunch:
        _launch_gmail(device_serial)

    all_entries = []
    seen_subjects = set()

    for pass_idx in range(scroll_passes + 1):
        xml_str = _dump_xml(device_serial)
        entries = _parse_inbox_entries(xml_str, max_entries=max_entries)

        for e in entries:
            key = (e.sender, e.subject, e.date)
            if key not in seen_subjects:
                seen_subjects.add(key)
                all_entries.append(e)

        if len(all_entries) >= max_entries:
            break

        if pass_idx < scroll_passes:
            # Scroll down to load more
            _adb(device_serial, "shell", "input", "swipe", "360", "1200", "360", "400", "500")
            time.sleep(2)

    return all_entries[:max_entries]


def find_email_by_subject(
    device_serial: str = "",
    subject_contains: str = "",
    sender_contains: str = "",
    max_entries: int = 20,
    scroll_passes: int = 2,
) -> Optional[GmailEntry]:
    """Search visible inbox for an email matching subject/sender substring.

    Returns the first matching GmailEntry or None.
    """
    entries = check_gmail_inbox_most_recent(
        device_serial=device_serial,
        max_entries=max_entries,
        scroll_passes=scroll_passes,
    )

    for e in entries:
        if subject_contains and subject_contains.lower() not in e.subject.lower():
            continue
        if sender_contains and sender_contains.lower() not in e.sender.lower():
            continue
        return e

    return None


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Check Gmail inbox")
    parser.add_argument("--device", default="")
    parser.add_argument("--max", type=int, default=10)
    parser.add_argument("--scroll", type=int, default=0)
    parser.add_argument("--find-subject", default="")
    parser.add_argument("--find-sender", default="")
    args = parser.parse_args()

    if args.find_subject or args.find_sender:
        entry = find_email_by_subject(
            device_serial=args.device,
            subject_contains=args.find_subject,
            sender_contains=args.find_sender,
        )
        if entry:
            print(f"FOUND: {entry}")
            print(f"  Sender:  {entry.sender}")
            print(f"  Subject: {entry.subject}")
            print(f"  Date:    {entry.date}")
            print(f"  Snippet: {entry.snippet}")
            print(f"  Unread:  {entry.is_unread}")
        else:
            print("NOT FOUND")
    else:
        entries = check_gmail_inbox_most_recent(
            device_serial=args.device,
            max_entries=args.max,
            scroll_passes=args.scroll,
        )
        print(f"Found {len(entries)} emails:\n")
        for i, e in enumerate(entries, 1):
            flag = " *UNREAD*" if e.is_unread else ""
            print(f"  {i}. [{e.date}] {e.sender} — {e.subject}{flag}")
            if e.snippet:
                print(f"     {e.snippet[:80]}...")
            print()
