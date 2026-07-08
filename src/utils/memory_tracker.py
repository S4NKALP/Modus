import os
import gc
import tracemalloc

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_snapshot_counter = 0
_initial_snapshot = None


def _is_project_module(filename: str) -> bool:
    return filename.startswith(PROJECT_ROOT) and ".venv" not in filename


def start_tracing() -> None:
    """Start tracemalloc + file-triggered dumps.

    Only activates if MODUS_MEMTRACE env var is set.
    Every 2s checks for /tmp/modus_dump. Touch that file to trigger a dump.

      MODUS_MEMTRACE=1 uv run start
      touch /tmp/modus_dump   # triggers dump
    """
    if not os.environ.get("MODUS_MEMTRACE"):
        return
    try:
        tracemalloc.start(10)
        global _initial_snapshot
        _initial_snapshot = tracemalloc.take_snapshot()

        from fabric.utils import GLib

        GLib.timeout_add(2000, _poll_dump_file)

        print("[memory_tracker] active — touch /tmp/modus_dump to dump", flush=True)
    except Exception as e:
        _log_error(f"start_tracing failed: {e}")
        print(
            f"[memory_tracker] FAILED: {e}",
            file=__import__("sys").stderr,
            flush=True,
        )


def _log_error(msg: str) -> None:
    try:
        with open("/tmp/modus_memtrace_err.log", "a") as f:
            f.write(f"{msg}\n")
    except Exception:
        pass


def _poll_dump_file() -> bool:
    if os.path.exists("/tmp/modus_dump"):
        try:
            os.unlink("/tmp/modus_dump")
            dump_memory_usage()
        except Exception as e:
            _log_error(f"dump failed: {e}")
    return True


def _get_process_rss() -> int:
    """Return RSS in bytes from /proc/self/status."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except Exception:
        pass
    return 0


def _estimate_obj_bytes(obj) -> int:
    """Best-effort byte estimate for a live object.
    Uses special handling for known types, falls back to sys.getsizeof.
    """
    import sys

    try:
        tname = type(obj).__name__
        tmod = getattr(type(obj), "__module__", "")

        # -- known C types with accessible pixel data --
        if "Pixbuf" in tname:
            try:
                return obj.get_width() * obj.get_height() * obj.get_n_channels()
            except Exception:
                pass
        if "Surface" in tname and "cairo" in tmod:
            try:
                return obj.get_width() * obj.get_height() * 4
            except Exception:
                pass

        # -- strings (include internal buffer) --
        if isinstance(obj, str):
            return sys.getsizeof(obj)

        # -- bytes / bytearray --
        if isinstance(obj, (bytes, bytearray)):
            return sys.getsizeof(obj)

        # -- dicts / lists / tuples (shallow — contents counted separately) --
        if isinstance(obj, (dict, list, tuple, set, frozenset)):
            return sys.getsizeof(obj)

        # -- GObject wrappers: return Python wrapper size (C struct not included) --
        return sys.getsizeof(obj)

    except Exception:
        return 0


def _scan_all_objects() -> dict:
    """Scan ALL live Python objects, group by type, show counts + size estimates."""

    by_type: dict[str, dict] = {}
    total_count = 0
    total_bytes = 0

    for obj in gc.get_objects():
        try:
            tname = type(obj).__name__
            tmod = getattr(type(obj), "__module__", "")
            key = f"{tname}"
            if tmod and tmod != "builtins":
                key = f"{tmod}.{tname}"
            if key not in by_type:
                by_type[key] = {"count": 0, "bytes": 0}
            by_type[key]["count"] += 1
            b = _estimate_obj_bytes(obj)
            by_type[key]["bytes"] += b
            total_count += 1
            total_bytes += b
        except Exception:
            pass

    sorted_types = sorted(by_type.items(), key=lambda x: -x[1]["bytes"])[:40]

    lines = []
    lines.append("--- ALL LIVE OBJECTS BY TYPE (top 40) ---")
    lines.append(f"{'Type':<55} {'Count':>8} {'Est. MB':>8} {'%':>6}")
    lines.append("-" * 79)

    for key, data in sorted_types:
        mb = data["bytes"] / 1024 / 1024
        pct = (data["bytes"] / total_bytes * 100) if total_bytes else 0
        lines.append(f"{key:<55} {data['count']:>8} {mb:>8.2f} {pct:>5.1f}%")

    # summarise 3rd-party C / external memory gap
    rss = _get_process_rss()
    gap_mb = (rss - total_bytes) / 1024 / 1024
    if gap_mb > 0:
        lines.append("")
        lines.append(
            f"--- C / non-Python memory (RSS − Python estimate): {gap_mb:.0f} MB ---"
        )
        lines.append(
            "  (GtkWidget C structs, GLib internals, stacks, mmap'd data, etc.)"
        )

    return {
        "lines": lines,
        "by_type": dict(sorted_types),
        "total_count": total_count,
        "total_bytes": total_bytes,
        "gap_mb": gap_mb if gap_mb > 0 else 0,
    }


def _get_module_label(filename: str) -> str:
    if not _is_project_module(filename):
        return "<external>"
    rel = os.path.relpath(filename, PROJECT_ROOT)
    return rel.replace(".py", "").replace("/", ".")


def dump_memory_usage() -> dict:
    global _snapshot_counter
    _snapshot_counter += 1
    gc.collect()

    rss = _get_process_rss()
    snapshot = tracemalloc.take_snapshot()
    growth = (
        snapshot.compare_to(_initial_snapshot, "lineno") if _initial_snapshot else None
    )

    stats = snapshot.statistics("lineno")

    module_totals: dict[str, dict] = {}
    external_stats = {"count": 0, "size": 0}

    for stat in stats:
        filename = stat.traceback[0].filename
        label = _get_module_label(filename)
        if label != "<external>":
            if label not in module_totals:
                module_totals[label] = {"size": 0, "count": 0, "growth": 0}
            module_totals[label]["size"] += stat.size
            module_totals[label]["count"] += stat.count
        else:
            external_stats["size"] += stat.size
            external_stats["count"] += stat.count

    if growth:
        for g in growth:
            filename = g.traceback[0].filename
            label = _get_module_label(filename)
            if label in module_totals:
                module_totals[label]["growth"] += g.size_diff

    sorted_modules = sorted(
        module_totals.items(), key=lambda x: x[1]["size"], reverse=True
    )

    total_size = sum(m["size"] for m in module_totals.values()) + external_stats["size"]
    total_count = (
        sum(m["count"] for m in module_totals.values()) + external_stats["count"]
    )

    lines = []

    def w(s=""):
        lines.append(s)

    # === Process memory ===
    w(f"=== Process RSS: {rss / 1024 / 1024:.1f} MB ===")
    w("")

    # === ALL live objects by type ===
    scan = _scan_all_objects()
    for line in scan["lines"]:
        w(line)
    w("")

    # === Python allocations ===
    w("--- Python Allocations (tracemalloc) ---")
    w(f"{'Module':<50} {'Count':>8} {'Size (MB)':>10} {'Growth (KB)':>12} {'%':>6}")
    w("-" * 88)

    for label, data in sorted_modules:
        size_mb = data["size"] / 1024 / 1024
        growth_kb = data.get("growth", 0) / 1024
        pct = (data["size"] / total_size * 100) if total_size else 0
        w(
            f"{label:<50} {data['count']:>8} {size_mb:>10.2f} {growth_kb:>+12.1f} {pct:>5.1f}%"
        )

    if external_stats["count"]:
        w(
            f"{'<external>':<50} {external_stats['count']:>8} {external_stats['size'] / 1024 / 1024:>10.2f}"
        )

    w("-" * 88)
    w(f"{'TOTAL Python':<50} {total_count:>8} {total_size / 1024 / 1024:>10.2f}")

    out = "\n".join(lines)

    dump_path = f"/tmp/modus_memdump_{_snapshot_counter}.txt"
    with open(dump_path, "w") as f:
        f.write(out + "\n")

    print(out, flush=True)

    return {
        "rss": rss,
        "modules": dict(module_totals),
        "external_count": external_stats["count"],
        "external_size": external_stats["size"],
        "total_size": total_size,
        "total_count": total_count,
    }


if __name__ == "__main__":
    print("Usage: MODUS_MEMTRACE=1 uv run start")
    print("Then:  touch /tmp/modus_dump")
