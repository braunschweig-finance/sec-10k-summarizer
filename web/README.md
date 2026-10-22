# SEC Terminal: animated web version

A redesigned front end for the SEC Financial & Corporate Governance Terminal. It shows the same numbers as the
Streamlit app (`app.py`), laid out like an analyst's marked-up filing: the hero traces a ratio back to its 10-K lines, ratios count up, and the five-step pipeline draws in as you scroll. Design notes are at the top of `app/globals.css`.

Two parts:

| Folder | What it is | Where it runs |
| --- | --- | --- |
| `web/` | Next.js + Tailwind + Motion site | Vercel (free) |
| `api/` | FastAPI wrapper around the same Python logic as `app.py` (edgartools, ratios, DEF 14A checks, Gemini memo) | Render (free) |

The Streamlit site stays live and untouched until the new one is ready.

## Run it on your computer

```bash
# API
cd api
pip install -r requirements.txt
uvicorn main:app --reload          # http://localhost:8000/api/company/CAT

# Site (in a second terminal)
cd web
npm install
echo NEXT_PUBLIC_API_URL=http://localhost:8000 > .env.local
npm run dev                        # http://localhost:3000
```

Without `NEXT_PUBLIC_API_URL` the site runs on a built-in Caterpillar FY2025 sample (`lib/sample.ts`), clearly labeled.

## Put it online

1. **API on Render.** Sign in at render.com with GitHub, choose New > Blueprint, pick this repo. Render reads
   `render.yaml`. When asked, paste your `GEMINI_API_KEY`. Leave `ALLOWED_ORIGINS` blank for now.
2. **Site on Vercel.** Sign in at vercel.com with GitHub, Add New > Project, pick this repo, set Root Directory to
   `web`, and add the environment variable `NEXT_PUBLIC_API_URL` = your Render address. Deploy.
3. Back on Render, set `ALLOWED_ORIGINS` to your Vercel address so only your site can call the API.

Render's free plan sleeps after 15 minutes idle, so the first lookup after a break takes about a minute.

## Preview build

`npm run preview:build` writes `preview/dist/index.html`, a single-file version that loads React and Motion from a
CDN. It's only for sharing a look without deploying.
