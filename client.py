import asyncio
from typing import Optional, AsyncGenerator
from contextlib import AsyncExitStack
import hashlib
import json
import os
import time
import logging
 
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

#turn off httpx logging except for errors
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.app")

MODEL = "anthropic/claude-sonnet-4.6"
# MODEL = "anthropic/claude-haiku-4.5"
PHOENIX_API_KEY = os.getenv("PHOENIX_API_KEY")
PHOENIX_MCP_URL = f"https://phoenix.hginsights.com/api/ai/{PHOENIX_API_KEY}/mcp"

logger.info(f"OPENROUTER KEY PRESENT: {bool(os.getenv('OPENROUTER_API_KEY'))}")
logger.info(f"Using model: {MODEL}")    

TOOL_CACHE_TTL = 3600


RESEARCH_SYSTEM_PROMPT="""You are an expert sales intelligence analyst. A sales rep will describe in natural language 
who they are calling and what they are selling. Your job is to research the prospect and 
produce a tight, scannable pre-call brief they can read in under 2 minutes — tailored 
specifically to their product and sales context.

STEP 1 — PARSE THE INPUT
Extract from the rep's message:
- The company domain to research
- What they are selling (product, solution, or category)
- Any other context they gave (e.g. existing customer, known competitor, specific use case)

If no domain is clearly stated but a company name is, infer the most likely domain.

STEP 2 — GATHER DATA
Call these tools using the extracted domain:
1. company_firmographic — size, revenue, industry, location, IT spend
2. company_technographic — full tech stack with intensity and verification dates
3. company_fai — department-level technology breakdown (which teams own which tools)
4. company_intent — active buying signals from the last 30 days
5. company_operating_signals — AI maturity, cloud posture, automation stage
6. contact_search (seniority = ["vp", "c_suite", "director", "head"], limit = 10)

company_fai needs one or a list of products or it will fail. If company_fai returns no data, note it and continue — do not stop.
always limit the number of results returned by the tools.

STEP 3 — ANALYZE THROUGH THE PRODUCT LENS
Before writing a single word of output, reason through these questions internally:
- Which parts of their tech stack create a specific gap or risk relevant to what the rep is selling?
- Which department owns the budget and tooling most relevant to this sale?
- What is the single strongest entry point for THIS rep selling THIS product at THIS company right now?
- Who is the single best first call — not just relevant, but most likely to move?
- What is the one data point that would make a rep say "I didn't know that — that changes my angle"?

This analysis must drive every section. Do not report data. Make arguments.

Before writing, ask: "If I removed all the data from this brief, would there still be an argument?" 
If yes, the brief is reporting, not analyzing. Every section must be unreadable without the data — 
the data is the argument.

GROUNDING RULES:
- Use ONLY data returned by the tools. Never invent facts.
- If a field has no data, write "No data." Never omit a section.
- Every claim must reference actual data from the tools (product name, intensity score, date, stage).

FORMATTING RULES:
- Write money as "384M USD" — never use $ signs (they break markdown rendering)
- Translate raw API enum values into plain English:
    "ai-leader-accelerating" → "AI Leader, accelerating"
    "genai-interested" → "Interested in GenAI"
    "public-cloud-first" → "Public cloud first"
    "autonomous" → "Autonomous (highest stage)"
    "remote-heavy" → "Remote-heavy"
    Apply this to ALL signal stages — never output raw enum strings
- Snapshot table MUST have a header row — use the exact format shown below
- No bold (**) inside parentheses or mid-sentence
- Each bullet is one line max
- No text before the # heading or after the Recommended Opening

WORD BUDGET: The entire output must not exceed 600 words.
If over, cut from Tech Stack and contact descriptions first.
Never cut The Angle, Watch-outs, or Recommended Opening.

CONTACT FILTERING:
From the contacts returned, only include people whose role is plausibly relevant to the sale.
Think about who typically buys, champions, or influences purchases of what the rep is selling.
Exclude: HR, Recruiting, Legal, PR, Admin, Office Management — unless directly relevant.
Max 5 contacts.

---

OUTPUT THIS EXACT STRUCTURE:

# [Company Name] — Pre-Call Brief
*Selling: [what the rep is selling, in their own words]*

## Snapshot
| Field | Value |
|---|---|
| Industry | ... |
| Size | ... |
| Revenue | ... |
| HQ | ... |
| IT Spend | ... |

## Why This Account
2-3 sentences max. Given what the rep is selling, why is this a strong, moderate, or weak fit?
Be direct — reference specific data points, not generalities.
End with a one-line verdict on its own line:
Fit: [Strong / Moderate / Weak] — [one sentence reason tied to actual data]

## The Angle
One sentence. The single strongest entry point for this rep at this company right now.
Not a summary. A strategic bet.
Format: "Lead with [specific pain/gap/signal] because [specific data point] — 
this gives you a reason to call that isn't 'we sell X'."

## Who To Call
Best first call: [Name] — [one sentence on why they move first, tied to The Angle.]

Then list remaining contacts, most relevant first. Max 5 total including the best first call.
**[Full Name]** · [Title] · [City, Country]
→ [One line max. Role relevance + one data point. If not the best first call, 
   start with "Call after [Name] —". No more than 20 words.]

## Tech Stack Relevance
Focus ONLY on technologies relevant to what the rep is selling.
Group into 2-3 meaningful categories. Skip anything not relevant. Max 8 total.

**[Category]**
- [Product] (vendor, last verified [date], intensity [score]) — [phrase this as something 
  a rep could say out loud: a question they could ask or an observation they could make. 
  Not analyst language. One line.]

## Department Breakdown (FAI)
Which departments own the tools most relevant to this sale?
If FAI data is unavailable, write "No FAI data available."
Otherwise list only the 2-3 most relevant departments:
**[Department name]** — [tools they own] → [routing implication: who owns the budget, 
who is likely blocked, which team to enter through]

## Buying Signals
| Signal | Finding |
|---|---|
| Intent (last 30 days) | [topics researched, or "No active signals"] |
| Automation stage | [plain English stage] |
| AI trajectory | [plain English stage] |
| Cloud posture | [plain English stage] |
| Work model | [plain English stage] |

## Watch-outs
Exactly 3 bullets. No more, no less.
Format: "[Risk] → Do: [one specific action]"
Every bullet follows this format. No exceptions.

## Recommended Opening
This is the most important section. Write it to be said out loud on a cold call.
2-3 sentences. Must:
- Open with a specific data point from the research (not the product being sold)
- Connect that data point to a likely pain without stating the obvious
- End with a single open question about their priorities or a known gap in their stack
- Sound like a human who did their homework, not a pitch or a chatbot
- Contain zero placeholders, zero hypotheticals, zero product names"""
 
 
CHAT_SYSTEM_PROMPT = """You are a sales intelligence assistant with full access to HG Insights data tools \
and the pre-call research already done on this company.
 
The sales rep may ask follow-up questions like:
- "Who else should I talk to?"
- "What do they use for X?"
- "How long have they been on Salesforce?"
- "Find me similar companies"
- "What's their cloud spend?"
 
Answer concisely and specifically. Use tools to fetch additional data when the question requires it.
Always tie your answers back to what the rep is selling and their sales context.
Never give generic advice — every answer should be grounded in actual data."""


def convert_tool_format(tool):
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": tool.inputSchema.get("properties", {}),
                "required": tool.inputSchema.get("required", [])
            }
        }
    }
    
def _cache_key(tool_name: str, tool_args: dict) -> str:
    payload = json.dumps({"tool": tool_name, "args": tool_args}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


class MCPClient:
    def __init__(self):
        self.session: Optional[ClientSession] = None
        self.exit_stack = AsyncExitStack()
        self.openai = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=os.getenv("OPENROUTER_API_KEY")
        )
        # Separate message histories for research and chat
        self.research_messages = []
        self.chat_messages = []
        self.current_domain = None
        self.available_tools = []
        self._tool_cache: dict[str, tuple[str, float]] = {}
        
    def _get_cached(self, key: str) -> Optional[str]:
        if key in self._tool_cache:
            result, ts = self._tool_cache[key]
            if time.time() - ts < TOOL_CACHE_TTL:
                return result
            del self._tool_cache[key]
        return None
 
    def _set_cached(self, key: str, result: str):
        self._tool_cache[key] = (result, time.time())
 
    def clear_cache(self):
        self._tool_cache.clear()

    async def connect(self):
        transport = await self.exit_stack.enter_async_context(
            streamable_http_client(PHOENIX_MCP_URL)
        )
        self.read, self.write, _ = transport
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(self.read, self.write)
        )
        await self.session.initialize()

        response = await self.session.list_tools()
        self.available_tools = [convert_tool_format(t) for t in response.tools]
        logger.info(f"Connected to Phoenix MCP — {len(self.available_tools)} tools available")

    async def _run_llm_with_tools(
        self,
        messages: list,
        system: str,
        tools: list,
        log_queue: Optional[asyncio.Queue] = None
    ) -> tuple[str, list]:
        """
        Run LLM with tool loop. If log_queue is provided, emits tool log events:
        {"tool": name, "input": args, "output": result, "cached": bool}
        """
        full_messages = [{"role": "system", "content": system}] + messages
 
        while True:
            completion = self.openai.chat.completions.create(
                model=MODEL,
                tools=tools,
                messages=full_messages
            )
            msg = completion.choices[0].message
            full_messages.append(msg.model_dump())
 
            if not msg.tool_calls:
                return msg.content, full_messages[1:]
 
            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                tool_args = json.loads(tool_call.function.arguments or "{}")
 
                cache_key = _cache_key(tool_name, tool_args)
                logger.debug(f"Tool call requested: {tool_name} with args {tool_args}. Cache key: {cache_key}")
                cached_result = self._get_cached(cache_key)
                was_cached = cached_result is not None
                
                logger.info(f"Tool call: {tool_name}, cached: {was_cached}")
 
                if was_cached:
                    tool_content = cached_result
                else:
                    try:
                        result = await self.session.call_tool(tool_name, tool_args)
                        tool_content = result.content[0].text
                        self._set_cached(cache_key, tool_content)
                    except Exception as e:
                        tool_content = f"Error calling {tool_name}: {e}"
 
                if log_queue is not None:
                    await log_queue.put({
                        "tool": tool_name,
                        "input": tool_args,
                        "output": tool_content,
                        "cached": was_cached
                    })
                     
                full_messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": tool_content
                })
                
    async def research_stream(self, prompt: str) -> AsyncGenerator[dict, None]:
        """
        Yields events as dicts:
          {"type": "tool_log", "tool": ..., "input": ..., "output": ..., "cached": ...}
          {"type": "brief", "content": "...full markdown..."}
        """
        self.current_domain = prompt
        self.research_messages = []
        self.chat_messages = []
        self.research_messages.append({"role": "user", "content": prompt})
 
        log_queue: asyncio.Queue = asyncio.Queue()
 
        async def run():
            brief, updated = await self._run_llm_with_tools(
                self.research_messages,
                RESEARCH_SYSTEM_PROMPT,
                self.available_tools,
                log_queue=log_queue
            )
            self.research_messages = updated
            self.research_messages.append({"role": "assistant", "content": brief})
            self.chat_messages = [
                {
                    "role": "user",
                    "content": (
                        f"My research request was: {prompt}\n\n"
                        f"Here is the pre-call brief that was generated:\n{brief}"
                    )
                },
                {
                    "role": "assistant",
                    "content": "Got it — I have your brief and full research context loaded. What would you like to dig into?"
                }
            ]
            await log_queue.put({"type": "brief", "content": brief})
            await log_queue.put(None)  # sentinel
 
        task = asyncio.create_task(run())
 
        while True:
            event = await log_queue.get()
            if event is None:
                break
            if "type" not in event:
                event["type"] = "tool_log"
            yield event
 
        await task
                

    async def research(self, prompt: str) -> str:
        """Run full pre-call research from a natural language prompt. Returns markdown brief."""
        self.current_domain = prompt
        self.research_messages = []
        self.chat_messages = []
 
        self.research_messages.append({"role": "user", "content": prompt})
 
        brief, updated_messages = await self._run_llm_with_tools(
            self.research_messages,
            RESEARCH_SYSTEM_PROMPT,
            self.available_tools
        )
 
        self.research_messages = updated_messages
        self.research_messages.append({"role": "assistant", "content": brief})
 
        # Seed chat with full context: original prompt + brief
        self.chat_messages = [
            {
                "role": "user",
                "content": (
                    f"My research request was: {prompt}"
                    f"Here is the pre-call brief that was generated:{brief}"
                )
            },
            {
                "role": "assistant",
                "content": "Got it — I have your brief and full research context loaded. What would you like to dig into?"
            }
        ]
 
        return brief

    
    async def chat_stream(self, user_message: str) -> AsyncGenerator[dict, None]:
        """
        Yields events as dicts:
          {"type": "tool_log", "tool": ..., "input": ..., "output": ..., "cached": ...}
          {"type": "message", "content": "...full response text..."}
        """
        if not self.current_domain:
            yield {"type": "message", "content": "Please research a company first before asking follow-up questions."}
            return
 
        self.chat_messages.append({"role": "user", "content": user_message})
 
        log_queue: asyncio.Queue = asyncio.Queue()
 
        async def run():
            response, updated = await self._run_llm_with_tools(
                self.chat_messages,
                CHAT_SYSTEM_PROMPT,
                self.available_tools,
                log_queue=log_queue
            )
            self.chat_messages = updated
            self.chat_messages.append({"role": "assistant", "content": response})
            await log_queue.put({"type": "message", "content": response})
            await log_queue.put(None)  # sentinel
 
        task = asyncio.create_task(run())
 
        while True:
            event = await log_queue.get()
            if event is None:
                break
            if "type" not in event:
                event["type"] = "tool_log"
            yield event
 
        await task
    
    
    async def chat(self, user_message: str) -> str:
        """Handle a follow-up chat message with full research context."""
        if not self.current_domain:
            return "Please research a company first before asking follow-up questions."

        self.chat_messages.append({"role": "user", "content": user_message})

        response, updated_messages = await self._run_llm_with_tools(
            self.chat_messages,
            CHAT_SYSTEM_PROMPT,
            self.available_tools
        )

        self.chat_messages = updated_messages
        self.chat_messages.append({"role": "assistant", "content": response})

        return response

    async def cleanup(self):
        await self.exit_stack.aclose()
