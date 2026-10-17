---
id: sop-cancel-web-subscription
title: How to cancel a website subscription (agent steps)
type: procedure
audience: internal
sub_intents: [cancellation, delete_account_or_data]
channels: [web]
url: https://kb.nebula.internal/sop/cancel-web
last_reviewed: 2026-09-10
---
1. Find the customer in the admin panel by email.
2. Check the subscription source. If it says "App Store" or "Google Play", stop: the customer must cancel in the store (`policy-refund-store`).
3. Click **Subscription → Cancel auto-renewal**. Access stays active until the end of the paid period.
4. Confirm to the customer: the date access ends, and that no further charges will be made.
5. If the customer was charged after an earlier cancellation attempt, check `policy-refund-web` for a refund.
