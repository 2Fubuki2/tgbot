import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYBOARD_PATH = ROOT / "src" / "presentation" / "keyboards" / "common.py"
HANDLER_PATHS = list((ROOT / "src").rglob("*.py"))


def extract_keyboard_callbacks():
    text = KEYBOARD_PATH.read_text(encoding="utf-8")
    values = set(re.findall(r'\(\s*\(\s*"[^"]+"\s*,\s*"([^"]+)"\s*\)\s*\]', text))
    values |= set(re.findall(r'callback_data\s*=\s*(?:f)?"([^"]+)"', text))
    return values


def extract_handler_routes():
    routes = set()
    for path in HANDLER_PATHS:
        text = path.read_text(encoding="utf-8")
        routes |= set(re.findall(r'F\.data\s*==\s*"([^"]+)"', text))
        routes |= set(re.findall(r'F\.data\.startswith\(\s*"([^"]+)"', text))
    return routes


def test_keyboard_callbacks_have_matching_routes():
    keyboard_callbacks = extract_keyboard_callbacks()
    handler_routes = extract_handler_routes()

    missing = []
    for callback in sorted(keyboard_callbacks):
        if callback in handler_routes:
            continue
        if ":" in callback:
            prefix = callback.split(":", 1)[0]
            if any(route == prefix or route.startswith(f"{prefix}:") for route in handler_routes):
                continue
        if callback.startswith("main_menu") and "main_menu" in handler_routes:
            continue
        missing.append(callback)

    assert not missing, f"Broken callback routes: {missing}"


def test_payment_and_search_callbacks_are_exposed():
    callbacks = extract_keyboard_callbacks()
    assert "treasurer_user_search" in callbacks
    assert any(cb.startswith("pay_type:") for cb in callbacks)
