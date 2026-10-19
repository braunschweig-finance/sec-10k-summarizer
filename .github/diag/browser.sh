#!/bin/bash
# Same calls the page makes: company, then governance + pay efficiency together, then trends. Per ticker in $@.
B=http://localhost:8000
for t in "$@"; do
  curl -s -o /dev/null -w "$t company %{http_code} %{time_total}s\n" --max-time 150 $B/api/company/$t
  curl -s -o /dev/null -w "$t governance %{http_code} %{time_total}s\n" --max-time 150 $B/api/governance/$t &
  curl -s -o /dev/null -w "$t pay-eff %{http_code} %{time_total}s\n" --max-time 150 $B/api/pay-efficiency/$t
  curl -s -o /dev/null -w "$t trends %{http_code} %{time_total}s\n" --max-time 150 $B/api/trends/$t
  wait
  echo "$t container: $(docker inspect -f 'running={{.State.Running}} oom={{.State.OOMKilled}} restarts={{.RestartCount}}' api) anon_now=$(docker exec api grep '^anon ' /sys/fs/cgroup/memory.stat 2>/dev/null | awk '{printf "%d MiB", $2/1048576}')"
done
