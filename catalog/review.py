"""Build the reviewer's shortlist, and record what the reviewer approved.

  python catalog/review.py build
      Reads catalog/picks.tsv (draft id, display title, optional shorter credit)
      and catalog/drafts.jsonl,
      and writes catalog/catalog.json (the manifest, nothing approved) and
      catalog/REVIEW.md (the numbered list a person watches and chooses from).

  python catalog/review.py approve --reviewer NAME --numbers 1,2,5 [--keep-sound 2]
      Marks those numbers approved, fact-checked, age-appropriate and rights
      cleared by NAME, keeps the original sound on --keep-sound numbers, and
      leaves every other entry unapproved. Only run it with the numbers the
      reviewer chose themselves.

Then: python scripts/discover_catalog.py validate --manifest catalog/catalog.json
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
from discover_catalog import MAX_SECONDS  # noqa: E402

MANIFEST = HERE / "catalog.json"


def build():
    drafts = {}
    for line in (HERE / "drafts.jsonl").read_text().splitlines():
        if line.strip():
            entry = json.loads(line)
            drafts[entry["id"]] = entry
    entries, missing = [], []
    for line in (HERE / "picks.tsv").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        draft_id, title, *credit = line.split("\t")
        if draft_id not in drafts:
            missing.append(draft_id)
            continue
        entry = {k: v for k, v in drafts[draft_id].items() if k not in ("blockers", "query")}
        if drafts[draft_id].get("blockers"):
            missing.append(f"{draft_id} ({'; '.join(drafts[draft_id]['blockers'])})")
            continue
        entry["sourceTitle"], entry["title"] = entry["title"], title
        if credit:
            # A long author list abbreviated the usual way ("et al.").
            entry["source"] = {**entry["source"], "credit": credit[0], "sourceCredit": entry["source"]["credit"]}
        entries.append(entry)
    MANIFEST.write_text(json.dumps({"entries": entries}, indent=2, ensure_ascii=False) + "\n")

    lines = ["# Discover library: videos to review", "",
             "Watch each one from its link. Approving a number means it is accurate, suitable for",
             "learners, and fine to show with the credit listed. Silent ones are published without",
             "their soundtrack unless you check it has no music and ask to keep it.", ""]
    subject = None
    for number, entry in enumerate(entries, 1):
        if entry["subject"] != subject:
            subject = entry["subject"]
            lines += ["", f"## {subject}", ""]
        seconds = entry["probe"]["duration"]
        minutes = f"{int(seconds // 60)}:{int(seconds % 60):02d}"
        length = f"{seconds:.0f}s" if seconds <= MAX_SECONDS else f"first {MAX_SECONDS}s of {minutes}"
        sound = "silent" if entry["clip"]["audio"] == "mute" or not entry["probe"]["audio"] else "with sound"
        source = entry["source"]
        lines.append(f"{number}. **{entry['title']}**: {length}, {sound}. "
                     f"{source['credit']}, {source['license']}. [Watch]({source['pageUrl']})")
    (HERE / "REVIEW.md").write_text("\n".join(lines) + "\n")
    print(f"{len(entries)} entries in the shortlist")
    for item in missing:
        print(f"left out: {item}")
    return 0


def numbers(text):
    return {int(n) for n in text.split(",") if n.strip()}


def approve(reviewer, chosen, keep_sound):
    data = json.loads(MANIFEST.read_text())
    entries = data["entries"]
    unknown = sorted(n for n in chosen | keep_sound if not 1 <= n <= len(entries))
    if unknown:
        raise SystemExit(f"no such numbers: {unknown}")
    for number, entry in enumerate(entries, 1):
        ok = number in chosen
        entry["review"].update({"approved": ok, "factChecked": ok, "ageAppropriate": ok,
                                "rightsCleared": ok, "reviewer": reviewer if ok else None})
        if number in keep_sound:
            entry["clip"]["audio"] = "keep"
    MANIFEST.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(chosen)} of {len(entries)} approved by {reviewer}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("build")
    mark = sub.add_parser("approve")
    mark.add_argument("--reviewer", required=True)
    mark.add_argument("--numbers", required=True, type=numbers)
    mark.add_argument("--keep-sound", default=set(), type=numbers)
    args = parser.parse_args(argv)
    if args.command == "build":
        return build()
    return approve(args.reviewer, args.numbers, args.keep_sound)


if __name__ == "__main__":
    sys.exit(main())
