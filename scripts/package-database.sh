#!/bin/sh
# Run the documented static/integration gates before invoking this packaging step.
set -eu
mkdir -p artifacts
python3 - <<'PY'
import gzip
from pathlib import Path
import tarfile

roots = ["README.md", "AGENTS.md", "user-stories.md", ".env.example",
         "compose.yaml", "compose.test.yaml", "database", "scripts", "docs"]
files = []
for name in roots:
    path = Path(name)
    files.extend(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else files.append(path)
with Path("artifacts/database-foundation.tar.gz").open("wb") as output:
    with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for path in sorted(files):
                if "__pycache__" in path.parts or path.suffix == ".pyc":
                    continue
                info = archive.gettarinfo(str(path))
                info.mtime = info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o755 if path.suffix == ".sh" else 0o644
                with path.open("rb") as content:
                    archive.addfile(info, content)
PY
shasum -a 256 artifacts/database-foundation.tar.gz > artifacts/database-foundation.tar.gz.sha256
