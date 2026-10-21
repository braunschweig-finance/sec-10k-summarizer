# Running the app's AI for free (local AI)

Every AI task in the API goes through `api/ai_client.py`. Where the AI runs is set by four environment variables,
so the same code works with a model on your laptop, a university GPU server, or a paid API.

| Setting | What it does | Example |
|---|---|---|
| `AI_PROVIDER` | `lmstudio`, `ollama`, `openai`, `gemini` or `custom` | `lmstudio` |
| `AI_BASE_URL` | OpenAI-compatible address (needed for `custom`) | `https://gpu.example.edu/v1` |
| `AI_MODEL` | Model name (LM Studio/Ollama: optional, uses the loaded one) | `qwen3-4b` |
| `AI_API_KEY` | Key, if the server needs one | |

With nothing set, the API uses Gemini when `GEMINI_API_KEY` is set (the live site today), otherwise LM Studio.

## On a laptop with LM Studio

1. Install LM Studio from https://lmstudio.ai and open it.
2. Search for and download a small instruct model that LM Studio marks as fitting your machine
   (on a 16 GB laptop without a graphics card: a 3B to 4B model at Q4).
3. Developer tab (the `>_` icon) > Start Server. It listens on `http://localhost:1234/v1`.
4. From the `api/` folder: `python governance_policies.py CAT`

## Which model for which machine

| Machine | Model size | Speed |
|---|---|---|
| Laptop, 16 GB RAM, no graphics card (CPU only) | 3B to 4B, Q4 (about 2.5 GB) | a few words per second |
| Laptop or PC, 32 GB RAM, or an 8 to 12 GB graphics card | 7B to 14B, Q4 | usable |
| University GPU server (24 to 80 GB per GPU) | 30B to 70B | close to paid APIs |

LM Studio shows whether each model fits your hardware before you download it.

## On a university GPU server

Most servers run vLLM or Ollama, which speak the same format. Ask the admin for the address and a key, then:

```
AI_PROVIDER=custom
AI_BASE_URL=<address ending in /v1>
AI_API_KEY=<key>
AI_MODEL=<model name they host>
```

## What uses it

- `POST /api/memo`: the research memo.
- `GET /api/governance-policies/{ticker}`: ten governance policies read from the proxy (independent chair,
  annual elections, majority voting, proxy access, special meetings, written consent, poison pill, pledging ban,
  clawback scope, CEO ownership guideline). Each answer comes with a quote, and the quote is checked word for word
  against the filing; an answer whose quote isn't in the filing doesn't count toward the score.
- `GET /api/ai-status`: which provider and model the server is set to (never the key).
