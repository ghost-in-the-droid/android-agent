# messages - SOFT skill (LLM-adaptable narrative)

What each action means, which UI landmarks it relies on, and how success is recognised, so an agent can adapt it to another SMS app or version.

**Package**: `com.google.android.apps.messaging` (Google Messages)
**Verified**: 2026-10-05 on a headless emulator pool, Android 14 google_apis x86_64, 1080x2400 @ 420 dpi, Messages 20230529, en-US, no Google account ("Use Messages without an account").
**Skill class**: HARD. No login, no checkpoints. Drafts only: no step taps Send.

## Safety rules (read before adapting)

- Never tap the Send button (`id/send_message_button_icon`).
- Never tap in the top band of the screen while a message may arrive: a heads-up notification there carries smart-reply chips ("Sure!", "Yes, I did") that send on a single tap, and Ghost Portal cannot see that window. Conversations are therefore opened with `android.intent.action.SENDTO` (`smsto:<number>`) and left with BACK, never by tapping rows or the toolbar arrow.
- Test pools can turn heads-up off with `settings put global heads_up_notifications_enabled 0`.

## Layout reference

- Conversation list: rows `id/swipeableContainer` containing `id/conversation_name`, `id/conversation_snippet` (`You: ...` for own or draft text), `id/conversation_timestamp` (`Draft` for drafts) and `id/unread_badge`. FAB `id/start_chat_fab`.
- Conversation: `id/conversation_title`, message bubbles `id/message_content` with content-desc `"<sender> said  <text>  ., <time>[, SMS]"` (`You said` for own messages), compose box `id/compose_message_text`.

## Actions

### `draft_message(number, text)`

1. Fresh launch; skip the sign-in screen with "Use Messages without an account".
2. SENDTO `smsto:<number>` with extra `sms_body=<text>`; the body replaces any older draft.
3. Check the compose box holds exactly `text`, else abort.
4. BACK. Messages saves the draft.
5. Success: a list row with timestamp `Draft` and snippet `You: <text>`.

### `list_conversations()`

Read every row (scrolling): `{name, snippet, time, is_draft, unread}`.

### `read_conversation(number)`

SENDTO `smsto:<number>` without a body opens the thread (an existing draft stays in the compose box, unsent). Parse bubble descriptions into `{from, text, time}`; `from` is `me` for own messages. BACK.

## Test fixture

Incoming SMS can be simulated on the emulator host: `adb -s <serial> emu sms send 5550100 "Lunch tomorrow at noon?"`.

## Failure modes

- Signed-in Messages (RCS) shows chat features and different first-run screens.
- A number that matches a contact shows the contact name as the title; the helpers do not depend on the title text.
