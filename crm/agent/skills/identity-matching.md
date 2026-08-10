# Identity matching

version: 1

Deciding that two records are the same person is the highest-consequence call
you make. Get it wrong and you merge two customers' histories, or you send one
person's quote to another. Neither is recoverable by editing a field.

## Ranking of identifiers, strongest first

1. **Phone number** — in this market the mobile number is the account. It pays
   the bills, it receives the M-Pesa prompt, and people keep it for years.
   Compare on the last nine digits: `+254712345678`, `254712345678`,
   `0712345678` and `712345678` are one number, and comparing them literally
   is a guaranteed miss.
2. **Email address** — strong, but shared mailboxes exist
   (`info@`, `sales@`, `accounts@`). An exact match on a role address is
   evidence about a *company*, not a person.
3. **Full name** — weak on its own. Kenyan naming conventions mean common
   surnames repeat constantly within one account, and a "close match" between
   two similar names is more often two relatives than one person.

## Rules

- Never merge on name alone. Never.
- A near-match on a name is a candidate to report, not a match to act on.
- Two candidates scoring equally is not a tie to break — it is the exact
  situation where guessing does the most damage. Report both and ask.
- Free-mail domains (gmail, yahoo, outlook) tell you nothing about which
  company someone works for. Discard them explicitly rather than silently.
- When a person legitimately appears twice — same human, two records — say so
  with the basis for each. Merging remains a human action.

## Writing up a match

State the identifier that matched and how. "Phone matches exactly" and "name is
an 88% string match" are different claims, and the rep needs to know which one
you are making before they act on it.
