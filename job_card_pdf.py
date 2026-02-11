# job_card_pdf.py  (UPDATED — QR CODE ON PDF, QR ONLY (no URL text))
import os
from io import BytesIO
from datetime import datetime
from typing import Optional, List, Dict, Any

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# ✅ QR generation (requires: qrcode[pil])
import qrcode


def build_job_card_pdf(
    job_card: Dict[str, Any],
    signoff: Optional[Dict[str, Any]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
    brand_title: str = "Apricot Property Solutions",
    logo_path: str = "logo1.png",
    footer_text: str = "Apricot Property Solutions • Nairobi, Kenya • support@apricotproperty.co.ke • +254 735 524 444",
    public_verify_url: Optional[str] = None,  # ✅ pass the WhatsApp verification link here
) -> bytes:
    """
    Returns PDF bytes.

    - Renders logo + brand header
    - Professional layout (key details grid, sections)
    - Renders QR code that links to the PUBLIC verification URL (same as WhatsApp link)
      ✅ QR ONLY (does NOT print the URL)
    - Renders signature image (if signoff contains signature_blob or signature_path)
    - Footer contact details
    - Page numbers

    Requirements:
      - pip install "qrcode[pil]"
    """

    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"Job Card #{job_card.get('id')}",
        author=brand_title,
    )

    styles = getSampleStyleSheet()

    # Add custom styles (safe add)
    if "SectionHeader" not in styles:
        styles.add(
            ParagraphStyle(
                name="SectionHeader",
                parent=styles["Heading2"],
                fontSize=11.5,
                textColor=colors.HexColor("#1A237E"),
                spaceBefore=10,
                spaceAfter=6,
            )
        )

    if "MetaSmall" not in styles:
        styles.add(
            ParagraphStyle(
                name="MetaSmall",
                parent=styles["Normal"],
                fontSize=8.8,
                leading=11,
                textColor=colors.HexColor("#444444"),
            )
        )

    if "BodySmall" not in styles:
        styles.add(
            ParagraphStyle(
                name="BodySmall",
                parent=styles["Normal"],
                fontSize=9.4,
                leading=12,
            )
        )

    # -------------------------
    # Helpers
    # -------------------------
    def _safe(v):
        return "—" if v is None or str(v).strip() == "" else str(v)

    def _money(v):
        try:
            return f"KSh {float(v):,.2f}"
        except Exception:
            return "—"

    def _dt(v):
        if not v:
            return "—"
        try:
            if hasattr(v, "strftime"):
                return v.strftime("%Y-%m-%d %H:%M")
            return str(v)
        except Exception:
            return str(v)

    def _make_qr_png_bytes(url: str) -> bytes:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=6,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        b = BytesIO()
        img.save(b, format="PNG")
        return b.getvalue()

    # -------------------------
    # Page decorations
    # -------------------------
    def _draw_footer(canvas, doc_obj):
        canvas.saveState()

        w, _h = A4
        x_left = doc_obj.leftMargin
        x_right = w - doc_obj.rightMargin
        y = 10 * mm

        # thin line
        canvas.setStrokeColor(colors.HexColor("#C7C7C7"))
        canvas.setLineWidth(0.6)
        canvas.line(x_left, y + 8, x_right, y + 8)

        # footer text
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.setFont("Helvetica", 8.5)
        canvas.drawString(x_left, y, footer_text)

        # page numbers
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.setFont("Helvetica", 8.5)
        canvas.drawRightString(x_right, y, f"Page {canvas.getPageNumber()}")

        canvas.restoreState()

    # -------------------------
    # Build content
    # -------------------------
    elements = []

    # Header: logo + brand
    brand_p = Paragraph(f"<b>{brand_title}</b>", styles["Heading1"])
    meta_p = Paragraph(f"Generated: {_dt(datetime.now())}", styles["MetaSmall"])

    header_data = []
    col_widths = [175 * mm]

    if logo_path and os.path.exists(logo_path):
        logo = Image(logo_path, width=22 * mm, height=22 * mm, kind="proportional")
        header_data = [[logo, [brand_p, meta_p]]]
        col_widths = [28 * mm, 147 * mm]
    else:
        header_data = [[[brand_p, meta_p]]]
        col_widths = [175 * mm]

    header_table = Table(header_data, colWidths=col_widths)
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    elements.append(header_table)

    elements.append(
        HRFlowable(
            width="100%",
            thickness=1.2,
            color=colors.HexColor("#1A237E"),
            spaceBefore=6,
            spaceAfter=10,
        )
    )

    # Title
    elements.append(Paragraph("JOB CARD", styles["Heading2"]))
    elements.append(Paragraph(f"Reference ID: <b>#{_safe(job_card.get('id'))}</b>", styles["MetaSmall"]))
    elements.append(Spacer(1, 8))

    # ✅ QR block (top-right area in a 2-col table) — QR ONLY
    if public_verify_url:
        try:
            qr_png = _make_qr_png_bytes(public_verify_url)
            qr_img = Image(BytesIO(qr_png), width=30 * mm, height=30 * mm)  # square QR
            qr_label = Paragraph("Scan to verify", styles["MetaSmall"])

            qr_table = Table(
                [[
                    Paragraph("", styles["Normal"]),
                    [qr_img, Spacer(1, 2), qr_label],
                ]],
                colWidths=[120 * mm, 55 * mm],
            )
            qr_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 0),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                    ]
                )
            )
            elements.append(qr_table)
            elements.append(Spacer(1, 6))
        except Exception:
            # If QR creation fails for any reason, don't break PDF generation
            pass

    # Key details grid (Assigned To removed)
    data = [
        [
            "Ticket:",
            f"#{_safe(job_card.get('ticket_id'))}" if job_card.get("ticket_id") else "Standalone",
            "Status:",
            _safe(job_card.get("status")).upper(),
        ],
        [
            "Property:",
            _safe(job_card.get("property_name")),
            "Unit:",
            _safe(job_card.get("unit_number")),
        ],
        [
            "Created By:",
            _safe(job_card.get("created_by_name")),
            "Created At:",
            _dt(job_card.get("created_at")),
        ],
        [
            "Est. Cost:",
            _money(job_card.get("estimated_cost")),
            "Actual Cost:",
            _money(job_card.get("actual_cost")),
        ],
    ]

    t = Table(data, colWidths=[22 * mm, 66 * mm, 22 * mm, 65 * mm])
    t.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#666666")),
                ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#666666")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                # status cell emphasis
                ("BACKGROUND", (3, 0), (3, 0), colors.whitesmoke),
                ("BOX", (3, 0), (3, 0), 0.6, colors.HexColor("#BDBDBD")),
                # subtle outer border
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#E0E0E0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#EEEEEE")),
            ]
        )
    )
    elements.append(t)
    elements.append(Spacer(1, 10))

    # Description
    elements.append(Paragraph("Project Description", styles["SectionHeader"]))
    elements.append(Paragraph(_safe(job_card.get("description")), styles["BodySmall"]))

    # Activities
    elements.append(Paragraph("Activities / Work Log", styles["SectionHeader"]))
    acts = _safe(job_card.get("activities")).replace("\n", "<br/>")
    elements.append(Paragraph(acts, styles["BodySmall"]))

    # Attachments list (metadata only)
    if attachments:
        elements.append(Paragraph("Attachments", styles["SectionHeader"]))
        lines = [f"• {_safe(a.get('filename'))} ({_safe(a.get('media_type'))})" for a in attachments]
        elements.append(Paragraph("<br/>".join(lines), styles["MetaSmall"]))

    # Signoff section
    elements.append(Spacer(1, 14))
    elements.append(
        HRFlowable(
            width="100%",
            thickness=0.6,
            color=colors.HexColor("#C7C7C7"),
            spaceBefore=4,
            spaceAfter=8,
        )
    )
    elements.append(Paragraph("Official Sign-Off", styles["SectionHeader"]))

    if signoff:
        sign_data = [
            ["Authorized By:", _safe(signoff.get("signed_by_name")), "Role:", _safe(signoff.get("signed_by_role"))],
            ["Date Signed:", _dt(signoff.get("signed_at")), "", ""],
        ]
        stbl = Table(sign_data, colWidths=[28 * mm, 62 * mm, 14 * mm, 71 * mm])
        stbl.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        elements.append(stbl)

        if signoff.get("signoff_notes"):
            elements.append(Paragraph(f"<b>Notes:</b> {_safe(signoff.get('signoff_notes'))}", styles["BodySmall"]))

        # Signature rendering
        sig_path = signoff.get("signature_path")
        sig_blob = signoff.get("signature_blob")

        try:
            if not sig_path and sig_blob:
                tmp_path = f"/tmp/jobcard_sig_{job_card.get('id')}.png"
                with open(tmp_path, "wb") as f:
                    f.write(sig_blob)
                sig_path = tmp_path

            if sig_path and os.path.exists(sig_path):
                elements.append(Spacer(1, 6))
                elements.append(Paragraph("Signature:", styles["MetaSmall"]))
                elements.append(Image(sig_path, width=45 * mm, height=18 * mm, kind="proportional"))
        finally:
            pass
    else:
        elements.append(Paragraph("<i>Pending physical or digital signature.</i>", styles["MetaSmall"]))

    # Build PDF with footer + page numbers
    doc.build(elements, onFirstPage=_draw_footer, onLaterPages=_draw_footer)
    return buf.getvalue()
