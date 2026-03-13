# ⚡ Pre-Call Intel
> AI-powered sales intelligence agent. Type a company name, get a full pre-call brief in seconds.

Built with Streamlit + HG Insights MCP + OpenRouter (Claude).

---

## What it does
Type something like _"I have a call with stripe.com in 20 minutes"_ and the agent:
1. Pulls firmographic data (size, revenue, industry)
2. Maps their full tech stack
3. Checks buying intent signals
4. Finds operating signals (AI maturity, automation stage)
5. Surfaces relevant contacts to call
6. Synthesizes everything into a structured brief with talking points

---

## Local setup

```bash
git clone <your-repo>
cd <your-repo>

pip install -r requirements.txt

cp .env.example .env
# Edit .env with your keys

streamlit run app.py
```

Open http://localhost:8501 — enter your keys in the sidebar and start chatting.

---

## Deploy to Streamlit Cloud (free, 2 minutes)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Click **New app** → select your repo → `app.py`
4. Under **Advanced settings → Secrets**, add:
   ```toml
   HG_API_KEY = "your-hg-insights-key"
   OPENROUTER_API_KEY = "sk-or-your-key"
   ```
5. Click **Deploy** → share the link ✓

No server, no Docker, no setup required for viewers.

---

## Keys needed
| Key | Where to get it |
|-----|----------------|
| `HG_API_KEY` | Phoenix dashboard → MCP section |
| `OPENROUTER_API_KEY` | openrouter.ai → Keys |

---

## Example queries
- `"I have a call with notion.so in 30 min"`
- `"Prep me for Salesforce"`
- `"Who should I reach out to at stripe.com?"`
- `"What's 2-times.com's tech stack?"`
- `"Are there any buying signals at hubspot.com?"`

---

## Tech stack
- **Frontend + Backend**: Streamlit (single Python file)
- **LLM**: Claude via OpenRouter
- **Data**: HG Insights Phoenix MCP (firmographic, technographic, intent, operating signals, contacts)
- **Deployment**: Streamlit Cloud
