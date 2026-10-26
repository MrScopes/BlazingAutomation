import ast
import hashlib
import io
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from config import REPO, VERSION

SRC = Path(__file__).resolve().parent
APP = SRC.parent
INSTALLER = APP.parent

TIMEOUT = 30
MAX_ZIP_BYTES = 100 * 1024 * 1024
MAX_UNPACKED_BYTES = 250 * 1024 * 1024
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$", re.I)

LAUNCHERS = {"Run.bat"}
OLD_LAUNCHERS = {"Install.bat", "Developer.bat"}        # replaced by the launcher menu; offered for deletion
IGNORED_DIRS = {"__pycache__", ".git", ".venv", ".runtime", ".bootstrap", ".cache", "tools", "models"}
IGNORED_SUFFIXES = {".pyc", ".pyo", ".log", ".tmp", ".bak"}
IGNORED_FILES = {".setup.json", ".layout.json", "desktop.ini", "thumbs.db"}

def fetch(url):
    req = Request(url, headers={
        "User-Agent": "BlazingAutomation-Updater",
        "Accept": "application/vnd.github+json",
    })

    with urlopen(req, timeout=TIMEOUT) as response:
        size = response.headers.get("Content-Length")
        if size and int(size) > MAX_ZIP_BYTES:
            raise ValueError("Release archive exceeds size limit")

        data = response.read(MAX_ZIP_BYTES + 1)
        if len(data) > MAX_ZIP_BYTES:
            raise ValueError("Release archive exceeds size limit")
        return data

def repo_name():
    parsed = urlparse(REPO.rstrip("/"))
    parts = parsed.path.strip("/").split("/")
    if parsed.scheme != "https" or parsed.hostname != "github.com" or len(parts) != 2:
        raise ValueError("REPO must be a GitHub repository URL")
    return parts[0], parts[1].removesuffix(".git")

def parse_version(value):
    match = VERSION_PATTERN.fullmatch(str(value).strip())
    if not match:
        raise ValueError(f"Invalid version: {value!r}")
    return tuple(map(int, match.groups()))

def managed(name):
    parts = name.split("/")
    if any(part.lower() in IGNORED_DIRS for part in parts[:-1]):
        return False
    if parts[-1].lower() in IGNORED_FILES:
        return False
    if Path(parts[-1]).suffix.lower() in IGNORED_SUFFIXES:
        return False
    return name in LAUNCHERS or (len(parts) >= 3 and parts[:2] in (["app", "src"], ["app", "scripts"]))

def safe_files(zf):
    files = {}
    total_size = 0

    for info in zf.infolist():
        if info.is_dir():
            continue

        name = info.filename.replace("\\", "/")
        parts = name.split("/")
        if name.startswith("/") or any(part in ("", ".", "..") for part in parts) or re.match(r"^[A-Za-z]:", name) or ":" in name:
            raise ValueError(f"Unsafe archive path: {name}")

        mode = (info.external_attr >> 16) & 0o170000
        if mode not in (0, 0o100000):
            raise ValueError(f"Unsupported archive entry: {name}")

        if managed(name):
            if any(existing.casefold() == name.casefold() for existing in files):
                raise ValueError(f"Duplicate archive path: {name}")

            files[name] = info
            total_size += info.file_size
            if total_size > MAX_UNPACKED_BYTES:
                raise ValueError("Uncompressed release exceeds size limit")

    required = LAUNCHERS | {"app/src/main.py", "app/src/config.py", "app/src/launcher.py", "app/scripts/setup.ps1"}
    missing = required - files.keys()
    if missing:
        raise ValueError(f"Release ZIP missing: {', '.join(sorted(missing))}")
    return files

def version_from_zip(zf, files):
    source = zf.read(files["app/src/config.py"]).decode("utf-8-sig")
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "VERSION" for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError("Release config.py has no VERSION")

def read_constant(source, name, default=None):
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    return default

def installed_setup_revision():
    # installs from before revisions existed count as revision 1
    try:
        return int(json.loads((APP / ".setup.json").read_text(encoding="utf-8-sig")).get("revision", 1))
    except Exception:
        return 1

def get_latest_release():
    owner, repo = repo_name()
    api = f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}/releases/latest"
    release = json.loads(fetch(api))

    tag = release.get("tag_name", "").strip()
    match = VERSION_PATTERN.fullmatch(tag)
    if not match:
        raise RuntimeError(f"Invalid release tag: {tag!r}; expected v0.1.3")

    latest_version = ".".join(match.groups())
    expected_name = f"blazingautomation-{latest_version}.zip"
    asset = next(
        (item for item in release.get("assets", []) if item["name"].lower() == expected_name.lower()),
        None,
    )
    if not asset:
        raise RuntimeError(f"Release asset not found: {expected_name}")
    return latest_version, asset

def clean_notes(body, max_lines=25):
    # release notes are markdown; the console only needs readable text
    body = re.sub(r"<!--.*?-->", "", body or "", flags=re.S).replace("\r", "")
    lines = []
    for line in body.splitlines():
        line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line.rstrip())
        line = line.replace("**", "").replace("`", "")
        if line.strip() or (lines and lines[-1]):
            lines.append(line)
    while lines and not lines[-1].strip():
        lines.pop()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["..."]
    return lines

def release_notes(installed=VERSION, latest=None):
    """[(version, [lines])] for every published release newer than `installed`, newest first."""
    owner, repo = repo_name()
    releases = json.loads(fetch(f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}/releases?per_page=15"))
    found = []
    for release in releases:
        match = VERSION_PATTERN.fullmatch(str(release.get("tag_name", "")).strip())
        if not match or release.get("draft") or release.get("prerelease"):
            continue
        version = tuple(map(int, match.groups()))
        if version <= parse_version(installed) or (latest and version > parse_version(latest)):
            continue
        found.append((version, ".".join(map(str, version)), clean_notes(release.get("body"))))
    return [(name, lines) for _, name, lines in sorted(found, reverse=True)]

def print_notes(notes):
    for name, lines in notes:
        print(f"\n  v{name}", flush=True)
        for line in lines or ["(no release notes)"]:
            print(f"    {line}", flush=True)

def check_update():
    try:
        latest_version, _ = get_latest_release()
        if parse_version(latest_version) > parse_version(VERSION):
            return latest_version
    except Exception:
        pass
    return None

def local_managed_files():
    result = {}

    for launcher in LAUNCHERS | OLD_LAUNCHERS:
        path = INSTALLER / launcher
        if path.is_file():
            result[launcher] = path

    for folder in (APP / "src", APP / "scripts"):
        if not folder.is_dir():
            continue

        for path in folder.rglob("*"):
            if path.is_file() and not path.is_symlink():
                name = path.relative_to(INSTALLER).as_posix()
                if managed(name):
                    result[name] = path

    return result

def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.digest()

def display_group(title, names):
    print(f"\n{title} ({len(names)}):")
    for name in names:
        print(f"  {name}")

def ask(prompt):
    return input(prompt).strip().lower() in ("y", "yes")

def update(assume_yes=False):
    if not (APP / "scripts").is_dir() or not (INSTALLER / "Run.bat").is_file():
        raise RuntimeError("Updater must run from an installed installer/app/src layout")

    print("[UPDATE] Checking GitHub releases...", flush=True)
    latest_version, asset = get_latest_release()
    print(f"[UPDATE] Installed: {VERSION} | Latest release: {latest_version}", flush=True)

    if parse_version(latest_version) <= parse_version(VERSION):
        print("[UPDATE] Already up to date.", flush=True)
        return False

    if not assume_yes:
        try:
            print("\nWhat's new:", flush=True)
            print_notes(release_notes(VERSION, latest_version))
            print(flush=True)
        except Exception:
            pass                    # notes are a courtesy; never block an update on them

    if not (assume_yes or ask(f"Install Blazing Automation {latest_version}? [y/N]: ")):
        print("[UPDATE] Cancelled.", flush=True)
        return False

    print(f"[DOWNLOAD] {asset['name']}", flush=True)
    archive = fetch(asset["browser_download_url"])

    with tempfile.TemporaryDirectory(prefix="blazing-update-") as temp:
        tmp = Path(temp)
        staged = tmp / "staged"
        backup = tmp / "backup"
        staged.mkdir()
        backup.mkdir()

        with zipfile.ZipFile(io.BytesIO(archive)) as zf:
            files = safe_files(zf)
            archive_version = version_from_zip(zf, files)
            if parse_version(archive_version) != parse_version(latest_version):
                raise ValueError(
                    f"ZIP VERSION {archive_version!r} doesn't match release {latest_version!r}"
                )

            print("[UPDATE] Extracting release...", flush=True)
            for name, info in files.items():
                target = staged / Path(name)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as source, target.open("wb") as dest:
                    shutil.copyfileobj(source, dest)

        existing = local_managed_files()
        incoming = set(files)
        installed = set(existing)

        added = sorted(incoming - installed)
        changed = sorted(
            name for name in incoming & installed
            if digest(staged / name) != digest(existing[name])
        )
        unchanged = sorted((incoming & installed) - set(changed))
        obsolete = sorted(installed - incoming)

        display_group("[ADD] New files", added)
        display_group("[REPLACE] Changed files", changed)
        print(f"\n[UNCHANGED] {len(unchanged)} files", flush=True)
        display_group("[OLD] Files absent from new release", obsolete)

        remove_old = False
        if obsolete:
            print("\n[WARNING] Old files may include custom macros or local edits.", flush=True)
            remove_old = ask("Delete ALL listed old files? [y/N]: ")
            if not remove_old:
                print("[KEEP] Old files will be preserved.", flush=True)

        operations = [(name, "write") for name in added + changed]
        if remove_old:
            operations.extend((name, "delete") for name in obsolete)

        if not operations:
            print("[UPDATE] No file changes required.", flush=True)
            return False

        print(
            f"\n[PLAN] Add {len(added)}, replace {len(changed)}, "
            f"delete {len(obsolete) if remove_old else 0}, "
            f"leave unchanged {len(unchanged)}.",
            flush=True,
        )
        if not ask("Apply these changes? [y/N]: "):
            print("[UPDATE] Cancelled.", flush=True)
            return False

        print("[UPDATE] Installing files...", flush=True)
        applied = []

        try:
            for name, action in operations:
                target = INSTALLER / name
                saved = backup / name
                existed = target.exists()

                if existed:
                    saved.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, saved)

                applied.append((target, saved, existed))

                if action == "delete":
                    target.unlink()
                    print(f"[DELETE] {name}", flush=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(staged / name, target)
                    label = "REPLACE" if existed else "ADD"
                    print(f"[{label}] {name}", flush=True)

        except Exception:
            print("[UPDATE] Installation failed; restoring previous files...", flush=True)
            errors = []

            for target, saved, existed in reversed(applied):
                try:
                    if existed:
                        shutil.copy2(saved, target)
                    else:
                        target.unlink(missing_ok=True)
                except Exception as exc:
                    errors.append(f"{target}: {exc}")

            if errors:
                raise RuntimeError("Rollback incomplete:\n" + "\n".join(errors))
            raise

        needs_setup = read_constant((staged / "app/src/config.py").read_text(encoding="utf-8-sig"), "SETUP_REVISION", 1) > installed_setup_revision()

    if needs_setup:
        # no .setup.json makes Run.bat run setup before the menu; it only installs what is missing
        (APP / ".setup.json").unlink(missing_ok=True)
        print("\n[UPDATE] This update needs a setup refresh. It runs the next time you open Run.bat.", flush=True)

    print(f"\n[UPDATE] Installed {latest_version}. Restart the application.", flush=True)
    print("[UPDATE] Runtime, models, dependencies and ignored files were preserved.", flush=True)
    return True

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="BlazingAutomation updater")
    parser.add_argument("--check", action="store_true", help="Silently check for a newer release")
    parser.add_argument("--notes", action="store_true", help="Print the release notes of every newer version")
    parser.add_argument("--yes", action="store_true", help="Skip the first install question (the launcher already asked)")
    args = parser.parse_args()

    if args.notes:
        try:
            latest, _ = get_latest_release()
            print_notes(release_notes(VERSION, latest))
        except Exception:
            pass
        raise SystemExit(0)

    if args.check:
        # prints the newer version if there is one; exit code 1 means GitHub could not be reached
        try:
            latest, _ = get_latest_release()
        except Exception:
            raise SystemExit(1)
        if parse_version(latest) > parse_version(VERSION):
            print(latest)
        raise SystemExit(0)

    try:
        installed = update(assume_yes=args.yes)
        raise SystemExit(10 if installed else 0)
    except KeyboardInterrupt:
        print("\n[UPDATE] Cancelled.")
        raise SystemExit(0)
    except Exception as exc:
        print(f"[UPDATE] Error: {exc}")
        raise SystemExit(1)