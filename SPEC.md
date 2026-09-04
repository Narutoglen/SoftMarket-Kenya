# SPEC 001: Agritech Marketplace & Mobile Money Reconciliation Engine

## Problem Statement
Kenyan farmers and wholesale merchants lose revenue when M-Pesa network timeouts drop payment confirmations.

## Solution
A digital marketplace featuring autonomous Daraja timeout reconciliation, escrow protections, and offline inventory intake.

## User Stories
1. As a merchant, I want STK push payments verified automatically even if callbacks fail, so that I can dispatch orders without delays.
2. As a farmer, I want guaranteed escrow payment holds, so that I am never defrauded on produce delivery.

## Implementation Decisions
- Reconciliation engine in `src/services/mpesa/reconciliation.ts`.
- Field intake persistence in `src/services/intake.ts`.

## Testing Decisions
- Seam: `tests/mpesa-timeout-reconciliation.test.ts`.
- Verify query retry backoff and status state machine transitions.
