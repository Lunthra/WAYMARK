"""
WAYMARK M12 — Clean File Verification

SAFE MODE:
- Does not import or execute either Core.
- Does not call MAL, Serializd, TMDB, Playwright, or any write function.
- Verifies that the v1.9 and v2.0 Core files are distinct, present,
  syntactically valid, and contain the expected guided-workflow structure.

Run from the WAYMARK project folder:
    .\.venv\Scripts\python.exe test_waymark_m12_guided_workflow.py
"""

from pathlib import Path
import ast

V1 = Path("waymark_core.py")
V2 = Path("waymark_core_v2_0_guided_workflow.py")
TEST = Path("test_waymark_m12_guided_workflow.py")


def read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def function_names(text: str) -> set[str]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


passed = 0
failed = 0


def report(ok: bool, label: str) -> None:
    global passed, failed
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if ok:
        passed += 1
    else:
        failed += 1


print("=" * 68)
print("WAYMARK M12 — CLEAN FILE VERIFICATION")
print("SAFE MODE: NO IMPORTS; NO SERVICE CALLS; NO LIVE WRITES")
print("=" * 68)

v1 = read_source(V1)
v2 = read_source(V2)
test_source = read_source(TEST)

report(V1.is_file() and bool(v1), "v1.9 Core exists and is non-empty")
report(V2.is_file() and bool(v2), "v2.0 Core exists and is non-empty")
report(TEST.is_file() and bool(test_source), "M12 test exists and is non-empty")

for label, path, source in (
    ("v1.9 Core", V1, v1),
    ("v2.0 Core", V2, v2),
):
    if not source:
        continue
    try:
        ast.parse(source, filename=str(path))
        report(True, f"{label} is syntactically valid")
    except SyntaxError as exc:
        report(False, f"{label} is syntactically valid")
        print(f"      {exc}")

v1f = function_names(v1)
v2f = function_names(v2)

required = [
    "run_waymark_chat",
    "_ask_for_mal_episode_number",
    "_chat_execute_anime_tv_action",
    "_chat_resolve_serializd_season",
    "_choose_mal_from_matches",
    "_choose_serializd_arc_and_episode",
    "_choose_serializd_match",
    "_validate_chat_action_plan",
]

for name in required:
    report(name in v1f, f"v1.9 contains {name}")

for name in required:
    report(name in v2f or name in v2, f"v2.0 contains or references {name}")

v2_lower = v2.lower()

markers = [
    (
        "v2.0 version marker",
        "v2.0" in v2_lower
        or 'version = "2.0"' in v2_lower
        or "waymark_core_version" in v2_lower,
    ),
    (
        "v2.0 guided watch-today wording",
        "what did you watch today" in v2_lower,
    ),
    (
        "v2.0 anime classification",
        "is it anime" in v2_lower or "is it an anime" in v2_lower,
    ),
    (
        "v2.0 movie / TV classification",
        "movie or tv" in v2_lower
        or "tv show or a movie" in v2_lower
        or "tv or movie" in v2_lower,
    ),
    (
        "v2.0 Serializd season / arc handling",
        "serializd" in v2_lower
        and ("season" in v2_lower or "arc" in v2_lower),
    ),
    (
        "v2.0 Serializd episode handling",
        "serializd" in v2_lower and "episode" in v2_lower,
    ),
    (
        "v2.0 MAL episode handling",
        "_ask_for_mal_episode_number" in v2
        or "mal episode" in v2_lower,
    ),
    (
        "v2.0 confirmation handling",
        "confirm" in v2_lower,
    ),
    (
        "v2.0 cancellation handling",
        "cancel" in v2_lower,
    ),
    (
        "v2.0 MAL + Serializd routing",
        "mal" in v2_lower and "serializd" in v2_lower,
    ),
    (
        "v2.0 TMDB movie reference",
        "tmdb" in v2_lower and "movie" in v2_lower,
    ),
    (
        "v2.0 validation handling",
        "_validate_chat_action_plan" in v2
        or "validate" in v2_lower,
    ),
    (
        "v2.0 execution handling",
        "_chat_execute_anime_tv_action" in v2,
    ),
]

for label, ok in markers:
    report(ok, label)

# Verify that the test file itself is structurally a static test.
test_lower = test_source.lower()
report(
    "waymark m12" in test_lower
    and "no imports" in test_lower
    and "no live writes" in test_lower
    and "ast.parse" in test_source
    and "waymark_core" not in test_lower.replace(
        "waymark_core.py", ""
    ).replace(
        "waymark_core_v2_0_guided_workflow.py", ""
    ),
    "M12 harness is a static verification harness, not the WAYMARK Core",
)

# Check the actual test source for network/write APIs, while ignoring the
# explanatory words in the module docstring.
try:
    test_tree = ast.parse(test_source, filename=str(TEST))
    executable_calls = []
    for node in ast.walk(test_tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                executable_calls.append(node.func.attr)
            elif isinstance(node.func, ast.Name):
                executable_calls.append(node.func.id)

    forbidden = {
        "post", "patch", "put", "delete", "request",
        "update_progress", "update_status", "update_score",
    }
    found = sorted(forbidden.intersection(executable_calls))
    report(
        not found,
        "M12 harness contains no executable service-write calls",
    )
    if found:
        print(f"      Found: {', '.join(found)}")
except SyntaxError:
    report(False, "M12 harness contains no executable service-write calls")

print("\n" + "=" * 68)
print(f"RESULT: {passed} passed, {failed} failed")
print("=" * 68)

if failed:
    print("M12 verification needs attention.")
else:
    print("M12 verification PASSED.")
print("NO live service writes were performed.")
