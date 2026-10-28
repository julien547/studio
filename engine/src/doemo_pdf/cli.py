import argparse
import json
import sys

import pikepdf

from .geometry import Rect
from .pdf import compose_diagnostic, inspect_pdf
from .ai_metadata import inspect_ai_metadata
from .settings import templates_dir
from .batch import plan_batch
from .levels import new_document, read_document, validate_document, clip_preview


def main(argv=None):
    parser = argparse.ArgumentParser(description="DOEMO Studio : inspection et composition PDF de diagnostic.")
    commands = parser.add_subparsers(dest="command", required=True)
    directory = commands.add_parser("templates-dir", help="Afficher le dossier privé d'une collection de trames.")
    directory.add_argument("--client", default="doemo", help="Identifiant de collection, doemo par défaut.")
    inspect = commands.add_parser("inspect")
    inspect.add_argument("source")
    native = commands.add_parser("inspect-ai", help="Lire les noms et matrices natives sans exécuter Illustrator.")
    native.add_argument("source")
    batch = commands.add_parser("plan-batch", help="Préparer tous les candidats VEI et associer les trames automatiquement, sans générer de PDF.")
    batch.add_argument("source")
    batch.add_argument("--client", default="doemo")
    init = commands.add_parser('levels-init')
    init.add_argument('source')
    validate = commands.add_parser('levels-validate')
    validate.add_argument('source')
    validate.add_argument('document')
    clip = commands.add_parser('levels-preview')
    clip.add_argument('source')
    clip.add_argument('document')
    clip.add_argument('output')
    clip.add_argument('--mode', choices=['PE', 'PI'], required=True)
    clip.add_argument('--level')
    compose = commands.add_parser("compose-diagnostic", help="Non conforme pour production : page BAT complète conservée.")
    compose.add_argument("source")
    compose.add_argument("template")
    compose.add_argument("output")
    compose.add_argument("--zone", type=float, nargs=4, required=True, metavar=("X0", "Y0", "X1", "Y1"))
    compose.add_argument("--direction", type=float, nargs=2, required=True, metavar=("DX", "DY"))
    compose.add_argument("--page", type=int, default=1)
    compose.add_argument("--margin", type=float, default=12)
    compose.add_argument("--reduce-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "templates-dir":
            directory = templates_dir(args.client)
            result = {"client": args.client, "templates_dir": str(directory), "exists": directory.is_dir()}
        elif args.command == "inspect":
            result = inspect_pdf(args.source)
        elif args.command == "inspect-ai":
            result = inspect_ai_metadata(args.source)
        elif args.command == "plan-batch":
            result = plan_batch(args.source, args.client)
        elif args.command == 'levels-init':
            result = {'document': new_document(args.source)}
        elif args.command == 'levels-validate':
            result = validate_document(args.source, read_document(args.document))
        elif args.command == 'levels-preview':
            result = clip_preview(args.source, read_document(args.document), args.output, args.mode, args.level)
        else:
            result = compose_diagnostic(args.source, args.template, args.output,
                                        Rect(*args.zone), args.direction, args.page-1,
                                        args.margin, not args.reduce_only)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, OSError, pikepdf.PdfError) as error:
        print(json.dumps({"status": "blocked", "error": str(error), "production_ready": False}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
