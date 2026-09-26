#!/bin/bash
# GCE startup: run the multi-season cloud-seeding evaluation (SNOTEL via AWDB + HRRR winds via S3 byte ranges) and upload results.
exec > >(tee -a /var/log/seeding.log) 2>&1
apt-get -qq update && apt-get -qq install -y python3-pip python3-eccodes libeccodes0 >/dev/null
pip3 install -q --break-system-packages pandas pyarrow numpy requests eccodes 2>&1 | tail -1
B=gs://oceanmap-seabed/cloud-seeding; mkdir -p /work && cd /work && gsutil -q -m cp -r $B/code/* . && mkdir -p data && gsutil -q -m cp -r $B/data/* data/
ls; python3 -c "import eccodes; print('eccodes ok')"
python3 multi_season.py 2>&1 | tail -80
gsutil -q -m cp data/v23-multi-season-results.json data/v23-multi-panel.parquet data/storm-results-*.json data/storm-per-event-*.csv data/event-winds-*.csv data/.wind_cache.json $B/results/ 2>/dev/null
gsutil -q -m cp -r data/.local_snotel $B/results/local_snotel 2>/dev/null
gsutil -q cp /var/log/seeding.log $B/results/seeding-vm.log; echo "SEEDING DONE"; shutdown -h now
