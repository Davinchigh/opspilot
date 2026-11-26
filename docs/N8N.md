# n8n

**Status:** the workflow file is written and is valid JSON. It has not yet been imported or run in n8n.
Do not claim n8n experience from it until you have completed the steps below.

## Steps

1. Start OpsPilot: `python -m opspilot serve`.
2. Start n8n (see https://docs.n8n.io/hosting/ for current requirements): `npx n8n`.
3. In n8n, create a workflow, choose **Import from file** and pick `n8n/opspilot-intake.json`.
4. Press **Listen for test event** on the Webhook node.
5. Send a message to the test URL that n8n shows:

```bash
curl -X POST <test-url> -H "Content-Type: application/json" -d '{"id":"1","sender":"ama","message":"My cake arrived smashed"}'
```

6. Check that the escalated branch ran and the ticket appears in the dashboard.

## Notes

- n8n in Docker cannot reach `127.0.0.1` on your computer. Use `host.docker.internal` and start
  OpsPilot with `--host 0.0.0.0` and `OPSPILOT_TOKEN` set.
- With a token, add the header `Authorization: Bearer <token>` using an n8n credential, not plain text
  in the workflow.
- The webhook has no authentication. Add header auth on it before exposing n8n to the internet.
