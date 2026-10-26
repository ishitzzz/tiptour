#!/bin/bash
# usage: snapshot_tree.sh RUN_DIR  -> RUN_DIR/TREE_MANIFEST.txt (sorted "sha256  relpath" of every file under linux/ except __pycache__) + tested-tree.tgz (the exact bytes tested) + env list.
O=$1; cd "$(dirname "${TT_TREE:-/home/sandbox/tiptour/linux}")" || exit 1
( find linux -type f -not -path '*/__pycache__/*' | LC_ALL=C sort | xargs sha256sum ) > $O/TREE_MANIFEST.txt
echo "tree_sha256 $(sha256sum $O/TREE_MANIFEST.txt | cut -d' ' -f1)" >> $O/TREE_MANIFEST.txt
tar --exclude=__pycache__ --sort=name --mtime=@0 --owner=0 --group=0 -czf $O/tested-tree.tgz linux
env | grep -E '^TIPTOUR_' | sed -E 's/(KEY|TOKEN)[^=]*=.*/\1=<redacted>/' | sort > $O/ENV_TIPTOUR.txt
