"""Downloadable, verification-linked Silabs & Co completion certificates."""
from io import BytesIO
import qrcode
from flask import current_app, url_for
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ISSUER = "SILAB & CO TECHNOLOGIES LTD."


def _fit(c, text, font, max_size, max_width):
    size = max_size
    while size > 13 and c.stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def render_certificate(certificate):
    """Render a certificate using immutable name/course snapshots.

    This certificate confirms learner-marked module completion, not a
    proctored exam or verified skill competency.
    """
    width, height = landscape(A4)
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(width, height), pageCompression=1)
    pdf.setTitle("Silabs Certificate of Completion — " + certificate.course_title)
    pdf.setAuthor(ISSUER)
    navy = HexColor("#081369")
    blue = HexColor("#3041BE")
    gold = HexColor("#B99A42")
    ink = HexColor("#23334A")

    pdf.setFillColor(navy)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setFillColor(HexColor("#FAFBFF"))
    pdf.rect(16, 16, width - 32, height - 32, fill=1, stroke=0)
    pdf.setStrokeColor(gold)
    pdf.setLineWidth(2.2)
    pdf.rect(27, 27, width - 54, height - 54, fill=0, stroke=1)
    pdf.setLineWidth(0.5)
    pdf.setStrokeColor(blue)
    pdf.rect(34, 34, width - 68, height - 68, fill=0, stroke=1)

    # Draw the Silabs circular monogram directly as vector artwork.
    # No network, external font, or image file needed for certificate PDFs.
    cx, cy = width / 2, 468
    pdf.setStrokeColor(navy)
    pdf.setLineWidth(4)
    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.circle(cx, cy, 43, stroke=1, fill=1)
    pdf.setFillColor(blue)
    pdf.setFont("Helvetica-Bold", 5.3)
    pdf.drawCentredString(cx, cy + 30, "SILAB & CO.")
    pdf.setFillColor(navy)
    pdf.drawCentredString(cx, cy - 33, "TECHNOLOGIES LTD.")
    shape = pdf.beginPath()
    shape.moveTo(cx - 17, cy + 21)
    shape.lineTo(cx + 18, cy + 21)
    shape.lineTo(cx + 18, cy + 10)
    shape.lineTo(cx - 6, cy + 10)
    shape.lineTo(cx - 6, cy - 3)
    shape.lineTo(cx + 3, cy - 3)
    shape.lineTo(cx + 3, cy - 13)
    shape.lineTo(cx - 17, cy - 13)
    shape.close()
    pdf.setFillColor(navy)
    pdf.drawPath(shape, fill=1, stroke=0)
    shape = pdf.beginPath()
    shape.moveTo(cx + 3, cy + 4)
    shape.lineTo(cx + 18, cy + 4)
    shape.lineTo(cx + 18, cy - 21)
    shape.lineTo(cx - 17, cy - 21)
    shape.lineTo(cx - 17, cy - 10)
    shape.lineTo(cx + 6, cy - 10)
    shape.lineTo(cx + 6, cy - 3)
    shape.lineTo(cx + 3, cy - 3)
    shape.close()
    pdf.setFillColor(blue)
    pdf.drawPath(shape, fill=1, stroke=0)

    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawCentredString(width / 2, 405, ISSUER)
    pdf.setFillColor(gold)
    pdf.setFont("Helvetica-Bold", 25)
    pdf.drawCentredString(width / 2, 357, "CERTIFICATE OF COMPLETION")
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(width / 2, 327, "This is to certify that")
    pdf.setFont("Helvetica-Bold", _fit(
        pdf, certificate.learner_name, "Helvetica-Bold", 28, width - 150))
    pdf.drawCentredString(width / 2, 288, certificate.learner_name)
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(width / 2, 256, "has recorded completion of all lessons in")
    pdf.setFillColor(blue)
    pdf.setFont("Helvetica-Bold", _fit(
        pdf, certificate.course_title, "Helvetica-Bold", 21, width - 160))
    pdf.drawCentredString(width / 2, 218, certificate.course_title)
    pdf.setFillColor(ink)
    pdf.setFont("Helvetica", 10)
    pdf.drawCentredString(
        width / 2, 185,
        "{} self-reported video lessons completed".format(certificate.lesson_count),
    )

    pdf.setStrokeColor(gold)
    pdf.line(135, 156, width - 135, 156)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawCentredString(width / 2, 134,
                          "Issued: {}".format(certificate.issued_at.strftime("%d %B %Y")))
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(width / 2, 113,
                          "Certificate ID: {}".format(certificate.code.upper()))
    pdf.drawCentredString(width / 2, 96,
                          "Verify authenticity using the certificate ID or QR code.")
    pdf.setFont("Helvetica", 7)
    pdf.setFillColor(HexColor("#6A7384"))
    pdf.drawCentredString(
        width / 2, 53,
        "Learning completion record — not a proctored assessment or professional licence.",
    )

    base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    if not base or base.startswith("http://localhost"):
        base = "https://myplatoon.vercel.app" if not current_app.testing else "http://localhost"
    url = base + url_for("learning.verify_certificate", code=certificate.code)
    qr = qrcode.QRCode(box_size=3, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="#081369", back_color="white").convert("RGB")
    pdf.drawImage(ImageReader(qr_img), width - 118, 57, 70, 70)

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer
