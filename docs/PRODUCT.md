# Product brief

## Problem (hypothesis, not yet researched)
A small food business takes orders, questions and complaints as chat messages. The owner answers each
by hand, details get missed, and urgent complaints sit beside price questions.

## User
Owner or shop manager. Secondary: the customer, who wants a fast and correct answer.

## Solution
Triage every message, draft a grounded reply, put risky ones first, and let a person approve in one click.

## Decisions and why
| Decision | Reason | Cost of the choice |
|---|---|---|
| A person approves everything | A wrong price or allergy answer is worse than a slow one | Less time saved |
| Complaints, health topics, injection attempts and weak confidence escalate | These need judgement | Some extra review work |
| Rules baseline before any model | Free to run, gives a score a model must beat, covers outages | Weak on unusual wording |
| Documents are plain markdown | The owner can edit them | Keyword search only, for now |

## Success measures (to be measured in a pilot)
- Minutes from message to reply
- Share of drafts approved without edits (already tracked in the dashboard)
- Missed escalations (target: zero)
- Model cost per 100 messages

## Estimating value
Hours saved per month = messages per month x (manual minutes - review minutes) / 60.
Illustration with assumed numbers, not measurements: 600 x (4 - 1) / 60 = 30 hours.
Replace them with pilot data before quoting any figure.

## Rollout
1. Shadow mode: drafts only, owner replies as usual, compare.
2. Owner approves drafts for questions.
3. Add orders. Auto-send stays off until months of data justify discussing it.

## Not doing yet
Payments, auto-send, voice, multiple businesses.
