"""Generates the digital album as a PDF using ReportLab.

Design notes
------------
* The album is treated as a "platoon-members-only" distribution: any
  field a member marked "platoon" or "public" is included; anything
  marked "private" is always omitted, matching Section 39 of the spec.
* QR codes are embedded per-member, pointing at each member's public
  profile URL.
* Output is returned as raw bytes so the caller can upload it straight
  to Cloudinary (or any blob store) without ever touching local disk —
  required for Vercel's serverless/read-only filesystem.
"""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table,
    TableStyle, Image as RLImage, NextPageTemplate, PageBreak, HRFlowable,
)

from app.services.qr_service import generate_qr_png_bytes, profile_public_url

BRAND_GREEN = colors.HexColor("#0B7A3B")
BRAND_GOLD = colors.HexColor("#C79A2E")
BRAND_DARK = colors.HexColor("#1A1A1A")
BRAND_GRAY = colors.HexColor("#666666")


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="AlbumTitle", fontSize=28, leading=32,
                               textColor=BRAND_GREEN, spaceAfter=6, alignment=1,
                               fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="AlbumSubtitle", fontSize=14, leading=18,
                               textColor=BRAND_DARK, alignment=1, spaceAfter=4))
    styles.add(ParagraphStyle(name="AlbumMotto", fontSize=11, leading=14,
                               textColor=BRAND_GOLD, alignment=1, spaceAfter=2,
                               fontName="Helvetica-Oblique"))
    styles.add(ParagraphStyle(name="SectionHeading", fontSize=16, leading=20,
                               textColor=BRAND_GREEN, spaceBefore=10, spaceAfter=8,
                               fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="MemberName", fontSize=14, leading=17,
                               textColor=BRAND_DARK, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="MemberMeta", fontSize=9.5, leading=13,
                               textColor=BRAND_GRAY))
    styles.add(ParagraphStyle(name="MemberBio", fontSize=9.5, leading=13,
                               textColor=BRAND_DARK, spaceBefore=4))
    styles.add(ParagraphStyle(name="Body", fontSize=10.5, leading=15,
                               textColor=BRAND_DARK))
    styles.add(ParagraphStyle(name="TOCEntry", fontSize=11, leading=18,
                               textColor=BRAND_DARK))
    styles.add(ParagraphStyle(name="FooterText", fontSize=8, leading=10,
                               textColor=BRAND_GRAY, alignment=1))
    return styles


def _branding():
    from flask import current_app
    cfg = current_app.config
    return {
        "name": cfg["APP_NAME"],
        "subtitle": cfg["APP_SUBTITLE"],
        "motto": cfg["APP_MOTTO"],
        "powered_by": cfg["POWERED_BY"],
        "member_label": cfg["APP_MEMBER_LABEL"],
    }


def _footer_text(branding):
    parts = [p for p in [
        f"Powered by {branding['powered_by']}" if branding["powered_by"] else None,
        branding["motto"] or None,
    ] if p]
    return "  \u2022  ".join(parts)


def _footer(canvas, doc):
    branding = _branding()
    footer_text = _footer_text(branding)
    canvas.saveState()
    canvas.setStrokeColor(BRAND_GOLD)
    canvas.setLineWidth(0.6)
    canvas.line(20 * mm, 16 * mm, doc.pagesize[0] - 20 * mm, 16 * mm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(BRAND_GRAY)
    if footer_text:
        canvas.drawCentredString(doc.pagesize[0] / 2, 11 * mm, footer_text)
    canvas.drawRightString(doc.pagesize[0] - 20 * mm, 6 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _cover_page(story, styles, member_count, business_count, version_label, branding):
    story.append(Spacer(1, 60 * mm))
    story.append(Paragraph(branding["name"].upper(), styles["AlbumTitle"]))
    story.append(Spacer(1, 6))
    if branding["subtitle"]:
        story.append(Paragraph(branding["subtitle"], styles["AlbumSubtitle"]))
        story.append(Spacer(1, 10))
    if branding["motto"]:
        story.append(Paragraph(branding["motto"], styles["AlbumMotto"]))
    story.append(Spacer(1, 30))
    story.append(Paragraph(
        f"Album Version {version_label} &bull; {member_count} Members &bull; "
        f"{business_count} Registered Businesses",
        styles["MemberMeta"],
    ))
    story.append(Paragraph(
        f"Generated {datetime.utcnow().strftime('%d %B %Y')}", styles["MemberMeta"]))
    story.append(Spacer(1, 40))
    if branding["powered_by"]:
        story.append(Paragraph(f"Powered by {branding['powered_by']}", styles["AlbumSubtitle"]))
    story.append(PageBreak())


def _intro_page(story, styles, branding):
    name = branding["name"]
    group = branding["subtitle"] or name
    story.append(Paragraph(f"About {name}", styles["SectionHeading"]))
    story.append(Paragraph(
        f"This album brings together the members of {group} &mdash; a community "
        "built to last well beyond any single event. Within these pages you will "
        "find the people, professions, skills and businesses that make up this "
        "network.",
        styles["Body"],
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "The goal of this project is not merely to preserve a moment in time. "
        f"It is to create a lasting digital network where members of {group} can "
        "continue to discover one another, collaborate, support one another's "
        "businesses, and maintain meaningful professional relationships.",
        styles["Body"],
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Every profile in this album was submitted voluntarily and reviewed by "
        "an administrator before publication. Contact details are shown "
        "strictly according to each member's own privacy preferences.",
        styles["Body"],
    ))
    story.append(PageBreak())


def _toc_page(story, styles, profiles):
    story.append(Paragraph("Table of Contents", styles["SectionHeading"]))
    data = [["#", "Name", "Profession", "State"]]
    for idx, profile in enumerate(profiles, start=1):
        data.append([
            str(idx),
            profile.user.full_name,
            profile.profession or "-",
            profile.state_of_origin or "-",
        ])
    table = Table(data, colWidths=[10 * mm, 65 * mm, 60 * mm, 35 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F4F4")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    story.append(PageBreak())


def _member_photo_flowable(profile, size_mm=32):
    # We only embed remote (Cloudinary) images if reachable; otherwise a
    # neutral placeholder box keeps layout stable.
    try:
        import urllib.request
        if profile.photo_url and profile.photo_url.startswith("http"):
            with urllib.request.urlopen(profile.photo_url, timeout=5) as resp:
                img_bytes = resp.read()
            return RLImage(io.BytesIO(img_bytes), width=size_mm * mm, height=size_mm * mm)
    except Exception:
        pass
    return Spacer(size_mm * mm, size_mm * mm)


def _member_section(story, styles, profile, branding):
    contact_lines = []
    if profile.phone_visibility in ("public", "platoon") and profile.phone_number:
        contact_lines.append(f"Phone: {profile.phone_number}")
    if profile.whatsapp_visibility in ("public", "platoon") and profile.whatsapp_number:
        contact_lines.append(f"WhatsApp: {profile.whatsapp_number}")
    if profile.address_visibility == "general" and profile.current_location:
        contact_lines.append(f"Location: {profile.current_location}")
    elif profile.address_visibility == "exact" and profile.address:
        contact_lines.append(f"Address: {profile.address}")

    skills = ", ".join(s.name for s in profile.skills) if profile.skills else "-"

    qr_bytes = generate_qr_png_bytes(profile_public_url(profile.slug))
    qr_image = RLImage(io.BytesIO(qr_bytes), width=22 * mm, height=22 * mm)

    photo = _member_photo_flowable(profile)

    info_lines = [
        Paragraph(profile.user.full_name, styles["MemberName"]),
        Paragraph(profile.profession or branding["member_label"], styles["MemberMeta"]),
        Paragraph(
            f"{profile.state_of_origin or '-'}, {profile.lga or '-'} "
            f"&bull; {profile.institution or '-'}",
            styles["MemberMeta"],
        ),
        Paragraph(f"Skills: {skills}", styles["MemberMeta"]),
    ]
    if contact_lines:
        info_lines.append(Paragraph(" | ".join(contact_lines), styles["MemberMeta"]))
    if profile.biography:
        bio = profile.biography.strip()
        if len(bio) > 400:
            bio = bio[:400].rstrip() + "..."
        info_lines.append(Paragraph(bio, styles["MemberBio"]))
    if profile.businesses:
        biz_names = ", ".join(b.name for b in profile.businesses if b.is_active)
        if biz_names:
            info_lines.append(Paragraph(f"Business: {biz_names}", styles["MemberMeta"]))

    row = Table(
        [[photo, info_lines, qr_image]],
        colWidths=[36 * mm, 112 * mm, 26 * mm],
    )
    row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
    ]))
    story.append(row)
    story.append(Spacer(1, 6))


def _business_directory_section(story, styles, businesses):
    story.append(Paragraph("Business Directory", styles["SectionHeading"]))
    if not businesses:
        story.append(Paragraph("No registered businesses at time of publication.",
                                styles["Body"]))
        return
    data = [["Business", "Owner", "Category", "Contact"]]
    for biz in businesses:
        contact = biz.phone or biz.email or biz.website or "-"
        data.append([
            biz.name,
            biz.profile.user.full_name if biz.profile and biz.profile.user else "-",
            biz.category.name if biz.category else "Other",
            contact,
        ])
    table = Table(data, colWidths=[45 * mm, 45 * mm, 35 * mm, 45 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_GOLD),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F4F4")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)


def _closing_section(story, styles, member_count, business_count, branding):
    group = branding["subtitle"] or branding["name"]
    story.append(PageBreak())
    story.append(Paragraph("By the Numbers", styles["SectionHeading"]))
    story.append(Paragraph(f"Total Members Featured: {member_count}", styles["Body"]))
    story.append(Paragraph(f"Registered Businesses: {business_count}", styles["Body"]))
    story.append(Spacer(1, 20))
    story.append(Paragraph("Closing Message", styles["SectionHeading"]))
    story.append(Paragraph(
        f"To every member of {group}: thank you for being part of this record. "
        "May the bonds formed here last, and may we continue to build one "
        "another up.",
        styles["Body"],
    ))
    story.append(Spacer(1, 30))
    story.append(HRFlowable(width="100%", color=BRAND_GOLD, thickness=1))
    story.append(Spacer(1, 10))
    story.append(Paragraph(branding["name"].upper(), styles["AlbumSubtitle"]))
    if branding["powered_by"]:
        story.append(Paragraph(f"Powered by {branding['powered_by']}", styles["MemberMeta"]))
    if branding["motto"]:
        story.append(Paragraph(branding["motto"], styles["AlbumMotto"]))


def build_album_pdf(profiles, businesses, version_label="1.0") -> bytes:
    """Build the full album PDF in memory and return raw bytes.

    `profiles` must already be filtered to APPROVED profiles only —
    this function does not re-check status, to keep it easily testable.
    """
    branding = _branding()

    buffer = io.BytesIO()
    doc = BaseDocTemplate(buffer, pagesize=A4,
                           leftMargin=20 * mm, rightMargin=20 * mm,
                           topMargin=18 * mm, bottomMargin=22 * mm,
                           title=branding["name"],
                           author=branding["powered_by"] or branding["name"])
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    template = PageTemplate(id="main", frames=[frame], onPage=_footer)
    doc.addPageTemplates([template])

    styles = _styles()
    story = []

    _cover_page(story, styles, len(profiles), len(businesses), version_label, branding)
    _intro_page(story, styles, branding)
    _toc_page(story, styles, profiles)

    story.append(Paragraph("Member Profiles", styles["SectionHeading"]))
    for profile in profiles:
        _member_section(story, styles, profile, branding)

    story.append(PageBreak())
    _business_directory_section(story, styles, businesses)
    _closing_section(story, styles, len(profiles), len(businesses), branding)

    doc.build(story)
    return buffer.getvalue()
