# NERD resource integration (Phase 1)

**Scope:** MyPlatoon provides a public NERD information-and-referral feature at `/nerd`. The feature links to NERD's and NYSC's official sites and offers MyPlatoon's independent assistance by telephone and WhatsApp.

**Not implemented:** NERD account registration, academic uploads, NERD receipt issuance, academic verification, NSN/NCN verification, NYSC eligibility checks, government SSO, or data synchronisation. Do not advertise those capabilities until they exist, and never imitate an official government site.

## NERD preparation checklist (new)

MyPlatoon includes a public, read-only preparation checklist at
`/nerd/requirements`, reachable from `/nerd`, Services and the home page.
The checklist contains **38 items in seven groups**, transcribed from
the list supplied for this project:

1. Personal Information (8): title, names, sex, date of birth,
   marital status and NIN.
2. Contact Information (7): nationality, state, LGA, town,
   contact address, email and phone.
3. Next of Kin (3): name, phone, email.
4. Academic Data (7): institution, faculty, department, programme category,
   programme type, registration/matriculation number and course.
5. Supervisor Details (4): academic title, name, phone, email.
6. HOD Details (4): academic title, name, phone, email.
7. Documents (5): passport photo, NIN image, result/certificate image,
   approved project page image and final project soft copy.

This user-supplied list is **not claimed to be a universal or fully official
NERD mandatory form**. The exact requirements may depend on the institution
and the official enrolment process. Verify directly with NERD and the
institutional NERD focal person.

**Data-minimisation guarantee for this phase:**
- No NIN text field, document uploader, collection form, or POST endpoint.
- No writes to Aiven or other databases.
- Checkboxes/progress exist only on the current browser page and are cleared
  on refresh/exit (no localStorage or cookie persistence).
- Print uses the browser's own print function; no server-side PDF generated.
- No next-of-kin, supervisor or HOD contact details are received by MyPlatoon.
- Registration and academic document submission stay with NERD or an
  authorised institution.

The NERD checklist is intentionally informational only. A future
officially authorised API implementation will require explicit permission,
privacy notices, consent/appropriate legal basis, encryption, lifecycle
controls and separate security review before collecting identity documents.

## Official sources

- NERD home: https://databank.ned.gov.ng/home
- Student/lecturer registration: https://databank.ned.gov.ng/info/student-lecturers-sign-up
- Deposit receipt information: https://databank.ned.gov.ng/info/nerd-receipt
- Official NERD contact: https://databank.ned.gov.ng/info/contact-and-support
- NERD institutional API support: https://databank.ned.gov.ng/info/training
- NYSC registration: https://portal.nysc.org.ng/nysC/home

NERD says **institutional** API integration is supported through its implementation team. MyPlatoon has not been supplied public developer credentials, an API agreement or endpoint documentation. Therefore integration is limited to safe external navigation and independent guidance, not a technical connection.

## MyPlatoon contacts (not NERD's contact details)

- Phone: **09039930006**
- Phone CTA: `tel:09039930006`
- WhatsApp CTA: `https://wa.me/2349039930006` (requires WhatsApp service on this number)

These are *MyPlatoon assistance* links. Users who require official decisions or help with their NERD records must use NERD's own listed support contacts or their institution's NERD focal person.

## Configuration

```dotenv
NERD_HELP_PHONE=09039930006
NERD_HELP_WHATSAPP_URL=https://wa.me/2349039930006
```

These values are optional, and have defaults in `app/config.py`. If changing the phone, also change the WhatsApp link to match. Never store credentials, OTPs, academic documents or payment data through the MyPlatoon NERD guidance page.

## Verification and future integration steps

1. Ask the NERD programme office for documented permission, sandbox/API specifications, and permitted use cases for a third-party community platform.
2. Execute a formal data-protection and partnership review before handling academic records or identifiers.
3. If approved, add server-side OAuth/authentication or service credentials from secure environment variables, user consent, an audit trail and rate limits.
4. Add tests with a sandbox before advertising a live NERD-backed status.

Sources checked: **11 October 2026**. Government policies, page addresses and requirements may change; defer to the official portals.
