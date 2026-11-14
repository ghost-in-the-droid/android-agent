"""type_smoke — TapElement focuses a Contacts text field, TypeText enters text into it."""

from gitd.skills._base.actions.core import TapElement, TypeText
from gitd.skills.base import Element

from .helpers import edit_texts, wait_settled, wait_until

# Contacts' "Create contact" form: plain EditTexts, idle UI, no account prompt on a
# fresh google_apis image. (Settings search was dropped: it lives in a separate app
# that indexes and updates itself for minutes after first boot, which flaked on GH.)
CONTACTS = "com.google.android.contacts"
ELEMENTS = {"first_name": Element("first_name", text="First name")}
QUERY = "ghostci"


def test_type_into_contact_first_name(phone):
    phone.adb("shell", "am", "force-stop", CONTACTS)
    phone.adb("shell", "am", "start", "-a", "android.intent.action.INSERT", "-t", "vnd.android.cursor.dir/contact")
    assert wait_settled(phone, text="First name"), "Create contact form never rendered or kept moving"

    result = TapElement(phone, ELEMENTS, element_name="first_name").run()
    assert result, f"tap_element failed: {result.error}"

    result = TypeText(phone, None, text=QUERY).run()
    assert result, f"type_text failed: {result.error}"

    try:
        assert wait_until(lambda: QUERY in edit_texts(phone)), f"typed text missing from fields: {edit_texts(phone)}"
    finally:
        phone.adb("shell", "am", "force-stop", CONTACTS)  # discard the unsaved contact
