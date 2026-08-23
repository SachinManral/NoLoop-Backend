import os
import sys
import base64
import json
from pathlib import Path

# Force stdout encoding to utf-8
sys.stdout.reconfigure(encoding='utf-8')

dotenv_path = Path(__file__).resolve().parents[1] / ".env"
if dotenv_path.exists():
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

synthetic_dir = Path(__file__).resolve().parents[1] / "data" / "synthetic"
png_path = synthetic_dir / "mockdata.png"
pdf_path = synthetic_dir / "mockpdf.pdf"

print("==========================================================")
print("  NOLOOP PLATFORM - ADVANCED LAYOUT-AWARE OCR & PARSER    ")
print("==========================================================")

import fitz  # PyMuPDF
from PIL import Image
import httpx
from rapidocr_onnxruntime import RapidOCR

ocr_engine = RapidOCR()
groq_key = os.environ.get("GROQ_API_KEY")

def extract_structured_text_from_image_bytes(img_bytes: bytes) -> str:
    """
    Layout-aware OCR: Extracts text blocks and sorts them into logical spatial streams.
    Handles 2-column medical bills/invoices without scrambling line items.
    """
    res, _ = ocr_engine(img_bytes)
    if not res:
        return ""
    
    # Render dimensions for spatial thresholding
    img = Image.open(fitz.io.BytesIO(img_bytes))
    w, h = img.width, img.height
    
    # 1. Identify section bounds (find BILL SUMMARY / INVESTIGATIONS / CLINICAL SUMMARY)
    bill_y = None
    for coords, text, score in res:
        if 'BILL SUMMARY' in text.upper():
            bill_y = min(pt[1] for pt in coords)
            break
            
    header_boxes = []
    left_table_boxes = []
    right_table_boxes = []
    
    for coords, text, score in res:
        x_min = min(pt[0] for pt in coords)
        y_min = min(pt[1] for pt in coords)
        
        # If in the BILL SUMMARY table section, split by left column vs right column
        if bill_y and y_min >= bill_y - 10:
            if x_min < w * 0.52:
                left_table_boxes.append((y_min, x_min, text))
            else:
                right_table_boxes.append((y_min, x_min, text))
        else:
            header_boxes.append((y_min, x_min, text))
            
    # Spatial sorting (Top-to-Bottom, Left-to-Right)
    def format_boxes(boxes):
        boxes.sort(key=lambda b: (b[0], b[1]))
        lines = []
        curr_line = []
        curr_y = None
        for y, x, text in boxes:
            if curr_y is None or abs(y - curr_y) < 14:
                curr_line.append((x, text))
                if curr_y is None: curr_y = y
            else:
                curr_line.sort(key=lambda item: item[0])
                lines.append("  ".join(t for _, t in curr_line))
                curr_line = [(x, text)]
                curr_y = y
        if curr_line:
            curr_line.sort(key=lambda item: item[0])
            lines.append("  ".join(t for _, t in curr_line))
        return "\n".join(lines)

    text_output = format_boxes(header_boxes)
    if left_table_boxes or right_table_boxes:
        text_output += "\n\n--- BILL SUMMARY (LEFT COLUMN) ---\n" + format_boxes(left_table_boxes)
        text_output += "\n\n--- BILL SUMMARY (RIGHT COLUMN) ---\n" + format_boxes(right_table_boxes)
        
    return text_output

def parse_with_llm(raw_layout_text: str, doc_name: str) -> dict:
    """Send layout-preserved OCR text to LLM to extract accurate JSON claim payload."""
    if not groq_key:
        print("GROQ_API_KEY missing, skipping LLM structuring.")
        return {}
    
    prompt = (
        "You are an expert AI medical bill auditor and claim adjudicator for NoLoop Platform.\n"
        f"You are provided with LAYOUT-PRESERVED OCR text from '{doc_name}'.\n"
        "Notice that the BILL SUMMARY section is separated into LEFT COLUMN and RIGHT COLUMN to avoid mixing line items.\n"
        "Carefully parse all fields and return ONLY a JSON object with EXACTLY these fields:\n"
        "{\n"
        '  "hospitalName": "Full name of hospital",\n'
        '  "patientName": "Full name of patient",\n'
        '  "patientAge": 42,\n'
        '  "patientGender": "M" or "F",\n'
        '  "policyNo": "Insurance policy number",\n'
        '  "insuranceProvider": "TPA or Insurance company name",\n'
        '  "procedure": "Procedure performed (e.g. IV fluids & supportive care, Appendectomy, Threatened Miscarriage treatment)",\n'
        '  "primaryDiagnosis": "Primary Diagnosis with code",\n'
        '  "secondaryDiagnosis": "Secondary Diagnosis if present",\n'
        '  "admittedAt": "YYYY-MM-DD",\n'
        '  "dischargedAt": "YYYY-MM-DD",\n'
        '  "lengthOfStayDays": 4,\n'
        '  "lineItems": [\n'
        '    {"desc": "Line item description", "amountRupees": 8000.0}\n'
        '  ],\n'
        '  "grossTotalRupees": 22500.0,\n'
        '  "discountRupees": 2250.0,\n'
        '  "netPayableRupees": 20250.0,\n'
        '  "confidenceScore": 0.99\n'
        "}\n"
        "Make sure line item descriptions match their EXACT amounts from their respective columns!\n"
        f"\nLAYOUT-PRESERVED OCR TEXT:\n{raw_layout_text}"
    )
    
    try:
        res = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {groq_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=30.0
        )
        if res.status_code == 200:
            return json.loads(res.json()["choices"][0]["message"]["content"])
        else:
            print("LLM Error:", res.status_code, res.text)
    except Exception as e:
        print("LLM exception:", e)
    return {}

# 1. PROCESS MOCKDATA.PNG
print("\n" + "="*60)
print(" 1. ACCURATE LAYOUT OCR ON mockdata.png ")
print("="*60)
with open(png_path, "rb") as f:
    png_bytes = f.read()

png_layout_text = extract_structured_text_from_image_bytes(png_bytes)
print("\n[EXTRACTED LAYOUT-AWARE TEXT]:\n", png_layout_text)

png_structured = parse_with_llm(png_layout_text, "mockdata.png")
print("\n[ACCURATE STRUCTURED JSON (mockdata.png)]:")
print(json.dumps(png_structured, indent=2))

# 2. PROCESS MOCKPDF.PDF
print("\n" + "="*60)
print(" 2. ACCURATE LAYOUT OCR ON mockpdf.pdf ")
print("="*60)
pdf_doc = fitz.open(str(pdf_path))
pix = pdf_doc[0].get_pixmap(dpi=200)
pdf_bytes = pix.tobytes("png")

pdf_layout_text = extract_structured_text_from_image_bytes(pdf_bytes)
print("\n[EXTRACTED LAYOUT-AWARE TEXT]:\n", pdf_layout_text)

pdf_structured = parse_with_llm(pdf_layout_text, "mockpdf.pdf")
print("\n[ACCURATE STRUCTURED JSON (mockpdf.pdf)]:")
print(json.dumps(pdf_structured, indent=2))

print("\n==========================================================")
print("  ACCURATE OCR & PARSING COMPLETED SUCCESSFULLY           ")
print("==========================================================")
