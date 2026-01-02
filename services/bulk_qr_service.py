import hashlib
import json
from datetime import datetime
import qrcode
from PIL import Image, ImageDraw, ImageFont
from services.database import db
from services.s3_service import s3_service
import io
import zipfile

class BulkQRService:
    def __init__(self):
        """Initialize the service"""
        pass
    
    def generate_serial_number(self, ticket_type):
        """Generate unique serial number for QR code"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        base = f"{ticket_type}{timestamp}"
        hash_obj = hashlib.md5(base.encode())
        return f"HOLI2026-{hash_obj.hexdigest()[:8].upper()}"
    
    def generate_bulk_qr_codes(self, event_id, ticket_type, quantity, event_name, venue, event_date):
        """
        Generate multiple high-resolution QR codes in bulk.
        Creates entries in both qr_codes and passes collections.
        """
        try:
            from bson.objectid import ObjectId
            qr_codes = []
            
            for i in range(quantity):
                serial_num = self.generate_serial_number(ticket_type)
                sequence_num = db.get_next_sequence()
                
                # QR data payload
                qr_data = {
                    "serial": serial_num,
                    "event": event_name,
                    "name": ticket_type,
                    "sequence": sequence_num,
                    "ticket_type": ticket_type
                }
                
                qr_content = json.dumps(qr_data)
                
                # Generate High-Quality QR
                # Using ERROR_CORRECT_M for a balance between density and robustness
                qr = qrcode.QRCode(
                    version=None,
                    error_correction=qrcode.constants.ERROR_CORRECT_M,
                    box_size=20, # Larger box size for high-res base image
                    border=2
                )
                qr.add_data(qr_content)
                qr.make(fit=True)
                
                # Make image with high contrast
                qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
                
                # Convert to bytes for storage and upload
                img_byte_arr = io.BytesIO()
                qr_img.save(img_byte_arr, format='PNG')
                qr_img_bytes = img_byte_arr.getvalue()
                
                # Upload to S3
                filename = f"{serial_num}.png"
                success, url = s3_service.upload_file(
                    qr_img_bytes,
                    filename,
                    folder='qr_codes',
                    content_type='image/png'
                )
                
                parsed_event_date = event_date
                if isinstance(event_date, str) and event_date != 'TBD':
                    try:
                        from dateutil import parser
                        parsed_event_date = parser.parse(event_date)
                    except:
                        parsed_event_date = datetime.now()
                elif not isinstance(event_date, datetime):
                    parsed_event_date = datetime.now()
                
                try:
                    event_obj_id = ObjectId(event_id) if isinstance(event_id, str) else event_id
                except:
                    event_obj_id = event_id
                
                qr_doc = {
                    "serial_number": serial_num,
                    "sequence_number": sequence_num,
                    "name": ticket_type,
                    "ticket_type": ticket_type,
                    "event_id": event_obj_id,
                    "event_name": event_name,
                    "venue": venue,
                    "event_date": parsed_event_date,
                    "qr_data": qr_data,
                    "qr_image_bytes": qr_img_bytes,
                    "s3_key": f"qr_codes/{filename}",
                    "qr_url": url,
                    "used": False,
                    "created_at": datetime.now(),
                    "used_at": None,
                    "assigned_to": None,
                    "is_bulk": True
                }
                
                result = db.qr_codes.insert_one(qr_doc)
                qr_doc['_id'] = result.inserted_id
                
                # Create corresponding pass entry
                pass_doc = {
                    "serial_number": serial_num,
                    "sequence_number": sequence_num,
                    "attendee_name": ticket_type,
                    "user_name": ticket_type,
                    "ticket_type": ticket_type,
                    "event_name": event_name,
                    "event_date": parsed_event_date,
                    "venue": venue,
                    "event_id": event_obj_id,
                    "issued_at": datetime.now(),
                    "status": "valid",
                    "scanned": False,
                    "scanned_at": None,
                    "is_admin_generated": True,
                    "is_bulk_generated": True,
                    "s3_key": f"qr_codes/{filename}",
                    "pass_url": url
                }
                db.passes.insert_one(pass_doc)
                qr_codes.append(qr_doc)
            
            return {"success": True, "qr_codes": qr_codes, "count": len(qr_codes)}
            
        except Exception as e:
            print(f"Error: {e}")
            return {"success": False, "error": str(e)}

    def create_printable_sheet(self, qr_codes):
        """
        Creates an A4 PNG sheet (300 DPI) with 6 QR codes in a 2x3 grid.
        Optimized for high visibility and clear text labels.
        """
        try:
            # A4 size at 300 DPI (2480 x 3508 pixels)
            width, height = 2480, 3508
            sheet = Image.new('RGB', (width, height), 'white')
            draw = ImageDraw.Draw(sheet)
            
            # Layout configuration
            cols, rows = 2, 3
            qr_display_size = 750 # Larger for scannability
            x_start = 280
            y_start = 250
            x_spacing = 1000
            y_spacing = 1050
            
            # Try to load high-quality system fonts
            try:
                bold_font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
                reg_font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
                font_title = ImageFont.truetype(bold_font_path, 50)
                font_serial = ImageFont.truetype(bold_font_path, 42)
                font_label = ImageFont.truetype(reg_font_path, 32)
            except:
                font_title = font_serial = font_label = ImageFont.load_default()

            for idx, qr_code in enumerate(qr_codes[:6]):
                col = idx % cols
                row = idx // cols
                
                x = x_start + (col * x_spacing)
                y = y_start + (row * y_spacing)

                # Draw subtle cutting guide box
                draw.rectangle(
                    [x - 40, y - 40, x + qr_display_size + 40, y + qr_display_size + 250],
                    outline="#DEDEDE", 
                    width=2
                )

                # Handle QR Image
                qr_img = None
                if 'qr_image_bytes' in qr_code and qr_code['qr_image_bytes']:
                    qr_img = Image.open(io.BytesIO(qr_code['qr_image_bytes']))
                elif 'qr_data' in qr_code:
                    # Fallback regeneration
                    qr = qrcode.QRCode(version=1, box_size=20, border=2)
                    qr.add_data(json.dumps(qr_code['qr_data']))
                    qr.make(fit=True)
                    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')

                if qr_img:
                    # Using Resampling.LANCZOS ensures maximum sharpness when scaling down/up
                    qr_img = qr_img.resize((qr_display_size, qr_display_size), Image.Resampling.LANCZOS)
                    sheet.paste(qr_img, (x, y))
                
                # Sequence label (Top Right)
                seq_text = f"#{qr_code.get('sequence_number', 0):03d}"
                draw.text((x + qr_display_size - 100, y - 75), seq_text, fill="black", font=font_title)

                # Serial & Type Metadata
                text_y = y + qr_display_size + 40
                draw.text((x, text_y), "SERIAL NUMBER:", fill="#555555", font=font_label)
                draw.text((x, text_y + 45), qr_code.get('serial_number', 'N/A'), fill="black", font=font_serial)
                
                draw.text((x, text_y + 110), "TICKET TYPE:", fill="#555555", font=font_label)
                draw.text((x, text_y + 155), qr_code.get('ticket_type', 'N/A').upper(), fill="black", font=font_serial)

            # Save as PNG with 300 DPI metadata
            output = io.BytesIO()
            sheet.save(output, format='PNG', dpi=(300, 300))
            return output.getvalue()

        except Exception as e:
            print(f"Error creating printable sheet: {e}")
            raise

    def create_pass_sheet_pdf(self, qr_codes, event_name, ticket_type):
        """Create PDF with high-res QR codes and labels"""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from reportlab.lib.utils import ImageReader
            
            pdf_buffer = io.BytesIO()
            c = canvas.Canvas(pdf_buffer, pagesize=A4)
            width, height = A4
            
            for i in range(0, len(qr_codes), 6):
                if i > 0: c.showPage()
                batch = qr_codes[i:i+6]
                
                # Positioning
                qr_size = 180 
                x_start = 80
                y_start = height - 250
                x_gap = 260
                y_gap = 250
                
                for idx, qr_code in enumerate(batch):
                    row, col = idx // 2, idx % 2
                    x = x_start + (col * x_gap)
                    y = y_start - (row * y_gap)
                    
                    if qr_code.get('qr_image_bytes'):
                        qr_img = Image.open(io.BytesIO(qr_code['qr_image_bytes']))
                        c.drawImage(ImageReader(qr_img), x, y, width=qr_size, height=qr_size)
                    
                    c.setFont("Helvetica-Bold", 11)
                    c.drawString(x, y - 20, f"Seq: #{qr_code.get('sequence_number', 0):03d}")
                    c.setFont("Helvetica", 9)
                    c.drawString(x, y - 35, f"SN: {qr_code.get('serial_number', 'N/A')}")
                    c.drawString(x, y - 48, f"Type: {qr_code.get('ticket_type', 'N/A')}")
            
            c.save()
            return pdf_buffer.getvalue()
        except Exception as e:
            print(f"PDF Error: {e}")
            return None

    def create_batch_pdf(self, qr_codes, event_name, ticket_type, batch_size=6):
        """ZIP of multiple PDFs"""
        try:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i in range(0, len(qr_codes), batch_size):
                    batch = qr_codes[i:i+batch_size]
                    pdf_data = self.create_pass_sheet_pdf(batch, event_name, ticket_type)
                    if pdf_data:
                        zf.writestr(f"batch_{i//batch_size + 1}.pdf", pdf_data)
            zip_buffer.seek(0)
            return zip_buffer.getvalue()
        except: return None

    def create_batch_png(self, qr_codes, batch_size=6):
        """ZIP of multiple high-res PNG sheets"""
        try:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for i in range(0, len(qr_codes), batch_size):
                    batch = qr_codes[i:i+batch_size]
                    sheet_data = self.create_printable_sheet(batch)
                    if sheet_data:
                        zf.writestr(f"sheet_{i//batch_size + 1}.png", sheet_data)
            zip_buffer.seek(0)
            return zip_buffer.getvalue()
        except: return None

    def get_unused_qr_codes(self, ticket_type=None, skip=0, limit=50):
        try:
            query = {"used": False, "is_bulk": True}
            if ticket_type: query["ticket_type"] = ticket_type
            
            qr_codes = list(db.qr_codes.find(query).sort("created_at", -1).skip(skip).limit(limit))
            for qr in qr_codes:
                if 's3_key' in qr:
                    qr['qr_url'] = s3_service.generate_presigned_url(qr['s3_key'], expiration=3600)
            return qr_codes
        except: return []

    def get_unused_count(self, ticket_type=None):
        try:
            query = {"used": False, "is_bulk": True}
            if ticket_type: query["ticket_type"] = ticket_type
            return db.qr_codes.count_documents(query)
        except: return 0

    def get_qr_stats(self):
        try:
            total_qr = db.qr_codes.count_documents({"is_bulk": True})
            used_qr = db.qr_codes.count_documents({"is_bulk": True, "used": True})
            total_passes = db.passes.count_documents({"is_bulk_generated": True})
            scanned_passes = db.passes.count_documents({"is_bulk_generated": True, "scanned": True})
            
            ticket_type_stats = list(db.qr_codes.aggregate([
                {"$match": {"is_bulk": True}},
                {"$group": {
                    "_id": "$ticket_type",
                    "total": {"$sum": 1},
                    "used": {"$sum": {"$cond": ["$used", 1, 0]}},
                    "unused": {"$sum": {"$cond": ["$used", 0, 1]}}
                }}
            ]))
            return {
                "success": True, "total": total_qr, "used": used_qr, "unused": total_qr - used_qr,
                "passes_total": total_passes, "passes_scanned": scanned_passes,
                "by_type": ticket_type_stats, "synced": total_qr == total_passes
            }
        except: return {"success": False}

bulk_qr_service = BulkQRService()