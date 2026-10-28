import argparse
import json
import os
from pathlib import Path
import shutil
import uuid
from .store import Store
from .worker import run_job
from .models import Annotation, ProjectState
from .exchange import report


def main():
    parser = argparse.ArgumentParser(description="DOEMO Relevés : bibliothèque et audit réel, stockage privé")
    parser.add_argument("--data", default=os.environ.get("DOEMO_RELEVES_DATA", "/var/lib/doemo-studio/releves"))
    sub = parser.add_subparsers(dest="command", required=True)
    lib = sub.add_parser("import-library")
    lib.add_argument("inventory")
    lib.add_argument("--archive")
    audit = sub.add_parser("audit")
    audit.add_argument("survey")
    audit.add_argument("--target", required=True)
    audit.add_argument("--owner", required=True)
    audit.add_argument("--library-id")
    audit.add_argument("--name", default="Audit relevé fourni")
    audit.add_argument("--output", required=True)
    args = parser.parse_args()
    store = Store(args.data)
    if args.command == "import-library":
        ident = uuid.uuid4().hex
        result = run_job("library", {"inventory_file": str(Path(args.inventory).resolve()),
             "archive": str(Path(args.archive).resolve()) if args.archive else None,
             "output": str(store.root/"libraries"/ident)}, timeout=300)
        result["id"] = ident
        store.put_library(result)
        print(json.dumps({"id": ident, "counts": result["counts"], "archive_verified": result["archive_verified"],
                          "native_resources": sum(a["verified"] for a in result["assets"]),
                          "previews": sum(a["preview"] for a in result["assets"])}, ensure_ascii=False))
        return
    project_id = store.create(args.owner, args.name)
    state = ProjectState(revision=0, library_id=args.library_id)
    for role, file in [("survey", args.survey), ("target", args.target)]:
        ident = uuid.uuid4().hex
        directory = store.root/"documents"/ident
        directory.mkdir(parents=True, mode=0o700)
        shutil.copyfile(file, directory/"original")
        meta = run_job("document", {"path": str(directory/"original"), "directory": str(directory),
                                   "original_name": Path(file).name, "role": role})
        with store.connect() as c:
            c.execute("INSERT INTO documents VALUES(?,?,?)", (ident, project_id, json.dumps(meta)))
        if role == "survey":
            for page in meta["pages"]:
                result = run_job("recognition", {"image_path": str(directory/f"page-{page['number']}.png"),
                    "document_id": ident, "page": page["number"], "mode": "local"})
                (directory/f"analysis-{page['number']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
                state.annotations.extend(Annotation.model_validate(a) for a in result["annotations"])
    store.save(project_id, args.owner, state, "real-file-audit")
    output = store.get(project_id, args.owner)
    output["report"] = report(ProjectState.model_validate(output["state"]))
    Path(args.output).write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(json.dumps({"project_id": project_id, "report": output["report"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
