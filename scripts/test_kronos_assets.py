import argparse
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1] / "database"


def resolve_asset(path_str: str | None) -> tuple[str, str] | None:
    if not path_str:
        return None
    raw = Path(path_str)
    if raw.is_absolute():
        full_path = raw
    else:
        raw_str = str(raw).replace("\\", "/")
        if raw_str.startswith("database/"):
            rel_part = raw_str[len("database/") :]
            full_path = BASE_DIR / rel_part
        else:
            full_path = (BASE_DIR / raw).resolve()
    full_path = full_path.resolve()
    if not full_path.exists():
        return None
    relative = full_path.relative_to(BASE_DIR).as_posix()
    return relative, f"/assets/{relative}"


def inspect(metadata_path: Path) -> None:
    meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    print(f"Metadata: {metadata_path.relative_to(BASE_DIR)}")
    for label, value in (
        ("input_csv", meta.get("input_csv")),
        ("prediction_csv", meta.get("output_files", {}).get("csv")),
        ("plot", meta.get("output_files", {}).get("plot")),
    ):
        resolved = resolve_asset(value)
        if resolved:
            rel, url = resolved
            print(f"  {label:14s} -> rel={rel}  url={url}")
        else:
            print(f"  {label:14s} -> missing or not found ({value})")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect Kronos metadata asset paths")
    parser.add_argument("symbol", nargs="?", default=None, help="Optional symbol filter (e.g. COIN)")
    args = parser.parse_args()

    if not BASE_DIR.exists():
        raise SystemExit(f"database directory not found at {BASE_DIR}")

    metas = sorted(BASE_DIR.glob("*/**/Kronos_output/*_metadata_*.json"))
    if args.symbol:
        metas = [p for p in metas if f"/{args.symbol.upper()}/" in p.as_posix()]

    if not metas:
        print("No metadata files found")
        return

    for path in metas:
        inspect(path)


if __name__ == "__main__":
    main()
