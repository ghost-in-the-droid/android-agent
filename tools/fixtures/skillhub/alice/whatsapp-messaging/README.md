# whatsapp-messaging

Send a WhatsApp message to a saved contact, or read the last message in a chat. Fixture content for the hub site build; the real file lives at `skillhub/alice/whatsapp-messaging/README.md`.

## Actions

| Action | What it does |
|---|---|
| `send_msg` | Opens the chat for `contact_name` and sends `message` |
| `read_last_msg` | Returns the newest message text in the chat with `contact_name` |

## Known failure modes

- A "Back up your chats" banner can cover the search field on first launch. The skill dismisses it with a popup detector.
- Contacts with emoji in their display name need the exact emoji in `contact_name`.

<script>alert("this must never run: README is sanitized")</script>
<img src="x" onerror="alert('sanitized')" alt="sanitizer probe">
