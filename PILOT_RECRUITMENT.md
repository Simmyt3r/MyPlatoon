# MyPlatoon — Paid recruitment pilot playbook

**Status:** experiment plan, not a live payment product. No payment collection,
pricing enforcement, billing events or advertising monetization is implemented
by this plan. Members continue to apply for vacancies for free.

## What we are testing

Can MyPlatoon help schools and SMEs hire relevant corps members quickly enough
that an employer is willing to pay a recurring recruitment service fee?

Choose **one NYSC state / one outreach community** for the first cohort;
do not announce a nationwide paid launch before validating the service.

## 30-day experiment

**Week 1 — partner recruitment:** speak with at least 10 schools/SMEs and
onboard 5 genuine employers. Obtain explicit agreement to participate in a
free pilot and explain what is and is not verified. Review every employer
and vacancy; do not sell anyone a "verified" badge just for paying.

**Week 2 — recruit the candidates:** invite 100–150 eligible members through
consensual alumni, platoon and orientation networks. Explain the free member
experience and privacy controls. Track completed profiles and the quality of
applications, not raw registration totals.

**Week 3 — observe end-to-end:** confirm 10–15 actual vacancies, candidate
applications, shortlists, interview requests and outcomes. Contact employers
for qualitative feedback. Document time saved and candidate relevance.

**Week 4 — willingness to pay:** only if employers report useful outcomes,
offer a *manually contracted* recruitment-support pilot at a **hypothesis
price of ₦15,000 per month**. Do not start automatic charges. Explain
deliverables, contract duration, refund and cancellation terms, and the
scope of verified employer/student identities. Record voluntary
interest-to-pay and separate it from actual received payment.

## Decision gates

- **Adoption:** at least 5 legitimate employers and 100 eligible members.
- **Market usefulness:** at least 10 real job posts and 3 confirmed,
  employer-acknowledged recruitment outcomes.
- **Pricing validation:** at least 3 employers explicitly agree to the
  specified paid service under written terms.
- **Product readiness:** security and rate-limit review complete, privacy
  documentation accessible, backups tested, production errors monitored.

These targets are hypotheses. Stop paid rollout if any gate fails.
Do not equate "hired" status in the DB with a verified paid placement.

## Reading the admin dashboard

Admin → **Recruitment & Growth Insights** shows:

- User registrations, recent last-login dates (not weekly active users)
- Employer registration, approval and school counts
- Published/open listings and current application statuses
- 4 rolling weeks of application/registration totals
- Per-employer top-20 application and marked-hire figures
- Whether production has configured a shared rate-limiting store

The dashboard uses **existing PostgreSQL records** and requires no new
database tables, cookies, analytics SDK, or external sharing. It shows no
payment revenue because no verified billing system is connected.

## Before taking a payment

1. Decide the exact employer deliverable and refund/cancellation policy.
2. Have the legal entity and Nigerian tax/privacy implications reviewed.
3. Integrate a compliant payment provider with verified webhooks and
   idempotency, server-side entitlements, invoices and reconciliation.
4. Clearly label featured listings and keep ordinary job application free.
5. Test real employer renewals before expanding product scope.

Do not install a payment gateway or turn on a paywall just because a
dashboard can display recruitment counts.
