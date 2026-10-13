# Gig hiring and completion, phase 1

MyPlatoon has a **consent-first work agreement** at `/jobs/deals/`.
This is the next stage after gig owner registration, moderator-approved
listing, and a member voluntarily submitting an application.

## From listing to real work

1. A moderated, published **gig** receives applications. In the owner
   dashboard, open **Applicants** and **Send formal work offer**.
2. An approved gig owner proposes immutable scope, schedule and a positive
   NGN amount **inside the already-advertised pay range**. The pay unit
   comes from the listing and cannot be switched during an offer.
   An in-app notification is queued for the applicant.
3. The applicant independently reviews the details and must check
   **accept terms** before accepting. Declining creates no work contract.
   The old applicant-status selector cannot mark gig applicants **Hired**.
4. On acceptance the deal becomes **active** and the application becomes
   **hired**. An accepted deal can no longer be unilaterally withdrawn
   by the owner. Public gigs must pass owner and job approval to issue
   offers, and approval cannot be bypassed by directly calling the API.
5. When work has actually been delivered, **only the worker** can request
   completion. **Only the employer** can confirm completion, or raise
   a private dispute. The worker cannot mark a deal fully completed alone.
6. Payment is arranged entirely **outside MyPlatoon**. After completion,
   the employer can mark payment **reported paid** and the worker can
   separately acknowledge receipt. Payment flags are voluntary
   statements by their respective parties, not bank verification or
   evidence MyPlatoon transferred, escrowed or guaranteed any funds.
7. Once the work is completed, each party may submit **one private 1–5
   star rating** with optional feedback. These reviews are not yet
   surfaced as public reputation scores.
8. Either party can privately report a dispute during active work,
   completion request, or completed work (e.g. nonpayment). Work is
   marked **disputed**, suspending ordinary workflow actions. The admin
   dashboard at `/jobs/deals/admin/disputes` shows the confidential
   reason. Admins may resume the deal or cancel it, with a required
   written explanation. Moderators cannot invent work-completion or
   payment confirmations.

## Public and private routes

| Path | User |
| --- | --- |
| `/jobs/<job_id>/applications` | Listing owner (applicant list) |
| `/jobs/deals/offer/<application_id>` | Approved owner (offer form) |
| `/jobs/deals/` | Participant's agreements |
| `/jobs/deals/<deal_id>` | Only applicant or owner |
| `/jobs/deals/<deal_id>/respond` | Worker accept/decline, POST |
| `/jobs/deals/<deal_id>/cancel` | Owner only, unaccepted offers, POST |
| `/jobs/deals/<deal_id>/finish` | Worker completion request, POST |
| `/jobs/deals/<deal_id>/confirm` | Employer completion confirmation, POST |
| `/jobs/deals/<deal_id>/payment` | Employer report and worker acknowledgment, POST |
| `/jobs/deals/<deal_id>/dispute` | Either party, confidential POST |
| `/jobs/deals/<deal_id>/review` | Either party after completion, POST |
| `/jobs/deals/admin/disputes` | Admin private reports |
| `/jobs/deals/admin/disputes/<id>` | Admin resolution, POST |

All POST routes use Flask-WTF CSRF protection and authenticated user
checks; sensitive actions additionally check the current agreement state.
The moderator approval boundary for public jobs remains unchanged.

## Limitations

- No escrow, wallet, Paystack payments, automatic disbursements, payout
  guarantees, email/SMS or background processing.
- Deals cover **gig** listings, not open-ended full-time job employment
  contracts. Other job applications keep their existing flow.
- Agreements are not a substitute for written employment agreements or
  NYSC permission for outside work. Always vet counterparties, protect
  personal data, and follow PPA/CDS obligations.
- Gig reviews are private records for now. Public reputations need
  future moderation, anti-fraud weighting and safety policies.
- Dispute resolution is a platform workflow, **not** a court decision
  or legally binding arbitration.
- Existing company and personal address details remain restricted to
  the employer's previous disclosure settings. No member's private
  residential address or NYSC number is automatically shared.

## Database & deployment

Migration: **`f82b7e46c3a1`**, following `e71f6c82a9bb`.
It adds `gig_deals`, `gig_disputes` and `gig_reviews`. Do not
apply it automatically to production: follow the agreed final setup,
back up Aiven, and run a reviewed `flask db upgrade`/configured workflow
before exposing these backend actions.

Tests: `tests/test_gig_deals.py` plus the full regression suite and
fresh Alembic upgrade. The tests cover applicant/owner permissions,
one-off accepted terms, offer pay constraints, duplicate requests,
the two-party completion boundary, independent payment acknowledgement,
confidential disputes, admin limits, and one rating per party.
