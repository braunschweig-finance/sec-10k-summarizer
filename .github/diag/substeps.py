import resource, sys, time
sys.path.insert(0, "api")
import sec_core
from edgar import Company
def mb(): return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
t = sys.argv[1]; what = sys.argv[2]
print(t, what, "after import", mb(), flush=True)
c = Company(t); print("Company()", mb(), flush=True)
if what == "gov":
    p = c.get_filings(form="DEF 14A")[0]; print("get_filings", mb(), flush=True)
    h = p.html(); print("html() bytes", len(h or ""), mb(), flush=True)
    txt = p.text(); print("text()", len(txt), mb(), flush=True)
else:
    f = c.get_financials(); print("get_financials", mb(), flush=True)
    f.income_statement(); print("income", mb(), flush=True)
    f.balance_sheet(); print("balance", mb(), flush=True)
    f.cash_flow_statement(); print("cashflow", mb(), flush=True)
