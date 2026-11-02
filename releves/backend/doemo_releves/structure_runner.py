"""Executed by the explicitly configured, existing reconstruction Python environment."""
import hashlib
import json
from pathlib import Path
import resource
import sys


def main():
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    resource.setrlimit(resource.RLIMIT_CPU, (170, 175))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    args = json.loads(Path(sys.argv[1]).read_text())
    source = Path(args['source'])
    if hashlib.sha256(source.read_bytes()).hexdigest() != args['source_sha256']:
        raise ValueError('Source modifiée')
    from PIL import Image
    with Image.open(source) as image:
        if image.format != 'PNG' or list(image.size) != [args['width'], args['height']] or image.width * image.height > 20_000_000:
            raise ValueError('Repère source invalide')
    sys.path.insert(0, args['module_path'])
    from doemo_reconstruction.extract import reconstruct
    result = reconstruct(source, pages=[1])
    Path(args['output']).write_text(json.dumps(result, ensure_ascii=False, allow_nan=False))


if __name__ == '__main__':
    main()
