"""UTF-8 JSON/text IO shared by CLI entrypoints; single-writer atomic replacement."""
import json
import os
from pathlib import Path
import tempfile


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))



def save(path, value, replace=True):
    """Atomic replacement by the one owning process; init never overwrites."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if not replace:
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        return
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
