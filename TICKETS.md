# TICKETS — SoftMarket-Kenya Marketplace Pipeline

## [TICKET-001] Daraja Timeout Query Reconciler
- **Blocked by**: None
- **Delivers**: Polling worker resolving unconfirmed M-Pesa payments.
- **Verification**: `tests/mpesa-timeout-reconciliation.test.ts`

## [TICKET-002] Multi-Party Escrow Settlement Engine
- **Blocked by**: TICKET-001
- **Delivers**: Two-phase payment release pipeline deducting platform commission upon delivery confirmation.
- **Verification**: Escrow balance ledger tests.
