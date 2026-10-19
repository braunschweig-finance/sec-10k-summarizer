# Old 10-K read (edgartools get_financials) vs the XBRL-only read: same JSON? peak memory of each?
import json, resource, subprocess, sys
if len(sys.argv) == 3:
    sys.path.insert(0, "api")
    import sec_core
    t, how = sys.argv[1], sys.argv[2]
    if how == "old":
        sec_core.latest_tenk_financials = lambda c: c.get_financials()
    before = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
    r = sec_core.get_financial_report(t)
    json.dump(r, open(f"/tmp/{t}_{how}.json", "w"), sort_keys=True)
    print(f"{t} {how}: peak {round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)} MiB (after import {before})", flush=True)
else:
    for t in sys.argv[1].split(","):
        for how in ["old", "new"]:
            subprocess.run([sys.executable, __file__, t, how])
        subprocess.run(["bash", "-c", f"cmp -s /tmp/{t}_old.json /tmp/{t}_new.json && echo '{t}: identical output' || (echo '{t}: OUTPUT DIFFERS'; diff <(python -m json.tool /tmp/{t}_old.json) <(python -m json.tool /tmp/{t}_new.json) | head -20)"])
