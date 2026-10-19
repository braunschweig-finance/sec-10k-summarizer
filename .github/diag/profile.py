# Peak memory of one way of reading a filing, in a fresh process
import resource, subprocess, sys, time
def mb(): return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)
if len(sys.argv) == 3:
    t, how = sys.argv[1], sys.argv[2]
    sys.path.insert(0, "api")
    import sec_core
    from edgar import Company
    c = Company(t)
    base = mb()
    started = time.time()
    out = ""
    if how == "fin":
        f = c.get_financials(); f.income_statement(); f.balance_sheet(); f.cash_flow_statement()
    else:
        p = sec_core.latest_filings(c, "DEF 14A")[0]
        if how == "text":
            out = p.text()
        elif how == "direct":
            url = f"https://www.sec.gov/Archives/edgar/data/{int(c.cik)}/{p.accession_no.replace('-', '')}/{p.primary_document}"
            raw = sec_core.sec_fetch(url)
            print("  primary doc bytes", len(raw), flush=True)
            from edgar.documents import HTMLParser, ParserConfig
            doc = HTMLParser(ParserConfig(form=p.form)).parse(raw.decode("utf-8", errors="ignore"))
            out = doc.text(table_max_col_width=500)
        elif how == "lxml":
            url = f"https://www.sec.gov/Archives/edgar/data/{int(c.cik)}/{p.accession_no.replace('-', '')}/{p.primary_document}"
            out = sec_core.html_to_plain_text(sec_core.sec_fetch(url))
        elif how == "full":
            out, _ = sec_core.get_proxy_text(p)
        open(f"/tmp/{t}_{how}.txt", "w").write(sec_core.clean_governance_text(out))
    print(f"{t} {how}: before {base} MiB, peak {mb()} MiB, +{mb()-base}, {time.time()-started:.1f}s, chars {len(out)}", flush=True)
else:
    for t in sys.argv[1].split(","):
        for how in ["fin", "full", "text", "direct", "lxml"]:
            subprocess.run([sys.executable, __file__, t, how])
        subprocess.run(["bash", "-c", f"cmp -s /tmp/{t}_text.txt /tmp/{t}_direct.txt && echo '{t}: direct text identical' || echo '{t}: direct text differs'"])
