---
id: ts-login-account-not-found
title: Can't log in or "account not found"
type: troubleshooting
audience: customer
sub_intents: [login_access]
channels: [any]
url: https://help.nebula.example/troubleshooting/login
last_reviewed: 2026-09-05
---
"Account not found" almost always means a different sign-in method was used:
1. Try every method you might have used before: Sign in with Apple, Google, or email.
2. With Sign in with Apple, your account may be linked to a hidden "privaterelay.appleid.com" email.
3. Use "Forgot password" for email accounts.

Agents: if none works, verify identity (`sop-identity-verification`) and look up the account by purchase email or card digits; then tell the customer which sign-in method to use.
