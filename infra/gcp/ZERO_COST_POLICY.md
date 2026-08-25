# MPlacas — ZERO COST POLICY

Status: **MANDATORY**

Effective date: 2026-08-25

## Invariant

The MPlacas project must not depend on any Google Cloud configuration that can generate monetary charges.

A Google Cloud Free Tier allowance is **not** considered a zero-cost guarantee because it requires an active Cloud Billing relationship and can generate charges when free allowances are exceeded.

## Consequence

While this file exists:

- Cloud Run service deployment is prohibited.
- Cloud Run Job deployment or execution is prohibited.
- Cloud Scheduler provisioning is prohibited.
- automated cost-audit jobs running on Google Cloud are prohibited.
- database migration jobs running on Google Cloud are prohibited.
- new billable Google Cloud resources must not be provisioned.

Cleanup, read-only audit, and actions required to disable/unlink Cloud Billing remain allowed.

## Reactivation

Removing `SUSPENDED.md` does **not** authorize Google Cloud runtime deployment. This policy is independent of the administrative suspension.

Changing this policy requires an explicit architectural decision accepting the possibility of Google Cloud charges.
