#!/bin/bash
# usage: tools/run_manifest.sh RUN_DIR  -> RUN_DIR/MANIFEST.txt with the code version and sha256 + size of EVERY file in the run dir (except MANIFEST.txt itself)
D=$1; cd "$D" || exit 2
{ echo "run: $(basename "$PWD")"; echo "generated: $(date -Is)"; echo "code_version(sha256 of git diff of linux/ at generation time, may differ from the build that produced the run): ${CODE_VERSION:-unset}"
  find . -type f ! -name MANIFEST.txt | sort | while read f; do printf '%s  %9d  %s\n' "$(sha256sum "$f" | cut -d' ' -f1)" "$(stat -c %s "$f")" "$f"; done; } > MANIFEST.txt
