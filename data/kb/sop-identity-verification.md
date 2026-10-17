---
id: sop-identity-verification
title: Identity verification before account changes
type: procedure
audience: internal
sub_intents: [login_access, change_email, delete_account_or_data]
channels: [any]
url: https://kb.nebula.internal/sop/identity
last_reviewed: 2026-08-01
---
Required before changing an email, restoring access, or deleting an account.

1. If the request comes from the account email: verified.
2. Otherwise send the verification link from the admin panel to the account email and wait for confirmation.
3. If the customer no longer has access to the account email: ask for the last 4 digits of the card used and the date of the last purchase, and compare with the billing record. Two matches = verified.
4. Never confirm or deny that an account exists for an email address before verification.
