// Screenshots the built site (out/ served on a port) with live API data. API calls go through Node, so CORS doesn't apply.
import { chromium } from "playwright";
const [, , tag, port, dir] = process.argv;
const API = "https://sec-terminal-api.onrender.com";
const b = await chromium.launch();
for (const [w, h, name] of [[1440, 1000, "desktop"], [390, 844, "mobile"]]) {
  const ctx = await b.newContext({ viewport: { width: w, height: h } });
  await ctx.route(`${API}/**`, async (route) => {
    const res = await route.fetch({ timeout: 170000 });
    await route.fulfill({ response: res, headers: { ...res.headers(), "access-control-allow-origin": "*" } });
  });
  const p = await ctx.newPage();
  p.setDefaultTimeout(170000);
  await p.goto(`http://localhost:${port}/`, { waitUntil: "networkidle" });
  await p.waitForTimeout(2000);
  await p.screenshot({ path: `${dir}/${tag}-${name}-hero.png` });
  await p.fill("#ticker", "MSFT");
  await p.keyboard.press("Enter");
  await p.getByRole("tab", { name: "Grade" }).waitFor();
  await p.waitForTimeout(15000);
  await p.screenshot({ path: `${dir}/${tag}-${name}-ratios.png`, fullPage: true });
  const tabs = name === "desktop" ? ["Grade", "Fair Value", "Trends", "Compare", "10-K Summary", "Statements", "Governance", "Red Flags & Insiders", "Earnings Tone"] : ["Grade", "Trends"];
  for (const t of tabs) {
    await p.getByRole("tab", { name: t, exact: true }).click();
    await p.waitForTimeout(20000);
    if (t === "Compare") { await p.getByRole("button", { name: "AAPL", exact: true }).last().click(); await p.waitForTimeout(15000); }
    await p.screenshot({ path: `${dir}/${tag}-${name}-${t.replace(/[^A-Za-z0-9]+/g, "-")}.png`, fullPage: true });
  }
  await ctx.close();
}
await b.close();
