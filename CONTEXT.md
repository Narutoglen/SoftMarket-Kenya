# CONTEXT.md — Ubiquitous Domain Language (SoftMarket-Kenya)

## Core Entities
- **MarketOrder**: Commercial purchase of farm produce or wholesale retail inventory.
- **DarajaTransaction**: M-Pesa mobile money payment verified via STK Push or C2B confirmation.
- **EscrowHold**: Temporary fund reservation protecting buyers until produce inspection is confirmed.
- **ProduceIntake**: Field recording of agricultural goods with grade, weight, and harvest moisture.

## Domain Invariants
- Merchant wallet balances cannot be credited until the buyer signs off on produce intake.
- Unconfirmed Daraja payments trigger automatic API status queries before canceling orders.

## Forbidden Terminology
- Do not call M-Pesa payments "credit card transactions".
- Do not refer to wholesale buyers as "users"; use "BuyerMerchant".
