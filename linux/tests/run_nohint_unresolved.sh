#!/bin/bash
# NO point/box and the label matches nothing on screen (AT-SPI/CDP off): must be REFUSED, never pointed at the placeholder. Real page + real YOLO/OCR, FAKE model.
cd "${TT_TREE:-/home/sandbox/tiptour/linux}"; sed 's/{"open":"Open settings"}/{"open":"Zebra quantum flux"}/' tests/run_cache_nohint.sh > /tmp/nu.sh
RUN_DIR=${RUN_DIR:?} bash /tmp/nu.sh | tee /tmp/nu.out; O=$RUN_DIR
echo "ASSERT no cursor rendered: $(grep -a -q 'render cursor at' $O/stdout.txt && echo False || echo True)"
echo "ASSERT refused (could not resolve): $(grep -a -q 'could not resolve' $O/stdout.txt && echo True || echo False)"
