"""
Flask Web Application for RFP Tender Analysis
==============================================
Provides web interface for analyzing tenders via URLs or PDF uploads
"""

from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import os
import tempfile
import requests
from werkzeug.utils import secure_filename
import json
from datetime import datetime
import traceback

# Import your existing agents and utilities
from graph import build_graph
from utils.loader import load_oem
from config import OEM_PATH
from services.formatter import format_rfp
import PyPDF2

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Load product database once at startup
try:
    PRODUCT_DB = load_oem(OEM_PATH)
    print(f"✅ Loaded {len(PRODUCT_DB)} products from database")
except Exception as e:
    print(f"⚠️ Warning: Could not load product database: {e}")
    PRODUCT_DB = None


def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(pdf_path):
    """Extract text content from PDF file"""
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
    except Exception as e:
        raise Exception(f"Failed to extract text from PDF: {str(e)}")
    
    return text.strip()


def scrape_tender_url(url):
    """
    Scrape tender data from URL
    
    This is a simplified version - you may need to adapt based on actual websites
    """
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # For now, return raw HTML/text
        # In production, you'd parse the HTML to extract structured data
        return {
            'raw_content': response.text[:10000],  # Limit to first 10k chars
            'url': url,
            'scraped_at': datetime.now().isoformat()
        }
    except Exception as e:
        raise Exception(f"Failed to scrape URL: {str(e)}")


def process_tender_data(tender_text, source_info):
    """
    Process tender text through the analysis pipeline
    
    Args:
        tender_text: Raw tender text content
        source_info: Dictionary with source metadata (url or filename)
        
    Returns:
        Dictionary with analysis results
    """
    if PRODUCT_DB is None:
        raise Exception("Product database not loaded")
    
    # Format the raw text into structured sections using Gemini
    try:
        structured_rfp = format_rfp(tender_text)
    except Exception as e:
        # If formatting fails, create a basic structure
        structured_rfp = {
            "project_overview": tender_text[:500],
            "scope_of_supply": "",
            "technical_specifications": tender_text,
            "acceptance_and_test_requirements": "",
            "delivery_timeline": "",
            "pricing_details": "",
            "evaluation_criteria": "",
            "submission_format": ""
        }
    
    # Add metadata
    structured_rfp.update({
        "projectName": source_info.get('name', 'Uploaded Tender'),
        "issued_by": source_info.get('issuer', 'Unknown'),
        "category": source_info.get('category', 'General'),
        "submissionDeadline": source_info.get('deadline', ''),
    })
    
    # Build the analysis graph
    graph = build_graph()
    
    # Create initial state with the single RFP
    state = {
        "product_db": PRODUCT_DB,
        "rfps": [structured_rfp]
    }
    
    # Run the analysis pipeline
    final_state = graph.invoke(state)
    
    # Extract results
    result = {
        "rfp": structured_rfp,
        "technical_matches": final_state.get("tech_matches", [[]])[0],
        "price": final_state.get("prices", [0])[0],
        "score": final_state.get("scores", [0])[0],
        "detailed_score": final_state.get("detailed_scores", [{}])[0] if "detailed_scores" in final_state else {},
        "pdf_path": final_state.get("pdf_path"),
        "source": source_info
    }
    
    return result


@app.route('/')
def index():
    """Serve the main web interface"""
    return render_template('index.html')


@app.route('/api/analyze-url', methods=['POST'])
def analyze_url():
    """
    Analyze tender from URL
    
    Request JSON:
    {
        "url": "https://example.com/tender",
        "name": "Optional tender name",
        "issuer": "Optional issuer name",
        "deadline": "Optional deadline"
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'url' not in data:
            return jsonify({'error': 'URL is required'}), 400
        
        url = data['url']
        
        # Scrape the URL
        scraped_data = scrape_tender_url(url)
        tender_text = scraped_data['raw_content']
        
        # Process the tender
        source_info = {
            'type': 'url',
            'url': url,
            'name': data.get('name', 'Web Tender'),
            'issuer': data.get('issuer', 'Unknown'),
            'deadline': data.get('deadline', ''),
            'category': data.get('category', 'General')
        }
        
        result = process_tender_data(tender_text, source_info)
        
        # Convert numpy types to native Python types for JSON serialization
        result = json.loads(json.dumps(result, default=str))
        
        return jsonify({
            'success': True,
            'data': result
        })
        
    except Exception as e:
        print(f"Error in analyze-url: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/analyze-pdf', methods=['POST'])
def analyze_pdf():
    """
    Analyze tender from uploaded PDF
    
    Multipart form data:
    - file: PDF file
    - name: Optional tender name
    - issuer: Optional issuer name
    - deadline: Optional deadline
    """
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only PDF files are allowed'}), 400
        
        # Save the uploaded file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Extract text from PDF
            tender_text = extract_text_from_pdf(filepath)
            
            if not tender_text or len(tender_text) < 100:
                return jsonify({'error': 'Could not extract sufficient text from PDF'}), 400
            
            # Process the tender
            source_info = {
                'type': 'pdf',
                'filename': filename,
                'name': request.form.get('name', filename),
                'issuer': request.form.get('issuer', 'Unknown'),
                'deadline': request.form.get('deadline', ''),
                'category': request.form.get('category', 'General')
            }
            
            result = process_tender_data(tender_text, source_info)
            
            # Convert numpy types to native Python types
            result = json.loads(json.dumps(result, default=str))
            
            return jsonify({
                'success': True,
                'data': result
            })
            
        finally:
            # Clean up uploaded file
            if os.path.exists(filepath):
                os.remove(filepath)
        
    except Exception as e:
        print(f"Error in analyze-pdf: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/download-report', methods=['POST'])
def download_report():
    """
    Generate and download PDF report for analyzed tender
    
    Request JSON: Complete analysis result from analyze-url or analyze-pdf
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Import PDF generator
        from pdf_generator_v2 import generate_rfp_pdf
        
        # Prepare data for PDF generation
        pdf_data = {
            "rfp": data.get("rfp", {}),
            "matches": data.get("technical_matches", []),
            "price": float(data.get("price", 0)),
            "score": float(data.get("score", 0))
        }
        
        # Generate PDF
        output_filename = f"rfp_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        
        generate_rfp_pdf(pdf_data, output_path)
        
        # Send file and clean up
        return send_file(
            output_path,
            as_attachment=True,
            download_name=output_filename,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        print(f"Error in download-report: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'database_loaded': PRODUCT_DB is not None,
        'products_count': len(PRODUCT_DB) if PRODUCT_DB is not None else 0
    })


if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    print("\n" + "="*60)
    print("🚀 RFP Tender Analysis Web Application")
    print("="*60)
    print(f"📊 Products in database: {len(PRODUCT_DB) if PRODUCT_DB is not None else 0}")

    print("🌐 Starting server at http://localhost:5001")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5001)