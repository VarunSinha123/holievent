from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for, send_file
from flask_login import login_required, current_user
from functools import wraps
from datetime import datetime
import io
import zipfile
import requests
from services.bulk_qr_service import bulk_qr_service 

bulk_qr_bp = Blueprint('bulk_qr', __name__, url_prefix='/bulk-qr')

def admin_required(f):
    """Decorator for admin/super_admin access using Flask-Login"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        # Check if user is authenticated and has admin role
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        
        # Check if user has admin or super_admin role
        if current_user.role not in ['admin', 'super_admin']:
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        
        return f(*args, **kwargs)
    return decorated_function

# Page Route
@bulk_qr_bp.route('/')
@admin_required
def bulk_qr_page():
    return render_template('bulk_qr.html')

# Generate bulk QR codes (not full passes)
@bulk_qr_bp.route('/api/generate', methods=['POST'])
@admin_required
def bulk_generate():
    try:
        from bson import json_util
        import json
        
        data = request.get_json(silent=True) or {}
        
        event_id = data.get('event_id')
        ticket_type = data.get('ticket_type')
        quantity = int(data.get('quantity', 1))
        event_name = data.get('event_name', 'SAVORA') 
        venue = data.get('venue', 'Venue')
        event_date = data.get('event_date', 'TBD')

        if not event_id or not ticket_type:
            return jsonify({'success': False, 'message': 'Event ID and Ticket Type are required'}), 400

        if quantity <= 0 or quantity > 500:
            return jsonify({'success': False, 'message': 'Invalid quantity (1-500)'}), 400

        result = bulk_qr_service.generate_bulk_qr_codes(
            event_id=event_id,
            ticket_type=ticket_type,
            quantity=quantity,
            event_name=event_name,
            venue=venue,
            event_date=event_date
        )

        if result is None:
            return jsonify({'success': False, 'message': 'Service returned no result'}), 500

        if result.get('success'):
            # Clean up the QR codes data for JSON serialization
            qr_codes = result.get('qr_codes', [])
            cleaned_qr_codes = []
            
            for qr in qr_codes:
                qr_copy = qr.copy()
                
                # Convert ObjectId to string
                if '_id' in qr_copy:
                    qr_copy['_id'] = str(qr_copy['_id'])
                
                # Convert event_id if it's an ObjectId
                if 'event_id' in qr_copy and hasattr(qr_copy['event_id'], '__str__'):
                    qr_copy['event_id'] = str(qr_copy['event_id'])
                
                # Handle datetime objects
                if 'created_at' in qr_copy and isinstance(qr_copy['created_at'], datetime):
                    qr_copy['created_at'] = qr_copy['created_at'].isoformat()
                
                # Remove binary data (too large for JSON response)
                if 'qr_image_bytes' in qr_copy:
                    del qr_copy['qr_image_bytes']
                
                cleaned_qr_codes.append(qr_copy)
            
            return jsonify({
                'success': True,
                'passes': cleaned_qr_codes,
                'count': result.get('count', 0),
                'message': f"Successfully generated {result.get('count')} QR codes"
            })

        return jsonify(result)

    except Exception as e:
        print(f"Error in bulk_generate: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f"Internal Server Error: {str(e)}"}), 500

# Get Statistics
@bulk_qr_bp.route('/api/stats')
@admin_required
def get_qr_stats():
    try:
        from bson import json_util
        import json
        
        stats = bulk_qr_service.get_qr_stats()
        
        # Clean up any ObjectId in the stats
        if 'by_type' in stats and isinstance(stats['by_type'], list):
            for item in stats['by_type']:
                if '_id' in item and hasattr(item['_id'], '__str__'):
                    item['_id'] = str(item['_id'])
        
        return jsonify(stats)
    except Exception as e:
        print(f"Error in get_qr_stats: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'total': 0,
            'used': 0,
            'unused': 0,
            'by_type': [],
            'message': str(e)
        }), 500

# List unused QR codes
@bulk_qr_bp.route('/api/list-unused')
@admin_required
def list_unused():
    try:
        from bson import json_util
        import json
        
        ticket_type = request.args.get('ticket_type')
        limit = int(request.args.get('limit', 100))
        
        qr_codes = bulk_qr_service.get_unused_qr_codes(ticket_type=ticket_type, limit=limit)
        
        formatted_qr_codes = []
        if qr_codes:
            for qr in qr_codes:
                qr_copy = qr.copy()
                
                # Convert ObjectId to string
                if '_id' in qr_copy:
                    qr_copy['_id'] = str(qr_copy['_id'])
                
                # Convert event_id if it's an ObjectId
                if 'event_id' in qr_copy and hasattr(qr_copy['event_id'], '__str__'):
                    qr_copy['event_id'] = str(qr_copy['event_id'])
                
                # Handle datetime objects
                if 'created_at' in qr_copy and isinstance(qr_copy['created_at'], datetime):
                    qr_copy['created_at'] = qr_copy['created_at'].isoformat()
                
                if 'used_at' in qr_copy and isinstance(qr_copy['used_at'], datetime):
                    qr_copy['used_at'] = qr_copy['used_at'].isoformat()
                
                # Remove binary data before sending to frontend (too large)
                if 'qr_image_bytes' in qr_copy:
                    del qr_copy['qr_image_bytes']
                
                formatted_qr_codes.append(qr_copy)

        return jsonify({'success': True, 'qr_codes': formatted_qr_codes})
    except Exception as e:
        print(f"Error in list_unused: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# Download passes as PDF
@bulk_qr_bp.route('/api/download-pdf', methods=['GET', 'POST'])
@admin_required
def download_pdf():
    try:
        # Support both GET (query params) and POST (JSON body)
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
        else:
            data = request.args
        
        ticket_type = data.get('ticket_type')
        event_name = data.get('event_name', 'Event')
        limit = int(data.get('limit', 100))
        
        # Get QR codes to download
        qr_codes = bulk_qr_service.get_unused_qr_codes(ticket_type=ticket_type, limit=limit)
        
        if not qr_codes:
            return jsonify({'success': False, 'message': 'No QR codes found'}), 404

        # Generate PDF with passes
        pdf_data = bulk_qr_service.create_pass_sheet_pdf(qr_codes, event_name, ticket_type or 'General')
        
        if not pdf_data:
            return jsonify({'success': False, 'message': 'PDF generation failed'}), 500

        return send_file(
            io.BytesIO(pdf_data),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'qr_codes_{ticket_type or "all"}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        )
    except Exception as e:
        print(f"Error in download_pdf: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# Download Sheet (PNG format)
@bulk_qr_bp.route('/api/download-sheet', methods=['POST'])
@admin_required
def download_sheet():
    try:
        data = request.get_json(silent=True) or {}
        qr_codes = data.get('qr_codes', [])
        
        if not qr_codes:
            ticket_type = data.get('ticket_type')
            qr_codes = bulk_qr_service.get_unused_qr_codes(ticket_type=ticket_type, limit=100)
        
        if not qr_codes:
            return jsonify({'success': False, 'message': 'No codes provided'}), 400

        sheet_data = bulk_qr_service.create_printable_sheet(qr_codes)
        
        if not sheet_data:
            return jsonify({'success': False, 'message': 'Sheet generation failed'}), 500

        return send_file(
            io.BytesIO(sheet_data),
            mimetype='image/png',
            as_attachment=True,
            download_name=f'qr_sheet_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        )
    except Exception as e:
        print(f"Error in download_sheet: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Download batch PDFs as ZIP
@bulk_qr_bp.route('/api/download-batch-pdf', methods=['POST'])
@admin_required
def download_batch_pdf():
    try:
        data = request.get_json(silent=True) or {}
        ticket_type = data.get('ticket_type')
        event_name = data.get('event_name', 'Event')
        limit = int(data.get('limit', 200))
        batch_size = 6
        
        # Get QR codes to download
        qr_codes = bulk_qr_service.get_unused_qr_codes(ticket_type=ticket_type, limit=limit)
        
        if not qr_codes:
            return jsonify({'success': False, 'message': 'No QR codes found'}), 404

        # Generate ZIP with batched PDFs
        zip_data = bulk_qr_service.create_batch_pdf(
            qr_codes, 
            event_name, 
            ticket_type or 'General',
            batch_size=batch_size
        )
        
        if not zip_data:
            return jsonify({'success': False, 'message': 'Batch PDF generation failed'}), 500

        return send_file(
            io.BytesIO(zip_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'passes_batches_{ticket_type or "all"}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        )
    except Exception as e:
        print(f"Error in download_batch_pdf: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500

# Download batch PNGs as ZIP
@bulk_qr_bp.route('/api/download-batch-png', methods=['POST'])
@admin_required
def download_batch_png():
    try:
        data = request.get_json(silent=True) or {}
        ticket_type = data.get('ticket_type')
        limit = int(data.get('limit', 200))
        batch_size = 6
        
        # Get QR codes to download
        qr_codes = bulk_qr_service.get_unused_qr_codes(ticket_type=ticket_type, limit=limit)
        
        if not qr_codes:
            return jsonify({'success': False, 'message': 'No QR codes found'}), 404

        # Generate ZIP with batched PNGs
        zip_data = bulk_qr_service.create_batch_png(qr_codes, batch_size=batch_size)
        
        if not zip_data:
            return jsonify({'success': False, 'message': 'Batch PNG generation failed'}), 500

        return send_file(
            io.BytesIO(zip_data),
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'sheets_batches_{ticket_type or "all"}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.zip'
        )
    except Exception as e:
        print(f"Error in download_batch_png: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500