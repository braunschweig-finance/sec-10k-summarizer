# Temporary diagnostic: peak memory and time of each API lookup, one fresh process per step
import json, resource, subprocess, sys, time
STEPS = ["get_financial_report", "get_governance_report", "get_pay_efficiency", "get_trends"]
if len(sys.argv) == 3:
    sys.path.insert(0, "api")
    import sec_core
    base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t = time.time()
    err = None
    try:
        getattr(sec_core, sys.argv[2])(sys.argv[1])
    except Exception as e:
        err = repr(e)[:300]
    print(json.dumps({"ticker": sys.argv[1], "step": sys.argv[2], "seconds": round(time.time() - t, 1),
                      "import_mb": round(base / 1024), "peak_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024), "error": err}), flush=True)
else:
    for tk in sys.argv[1].split(","):
        for s in STEPS:
            subprocess.run([sys.executable, __file__, tk, s])
