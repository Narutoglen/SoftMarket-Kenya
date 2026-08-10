"""The agentic core of the CRM.

The organising idea, borrowed from trycompai/crm and rebuilt on Django: the
agent is not a feature of the CRM, the CRM is the agent's workspace. It keeps
its own queue (``queue.py``), runs on its own clock (``runner.py``), and every
change it makes is traceable to something it observed (``evidence.py``).

Layout
    evidence.py   the pricing ledger — what counts as proof, and what a given
                  strength of proof is allowed to do to a record
    tools.py      the 18 tools the agent can call; each reports observations,
                  never conclusions
    queue.py      lease-based work claiming (FOR UPDATE SKIP LOCKED on Postgres)
    runner.py     the loop: claim → plan → act → brief → schedule the next look
    brain.py      the planner. Claude when an API key is configured, a
                  deterministic playbook when it isn't — same tools either way
    skills/       versioned markdown the planner reads before it decides

Nothing here calls a third-party enrichment API by default. That is deliberate:
the agent must be useful, and auditable, on a laptop with no keys in the
environment.
"""
