from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
KEYBOARD_PATH = ROOT / "src" / "presentation" / "keyboards" / "common.py"
HANDLER_PATHS = list((ROOT / "src").rglob("*.py"))


def extract_keyboard_callbacks():
    """Extract callback data strings from keyboard definitions."""
    text = KEYBOARD_PATH.read_text(encoding="utf-8")
    values = set()
    # Match button tuples: (text, "callback_data")
    values |= set(re.findall(r'"([^"]+)"\s*\)', text))
    # Match f-string callback_data
    values |= set(re.findall(r'callback_data\s*=\s*f?"([^"]+)"', text))
    return values


def extract_handler_routes():
    """Extract F.data patterns from all handler files."""
    routes = set()
    for path in HANDLER_PATHS:
        text = path.read_text(encoding="utf-8")
        routes |= set(re.findall(r'F\.data\s*==\s*"([^"]+)"', text))
        routes |= set(re.findall(r'F\.data\.startswith\(\s*"([^"]+)"\s*\)', text))
    return routes


def _route_matches(callback: str, routes: set) -> bool:
    """Check if a callback is covered by at least one handler route.

    Keyboard callbacks may contain runtime template placeholders
    (e.g. ``admin_role_admin:{user_id}``); only the static prefix is compared.
    """
    # Strip runtime template placeholders like {user_id}
    static = callback.split("{", 1)[0]
    if static.endswith(":"):
        static = static[:-1]

    if callback in routes or static in routes:
        return True
    for route in routes:
        route_clean = route.rstrip(":")
        if route_clean == static or static.startswith(route_clean):
            return True
    if ":" in static:
        prefix = static.split(":", 1)[0]
        for route in routes:
            route_clean = route.rstrip(":")
            if route_clean == prefix or prefix.startswith(route_clean):
                return True
    if callback.startswith("main_menu") and "main_menu" in routes:
        return True
    return False


def test_keyboard_callbacks_have_matching_routes():
    keyboard_callbacks = extract_keyboard_callbacks()
    handler_routes = extract_handler_routes()

    missing = []
    for callback in sorted(keyboard_callbacks):
        if _route_matches(callback, handler_routes):
            continue
        missing.append(callback)

    assert not missing, (
        f"Broken callback routes — keyboard defines callbacks not handled:\n"
        f"  Missing handlers for: {missing}\n"
        f"  Handler routes: {sorted(handler_routes)}"
    )


def test_payment_and_search_callbacks_are_exposed():
    callbacks = extract_keyboard_callbacks()
    assert "treasurer_user_search" in callbacks, "treasurer_user_search not found in keyboards"
    assert any(cb.startswith("pay_type:") for cb in callbacks), "pay_type callbacks not found in keyboards"
