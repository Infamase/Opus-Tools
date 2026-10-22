"""Data tools (WP-F): ``data_fetch``; CLI ``opus data fetch|build|list`` (docs/S0B_DESIGN.md §13,
§14, §15). ``opus data build`` is v0.4's command moved here unchanged; ``data_fetch`` and
``data list`` are WP0 stubs until WP-F replaces the bodies.
"""

from __future__ import annotations

from opus.tools import emit, not_built

PACKAGE = "WP-F"


def data_fetch(pack: str = "", from_file: str = "", record: str = "", licence_page: str = "",
               list: bool = False) -> str:
    """Fetch a data pack into the library folder (manifest data/packs.yaml; sha256-checked, resumable,
    licence page snapshotted, lineage recorded). pack: a pack id; from_file: a manually downloaded
    file for that pack (kind manual, e.g. albion_typology); record: one museum record such as
    "met:23367" or "cma:1921.1252"; licence_page: a URL or saved HTML to snapshot with from_file;
    list: list the packs and their status. OPUS_OFFLINE=1 makes every fetch fail fast. Returns
    {"pack", "dir", "files": [{"path","sha256","size"}], "licence_id", "flags", "licence_json", "status"}."""
    raise not_built("data_fetch", PACKAGE)


def register(tool) -> None:
    tool(data_fetch)


def add_cli(sub, groups) -> None:
    g = groups["data"]
    s = g.add_parser("fetch", help="fetch a data pack or a museum record into the library")
    s.add_argument("--pack", default="")
    s.add_argument("--from-file", default="")
    s.add_argument("--record", default="")
    s.add_argument("--licence-page", default="")
    s.add_argument("--list", action="store_true", help="list the packs and their status")

    s = g.add_parser("build", help="rebuild the committed fact tables (maintainers)")
    s.add_argument("--tables", action="store_true", required=True)
    s.add_argument("--ansur", default="", help="folder with ANSUR_II_MALE/FEMALE_Public.csv")
    s.add_argument("--out", default="", help="write here instead of data/tables")

    g.add_parser("list", help="the data packs and their status")


def run_cli(args) -> int | None:
    if args.cmd != "data":
        return None
    if args.data_cmd == "build":
        from opus.tables import build_tables

        emit(build_tables(args.ansur or None, args.out or None))
        return 0
    if args.data_cmd == "fetch":
        emit(data_fetch(args.pack, args.from_file, args.record, args.licence_page, list=args.list))
        return 0
    if args.data_cmd == "list":
        emit(data_fetch(list=True))
        return 0
    return None
