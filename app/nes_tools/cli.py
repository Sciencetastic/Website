"""Command line: python -m nes_tools {audit|convert|batch-audit} ..."""
import argparse
import csv
import glob
import os
import sys

from . import pipeline
from .audit import audit_image, save_report, summary_lines
from .palette import from_hex


def _bd(s):
    return from_hex(s) if s.startswith("#") or len(s) == 6 else (0, 0, 0)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="nes_tools")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit", help="audit an image (or a folder of PNGs)")
    a.add_argument("path"); a.add_argument("--report-dir"); a.add_argument("--origin", nargs=2, type=int, default=(0, 0))
    a.add_argument("--backdrop", default="000000"); a.add_argument("--budget", type=int, default=192)
    a.add_argument("--nearblack", type=int, default=0)
    c = sub.add_parser("convert", help="make an image NES-compliant")
    c.add_argument("src"); c.add_argument("dst")
    c.add_argument("--mode", choices=["conform", "gb"], default="conform")
    c.add_argument("--backdrop", default="black"); c.add_argument("--origin", nargs=2, type=int, default=(0, 0))
    c.add_argument("--tile-budget", type=int, default=0); c.add_argument("--max-colors", type=int, default=24)
    c.add_argument("--reference"); c.add_argument("--ref-method", choices=["auto", "aligned", "palette"], default="auto")
    c.add_argument("--theme", default="auto"); c.add_argument("--crop", nargs=4, type=int)
    args = ap.parse_args(argv)

    if args.cmd == "audit":
        paths = sorted(glob.glob(os.path.join(args.path, "*.png"))) if os.path.isdir(args.path) else [args.path]
        rows = []
        for p in paths:
            res, canvas = audit_image(p, tuple(args.origin), _bd(args.backdrop), args.budget, args.nearblack)
            print("%-40s %s groups=%d conflicts=%d patterns>=%d" % (os.path.basename(p), "PASS" if res["palette_pass"] else "FAIL",
                  res["groups_needed"], res["conflict_blocks"], res["tiles"]["pattern_lower_bound"]))
            if args.report_dir:
                save_report(args.report_dir, os.path.splitext(os.path.basename(p))[0], canvas, res, p)
            rows.append([os.path.basename(p), res["palette_pass"], res["groups_needed"], res["conflict_blocks"],
                         res["tiles"]["pattern_lower_bound"]])
        if args.report_dir and len(paths) > 1:
            with open(os.path.join(args.report_dir, "summary.csv"), "w", newline="") as fh:
                w = csv.writer(fh); w.writerow(["file", "pass", "groups", "conflict_blocks", "pattern_lower_bound"]); w.writerows(rows)
        return 0 if all(r[1] for r in rows) else 1
    opt = pipeline.Options(mode=args.mode, backdrop=args.backdrop, origin=tuple(args.origin), tile_budget=args.tile_budget,
                           max_colors=args.max_colors, use_reference=bool(args.reference), reference=args.reference,
                           ref_method=args.ref_method, theme=args.theme, crop=tuple(args.crop) if args.crop else None)
    r = pipeline.run(args.src, opt)
    r.image.save(args.dst)
    print("\n".join(summary_lines(r.audit)))
    for n in r.notes:
        print(" -", n)
    return 0 if r.audit["palette_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
