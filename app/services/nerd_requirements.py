"""User-supplied NERD preparation checklist.

This is intentionally a LIST OF REQUIRED MATERIALS, not a collection form:
MyPlatoon has no authorised government identity-data submission integration.
Never populate this checklist with names, NINs, phone numbers or documents.
See NERD_INTEGRATION.md for the official referral-only workflow.
"""

# Item IDs must remain stable within the page for accessibility and JS progress.
NERD_REQUIREMENT_SECTIONS = (
    {
        "key": "personal",
        "title": "Personal Information",
        "subtitle": "Prepare your details exactly as they appear on your official records.",
        "items": (
            ("title", "Title"),
            ("first-name", "First Name"),
            ("middle-name", "Middle Name"),
            ("surname", "Surname"),
            ("sex", "Sex"),
            ("dob", "Date of Birth"),
            ("marital-status", "Marital Status"),
            ("nin", "NIN"),
        ),
    },
    {
        "key": "contact",
        "title": "Contact Information",
        "subtitle": "Check that your contact details are current.",
        "items": (
            ("nationality", "Nationality"),
            ("state", "State of Origin"),
            ("lga", "LGA"),
            ("town", "Town"),
            ("address", "Contact Address"),
            ("email", "Email"),
            ("phone", "Phone Number"),
        ),
    },
    {
        "key": "next-of-kin",
        "title": "Next of Kin",
        "subtitle": "Confirm the details with your next of kin before entering them on any official form.",
        "items": (
            ("name", "Name"),
            ("phone", "Phone Number"),
            ("email", "Email"),
        ),
    },
    {
        "key": "academic",
        "title": "Academic Data",
        "subtitle": "Use your institution's officially recorded programme information.",
        "items": (
            ("institution", "Institution"),
            ("faculty", "Faculty"),
            ("department", "Department"),
            ("category", "Programme Category"),
            ("type", "Programme Type"),
            ("matric", "Matric/Reg. No."),
            ("course", "Course of Study"),
        ),
    },
    {
        "key": "supervisor",
        "title": "Supervisor Details",
        "subtitle": "Ask your project supervisor to confirm their title and official contact details.",
        "items": (
            ("academic-title", "Academic Title"),
            ("name", "Full Name"),
            ("phone", "Phone"),
            ("email", "Email"),
        ),
    },
    {
        "key": "hod",
        "title": "HOD Details",
        "subtitle": "Confirm the current Head of Department's academic title and official contacts.",
        "items": (
            ("academic-title", "Academic Title"),
            ("name", "Full Name"),
            ("phone", "Phone"),
            ("email", "Email"),
        ),
    },
    {
        "key": "documents",
        "title": "Documents to Prepare",
        "subtitle": "Prepare readable digital files. Upload documents only where the official NERD process requests them.",
        "items": (
            ("passport", "Passport photograph"),
            ("nin-image", "Picture of NIN"),
            ("result", "Statement of result/Certificate"),
            ("approval", "Picture of project approval page"),
            ("project", "Soft copy of complete project work"),
        ),
    },
)

REQUIREMENT_TOTAL = sum(len(s["items"]) for s in NERD_REQUIREMENT_SECTIONS)
