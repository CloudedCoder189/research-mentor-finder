from __future__ import annotations

from pathlib import Path
from datetime import datetime
import shutil

APP = Path(__file__).resolve().parent / "app.py"

if not APP.exists():
    raise SystemExit(
        "app.py was not found. Put this patcher in the same folder as app.py, "
        "The legacy Streamlit app must be present alongside this patcher."
    )

text = APP.read_text(encoding="utf-8")

old_callback = 'def _toggle_favorite_from_button(professor_id: int, state_key: str) -> None:\n    """Persist a shortlist toggle before the fragment redraws."""\n    current_value = bool(st.session_state.get(state_key, False))\n    new_value = not current_value\n    try:\n        set_professor_favorite(professor_id, new_value)\n    except ValueError as exc:\n        st.toast(str(exc), icon="⚠️")\n        return\n    st.session_state[state_key] = new_value\n    if new_value:\n        st.toast("Saved to shortlist", icon="⭐")\n    else:\n        st.toast("Removed from shortlist", icon="🗑️")\n'
new_callback = 'def _toggle_favorite_from_button(\n    professor_id: int,\n    state_key: str,\n    feedback_key: str,\n) -> None:\n    """Persist a shortlist toggle without rendering UI inside the callback."""\n    current_value = bool(st.session_state.get(state_key, False))\n    new_value = not current_value\n    try:\n        set_professor_favorite(professor_id, new_value)\n    except ValueError as exc:\n        st.session_state[feedback_key] = ("error", str(exc))\n        return\n\n    st.session_state[state_key] = new_value\n    st.session_state[feedback_key] = (\n        "saved" if new_value else "removed",\n        "Saved to shortlist" if new_value else "Removed from shortlist",\n    )\n'
old_fragment = '    is_favorite = bool(st.session_state[state_key])\n    label = "🗑 Remove from shortlist" if is_favorite else "⭐ Save to shortlist"\n    st.button(\n        label,\n        key=f"{key_prefix}-favorite-action-{professor_id}",\n        use_container_width=True,\n        type="secondary",\n        help=(\n            "Remove this professor from your persistent shortlist."\n            if is_favorite\n            else "Save this professor to your persistent shortlist."\n        ),\n        on_click=_toggle_favorite_from_button,\n        args=(professor_id, state_key),\n    )\n'
new_fragment = '    is_favorite = bool(st.session_state[state_key])\n    label = "🗑 Remove from shortlist" if is_favorite else "⭐ Save to shortlist"\n    feedback_key = f"{state_key}-feedback"\n    st.button(\n        label,\n        key=f"{key_prefix}-favorite-action-{professor_id}",\n        use_container_width=True,\n        type="secondary",\n        help=(\n            "Remove this professor from your persistent shortlist."\n            if is_favorite\n            else "Save this professor to your persistent shortlist."\n        ),\n        on_click=_toggle_favorite_from_button,\n        args=(professor_id, state_key, feedback_key),\n    )\n\n    feedback = st.session_state.pop(feedback_key, None)\n    if feedback:\n        feedback_type, feedback_message = feedback\n        if feedback_type == "error":\n            st.error(feedback_message)\n        elif feedback_type == "saved":\n            st.toast(feedback_message, icon="⭐")\n        else:\n            st.toast(feedback_message, icon="🗑️")\n'

missing = []
if old_callback not in text:
    missing.append("_toggle_favorite_from_button")
if old_fragment not in text:
    missing.append("_render_favorite_button")

if missing:
    raise SystemExit(
        "Patch stopped safely because the expected code was not found: "
        + ", ".join(missing)
        + ". Your app.py was not changed."
    )

timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
backup = APP.with_name(f"app.before-shortlist-fragment-fix-{timestamp}.py")
shutil.copy2(APP, backup)

patched = text.replace(old_callback, new_callback, 1)
patched = patched.replace(old_fragment, new_fragment, 1)

compile(patched, str(APP), "exec")
APP.write_text(patched, encoding="utf-8")

print("Shortlist fragment fix applied successfully.")
print(f"Backup created: {backup.name}")
print("Syntax check: passed")
print("Restart Streamlit, then try Save to shortlist again.")
