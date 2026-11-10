import type {ScreenerData} from "./screener";

/** Project only rows or confirmed missing tickers already present in one response. */
export function localComparison(data:ScreenerData,tickers:readonly string[]):ScreenerData|null {
  if (!data.available || tickers.length>4 || new Set(tickers).size!==tickers.length || tickers.some(t=>!t.trim())) return null;
  const known=new Map([...data.rows,...(data.comparison?.rows??[])].map(row=>[row.ticker,row]));
  const missing=new Set(data.comparison?.missing??[]);
  if (tickers.some(ticker=>!known.has(ticker)&&!missing.has(ticker))) return null;
  const {comparison:previous,...rest}=data;
  void previous;
  return tickers.length ? {...rest,comparison:{tickers:[...tickers],rows:tickers.flatMap(t=>known.has(t)?[known.get(t)!]:[]),missing:tickers.filter(t=>!known.has(t))}} : rest;
}
