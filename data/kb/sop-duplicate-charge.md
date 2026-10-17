---
id: sop-duplicate-charge
title: Investigating unexpected or duplicate charges
type: procedure
audience: internal
sub_intents: [unexpected_charge]
channels: [any]
url: https://kb.nebula.internal/sop/unexpected-charge
last_reviewed: 2026-09-15
---
1. Ask for (or look up) the charge date, amount and the name on the bank statement.
2. "APPLE.COM/BILL" or "Google Play" → store purchase, follow `policy-refund-store`.
3. "NEBULA"/"OBRIO" → find the charges in the admin panel. Identify the type: trial conversion, renewal, duplicate, or charge after cancellation.
4. Apply `policy-refund-web` for that type. Explain in plain words what the charge was for.
5. Make sure auto-renewal is cancelled if the customer does not want the subscription (`sop-cancel-web-subscription`).
