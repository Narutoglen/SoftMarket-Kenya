# ADR 0001: Daraja M-Pesa Reconciliation and Escrow Settlement

## Context
SoftMarket-Kenya operates in rural environments where mobile data connectivity is inconsistent.

## Decision
1. **Automated Daraja Polling**: Background workers query transaction status for unacknowledged STK pushes.
2. **Milestone Escrow**: Marketplace holds buyer funds until physical produce receipt verification.
3. **Offline Intake Queue**: Field agents log produce locally with automated sync on reconnection.

## Consequences
- **Positive**: Zero lost sales due to telecom callback drops and high buyer/farmer trust.
- **Negative**: Adds 45-second latency before unconfirmed orders are resolved via polling.
