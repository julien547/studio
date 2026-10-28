"""Isolated, bounded parser/recognizer process. No shell or arbitrary operation names."""
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

LOCK = threading.Semaphore(1)


def run_job(operation, data, timeout=180):
    with LOCK, tempfile.TemporaryDirectory(prefix="doemo-job-") as tmp:
        args = Path(tmp) / "input.json"
        args.write_text(json.dumps(data))
        env = dict(os.environ, OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
        try:
            p = subprocess.run([sys.executable, "-m", "doemo_releves.worker", operation, str(args)],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise ValueError("Traitement interrompu : délai dépassé") from e
        if p.returncode or len(p.stdout) > 16*1024**2:
            raise ValueError("Traitement interrompu par une limite de ressources ou un fichier invalide")
        try:
            response = json.loads(p.stdout)
        except json.JSONDecodeError as e:
            raise ValueError("Réponse de traitement invalide") from e
        if "error" in response:
            raise ValueError(response["error"])
        return response["result"]


def main():
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (3*1024**3, 3*1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (150, 155))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128*1024**2, 128*1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    operation, input_path = sys.argv[1:]
    data = json.loads(Path(input_path).read_text())
    try:
        if operation == "document":
            from .documents import prepare_document
            result = prepare_document(**data)
        elif operation == "library":
            from .library import import_library
            result = import_library(**data)
        elif operation == "recognition":
            from .documents import rgb
            from .recognition import local_proposals, multimodal_proposals
            from .models import Box
            if data.pop("mode") == "multimodal":
                proposals, report = multimodal_proposals(data["image_path"], data["document_id"], data["page"])
            else:
                proposals, report = local_proposals(rgb(data["image_path"]), data["document_id"], data["page"],
                    Box.model_validate(data["legend_box"]) if data.get("legend_box") else None)
            result = {"annotations": [a.model_dump() for a in proposals], "report": report}
        elif operation == "automatic":
            from .documents import rgb
            from .registration import automatic
            result = automatic(rgb(data["source"]), rgb(data["target"]))
        else:
            raise ValueError("Opération inconnue")
        print(json.dumps({"result": result}, ensure_ascii=False))
    except (ValueError, OSError, KeyError, RuntimeError) as e:
        # Error details stay local; API substitutes generic messages for file internals.
        print(json.dumps({"error": str(e)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
