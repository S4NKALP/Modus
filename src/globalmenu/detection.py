"""Detect whether an executable is built against GTK3 or GTK4.

The global menu compat shim (libmenu_button_shim.so) links against GTK3 and
must only be loaded into GTK3 processes. Loading it into a GTK4 process pulls
GTK 2/3 symbols into the same process and GTK4 aborts with:

    GTK-ERROR: "GTK 2/3 symbols detected. Using GTK 2/3 and GTK 4 in the same
    process is not supported"

We therefore inspect an executable's ELF ``DT_NEEDED`` entries to learn which
GTK it depends on, and only inject the shim for GTK3 binaries. Results are
cached on disk (keyed by resolved path + mtime) so the lookup is cheap and is
never run on every launch for unchanged binaries.
"""

import json
import os
import shutil
from collections import deque
from pathlib import Path

from fabric.utils import logger

# SONAMEs we care about.
GTK3_SONAME = "libgtk-3.so.0"
GTK4_SONAME = "libgtk-4.so.1"

_CACHE_DIR = Path.home() / ".cache" / "modus"
_CACHE_FILE = _CACHE_DIR / "gtk_class_cache.json"

# Directories searched when resolving a NEEDED SONAME to a file. The binary's
# own directory is always tried first, then these (LD_LIBRARY_PATH wins).
_LIB_DIRS = [
    *os.environ.get("LD_LIBRARY_PATH", "").split(os.pathsep),
    "/usr/lib",
    "/usr/lib64",
    "/lib",
    "/lib64",
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib/i386-linux-gnu",
]


def _parse_dynamic(path: Path) -> tuple[set[str], list[Path]]:
    """Parse an ELF's dynamic section.

    Returns ``(needed_sonames, runpath_dirs)``. ``runpath_dirs`` are the
    directories named by DT_RUNPATH/DT_RPATH with ``$ORIGIN`` expanded to the
    directory containing ``path``. Private libraries (e.g. gedit's
    libgedit-50.so) live there and must be searched to follow the dependency
    tree correctly.
    """
    try:
        with open(path, "rb") as f:
            ident = f.read(20)
        if len(ident) < 20 or ident[:4] != b"\x7fELF":
            return set(), []
        is_64 = ident[4] == 2
        data = path.read_bytes()
    except OSError as e:
        logger.warning(
            f"[detection] with open(path, 'rb') as f: ident = f.read(20) failed: {e}"
        )
        return set(), []

    try:
        if is_64:
            e_phoff = int.from_bytes(data[0x20:0x28], "little")
            e_phentsize = int.from_bytes(data[0x36:0x38], "little")
            e_phnum = int.from_bytes(data[0x38:0x3A], "little")
        else:
            e_phoff = int.from_bytes(data[0x1C:0x20], "little")
            e_phentsize = int.from_bytes(data[0x2A:0x2C], "little")
            e_phnum = int.from_bytes(data[0x2C:0x2E], "little")
    except (IndexError, ValueError) as e:
        logger.warning(
            f"[detection] if is_64: e_phoff = int.from_bytes(data[0x20:0x28], 'litt... failed: {e}"
        )
        return set(), []

    PT_DYNAMIC = 2
    word_size = 8 if is_64 else 4

    def unpack(b: bytes) -> int:
        return int.from_bytes(b[:word_size], "little")

    dynamic_off = None
    for i in range(e_phnum):
        base = e_phoff + i * e_phentsize
        if unpack(data[base : base + 4]) == PT_DYNAMIC:
            dynamic_off = unpack(data[base + word_size : base + word_size * 2])
            dyn_strtab = unpack(data[base + word_size * 2 : base + word_size * 3])
            break

    if dynamic_off is None:
        return set(), []

    DT_NEEDED = 1
    DT_STRTAB = 5
    DT_RUNPATH = 0x1D
    DT_RPATH = 0x0F

    needed_offsets: list[int] = []
    strtab_off = dyn_strtab
    runpath_str = ""
    step = word_size * 2

    pos = dynamic_off
    while pos + step <= len(data):
        d_tag = unpack(data[pos : pos + word_size])
        d_val = unpack(data[pos + word_size : pos + step])
        if d_tag == 0:  # DT_NULL
            break
        if d_tag == DT_NEEDED:
            needed_offsets.append(d_val)
        elif d_tag == DT_STRTAB:
            strtab_off = d_val
        elif d_tag in (DT_RUNPATH, DT_RPATH):
            end = data.find(b"\x00", strtab_off + d_val)
            if end != -1:
                runpath_str = data[strtab_off + d_val : end].decode("utf-8", "replace")
        pos += step

    needed: set[str] = set()
    for off in needed_offsets:
        end = data.find(b"\x00", strtab_off + off)
        if end == -1:
            continue
        needed.add(data[strtab_off + off : end].decode("utf-8", "replace"))

    origin = path.parent
    runpath_dirs: list[Path] = []
    for entry in runpath_str.split(":"):
        entry = entry.strip()
        if not entry:
            continue
        entry = entry.replace("$ORIGIN", str(origin)).replace("${ORIGIN}", str(origin))
        runpath_dirs.append(Path(entry))

    return needed, runpath_dirs


def _find_lib(soname: str, search_dirs: list[Path]) -> Path | None:
    """Resolve a NEEDED SONAME to a file within ``search_dirs``."""
    for directory in search_dirs:
        candidate = directory / soname
        if candidate.is_file():
            return candidate
    return None


def _transitive_needed(root: Path) -> set[str]:
    """Collect every DT_NEEDED SONAME in the dependency tree of ``root``.

    Follows NEEDED entries transitively (including private libs reached via
    RUNPATH) so that GTK pulled in indirectly is still detected.
    """
    all_needed: set[str] = set()
    seen_paths: set[Path] = set()
    queue: deque[Path] = deque([root])

    while queue:
        lib = queue.popleft()
        if lib in seen_paths:
            continue
        seen_paths.add(lib)

        needed, runpath_dirs = _parse_dynamic(lib)
        search_dirs = [lib.parent, *runpath_dirs, *[Path(d) for d in _LIB_DIRS if d]]
        for soname in needed:
            all_needed.add(soname)
            if soname in (GTK3_SONAME, GTK4_SONAME):
                continue
            dep = _find_lib(soname, search_dirs)
            if dep and dep not in seen_paths:
                queue.append(dep)

    return all_needed


def _load_cache() -> dict:
    try:
        return json.loads(_CACHE_FILE.read_text())
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(
            f"[detection] return json.loads(_CACHE_FILE.read_text()) failed: {e}"
        )
        return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(cache))
    except OSError as e:
        logger.debug(f"[GlobalMenu] Could not write gtk class cache: {e}")


def executable_gtk_class(executable: str | None) -> str | None:
    """Classify an executable as ``"gtk3"``, ``"gtk4"`` or ``None``.

    ``None`` means "unable to determine" (e.g. a shell script, a wrapper, or a
    non-GTK binary). In that case the caller should NOT inject the GTK3 shim,
    which keeps GTK4 applications safe.
    """
    if not executable:
        return None

    token = executable.strip().split()[0] if executable.strip() else ""
    if not token:
        return None

    resolved = shutil.which(token) or token
    path = Path(resolved).expanduser()
    if not path.is_absolute() or not path.exists():
        # Try as a direct path too.
        path = Path(token)
        if not path.exists():
            return None

    try:
        mtime = path.stat().st_mtime_ns
    except OSError as e:
        logger.warning(f"[detection] mtime = path.stat().st_mtime_ns failed: {e}")
        return None

    cache = _load_cache()
    key = f"{path}"
    cached = cache.get(key)
    if cached and cached.get("mtime") == mtime:
        return cached.get("class")

    needed = _transitive_needed(path)
    if GTK4_SONAME in needed:
        klass = "gtk4"
    elif GTK3_SONAME in needed:
        klass = "gtk3"
    else:
        klass = None

    cache[key] = {"mtime": mtime, "class": klass}
    _save_cache(cache)
    return klass
