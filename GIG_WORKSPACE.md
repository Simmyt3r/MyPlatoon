# MyPlatoon private gig workspaces, phase 2

A gig is no longer just an offer and a completion button. After the
worker accepts the immutable job terms, both parties can use the
private workspace at `/jobs/deals/<deal_id>`.

## Features

- **Private progress journal:** `POST /jobs/deals/<id>/updates`, 5–1,200
  characters, append-only, visible to the worker and gig owner; both
  are notified. It is not a public chat and does not alter the agreement.
  Moderators may inspect the latest 30 notes only in an open-dispute case.
- **Delivery corrections:** After the worker requests completion,
  `POST /jobs/deals/<id>/revision` allows only the employer to explain
  what remains incomplete in the **existing original scope**. The
  accepted pay and schedule cannot be changed. The work returns to
  `active` until the worker resubmits.
- **Mutual cancellation:** A worker or gig owner can submit a reason
  of 20–1,000 characters at `POST /jobs/deals/<id>/termination`.
  The gig is NOT cancelled until the other party explicitly accepts.
  One pending proposal is permitted at a time, enforced by a
  PostgreSQL/SQLite partial unique index and parent deal row locking.
  Respond via `/termination/<request_id>/respond` with accept/decline;
  the proposer may `/termination/<request_id>/withdraw` a pending offer.
  The platform retains the reason and decision for the participants.
- **Safety:** If a dispute is opened, the pending cancellation request
  becomes superseded. Existing dispute handling remains confidential.
  Nothing in a cancellation marks money transferred, waives unpaid
  work or certifies compliance with employment legislation.
- **Role boundaries:** Strangers, unauthenticated people and employers
  from other companies cannot read another gig's journal or respond
  to its cancellation requests. State transitions are checked on each
  POST, CSRF-protected and rate limited. Existing public ratings remain
  based on two-party **completed** work, never cancelled gigs.

## Limitations

This release does not include uploaded evidence, a dispute appeal
tribunal, live chat, payment settlement, payroll, escrow, employer
identity assurance, job insurance or automated moderation. Do not
post highly sensitive personal information or financial credentials.
Cancellation of accepted work is voluntary; any outstanding payment
or contractual liability must be dealt with independently and, if
appropriate, through legal or NYSC-authorized channels.

## Deployment

Migration **`a14b82a0d7e6`** after `g93d0f6e2a41`
creates `gig_work_updates` and `gig_termination_requests`, with
a unique pending-request index. CI tests cover the new routes plus
fresh Alembic upgrade. Production Aiven migrations are **deferred**
until the requested final configuration stage.
