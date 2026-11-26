# Job playbook

## Straight answer on "90% of AI jobs"
No single project can do that. Many AI engineering roles also ask for a degree or years of experience,
software engineering depth, cloud, or machine learning. What this project can do is get you credible for
**junior AI automation, AI workflow, AI solutions and AI product roles**, once the roadmap is done.
"90%" is not a number anyone can promise you.

## What job ads commonly ask for (searched 2026-11-26, mostly vendor and training sites)

| Requirement | Status here | Roadmap item |
|---|---|---|
| Python, REST APIs, webhooks | Built | - |
| Structured output, guardrails, human in the loop | Built | - |
| Evals | Built, small synthetic set | 2-4 |
| RAG / vector database | Keyword retrieval only | 7 |
| Agents and tool calling | Not yet (fixed workflow) | 9 |
| n8n | Workflow file included; check `N8N.md` for its status | 1 |
| MCP | Built (hand-written server) | - |
| Agent frameworks | Not yet | 10 |
| Cloud deploy, Docker, monitoring | Not yet | 5, 11, 12 |
| Zapier / Make | Not covered | Rebuild the intake in Make's free plan |

## Resume bullets (true today)
- Built an AI operations workflow in Python that triages customer messages, drafts replies from company
  documents and routes every one to human approval, with an audit log.
- Added guardrails for prompt injection, unsupported prices and sensitive topics, plus PII masking before model calls.
- Created an evaluation harness with minimum scores enforced in CI, and an MCP server exposing the workflow to AI assistants.

Add numbers only after you measure them (items 2, 3, 15). Only list a skill you can explain.

## Make it yours
This first version was built with an AI coding assistant. Say so if asked, and earn it: read every file,
finish items 1-4 yourself, and be able to change the code live.

## Interview questions to practise
1. Why does nothing send automatically? When would you change that?
2. What happens when the model returns invalid JSON? (`llm.py`, `pipeline.py`)
3. Why are your eval scores optimistic, and how did you fix that?
4. How would a prompt injection get past your checks? What limits the damage?
5. Why BM25 first? What would make you add embeddings?
6. How do you stop a duplicated webhook creating two tickets, or two reviewers sending twice?
7. Rules versus model: cost, latency, accuracy. Which for which step?
8. What breaks at 10,000 messages a day? (synchronous calls, SQLite, no queue, 10k-row stats)

## Applying
- Pin the repo on GitHub, add the live link and video, put both at the top of your CV.
- Post one short write-up per roadmap item on LinkedIn: problem, change, before and after score.
- Offer the pilot to two or three local businesses. One real user beats five more features.
- Apply from item 6 onwards. Do not wait for the whole list.

## Sources for the job-ad table
- https://careers.bluelightcard.co.uk/jobs/8690942-ai-and-automation-engineer
- https://community.n8n.io/t/hiring-ai-automation-engineer-n8n-ai-agent-developer/294904?tl=en
- https://beon.tech/blog/ai-engineer-job-description/
- https://www.simplilearn.com/career-roadmap/ai-automation-engineer-usa
- https://dexity.com/intel/ai-agent-engineer-2026
