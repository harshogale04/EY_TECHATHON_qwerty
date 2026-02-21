# app.py
"""
Flask Web Application for RFP Tender Analysis (Updated)
=========================================================
Multi-URL support: passes source_urls list into graph state so
sales_agent scrapes all of them and picks the best tender overall.
"""

from flask import Flask, request, jsonify, send_file, render_template
from flask_cors import CORS
import os
import io
import tempfile
import requests
from werkzeug.utils import secure_filename
import json
from datetime import datetime
import traceback
import pandas as pd

from graph import build_graph
from utils.loader import load_oem
from config import OEM_PATH
from services.formatter import format_rfp
import PyPDF2

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = tempfile.gettempdir()
ALLOWED_EXTENSIONS = {'pdf'}
MAX_FILE_SIZE = 16 * 1024 * 1024

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

try:
    PRODUCT_DB = load_oem(OEM_PATH)
    TEST_SERVICES_DB = pd.read_excel(OEM_PATH, sheet_name="Testing Services")
    print(f"✅ Loaded {len(PRODUCT_DB)} products and {len(TEST_SERVICES_DB)} test services")
except Exception as e:
    print(f"⚠️  Warning: Could not load database: {e}")
    PRODUCT_DB = None
    TEST_SERVICES_DB = None


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
    except Exception as e:
        raise Exception(f"Failed to extract text from PDF: {str(e)}")
    return text.strip()


def process_tender_data(tender_text, source_info):
    """
    Run one tender through the full pipeline (sales agent bypassed).
    Used by the PDF upload flow — RFP injected directly into state.
    """
    if PRODUCT_DB is None:
        raise Exception("Product database not loaded")

    try:
        structured_rfp = format_rfp(tender_text)
    except Exception:
        structured_rfp = {
            "project_overview": tender_text[:500],
            "scope_of_supply": "",
            "technical_specifications": tender_text,
            "testing_requirements": "",
            "delivery_timeline": "",
            "pricing_details": "",
            "evaluation_criteria": "",
            "submission_format": ""
        }

    structured_rfp.update({
        "projectName": source_info.get('name', 'Uploaded Tender'),
        "issued_by": source_info.get('issuer', 'Unknown'),
        "category": source_info.get('category', 'General'),
        "submissionDeadline": source_info.get('deadline', ''),
    })

    graph = build_graph()
    state = {
        "product_db": PRODUCT_DB,
        "test_services_db": TEST_SERVICES_DB,
        "rfps": [structured_rfp],
    }
    final_state = graph.invoke(state)
    return _build_result(final_state, source_info)


def process_tender_urls(urls, source_info):
    """
    Run the full pipeline with the sales agent active.
    Passes source_urls into state — sales_agent scrapes every URL,
    pools all tenders found across all sites, picks the best one.
    """
    if PRODUCT_DB is None:
        raise Exception("Product database not loaded")

    graph = build_graph()
    state = {
        "product_db": PRODUCT_DB,
        "test_services_db": TEST_SERVICES_DB,
        "source_urls": urls,   # ← sales_agent reads this
    }

    print(f"🚀 Running pipeline with {len(urls)} source URL(s): {urls}")
    final_state = graph.invoke(state)
    return _build_result(final_state, source_info)


def _build_result(final_state, source_info):
    """Shared helper: extract frontend-ready dict from final graph state."""
    final_response   = final_state.get("final_response", {})
    bid_viability    = final_response.get("bid_viability", {})
    line_items       = final_response.get("line_items", [])
    summary          = final_response.get("summary", {})
    component_scores = bid_viability.get("component_scores", {})

    tech_match_scores = []
    for item in line_items:
        top3 = item.get("top_3_recommendations", [])
        if top3:
            tech_match_scores.append(top3[0].get("spec_match_pct", 0))
    avg_tech_match = (sum(tech_match_scores) / len(tech_match_scores)) if tech_match_scores else 0

    raw_score = bid_viability.get("score", 0)
    normalised_score = raw_score / 100.0 if raw_score > 1 else raw_score

    return {
        "final_response":    final_response,
        "pdf_available":     final_state.get("pdf_bytes") is not None,
        "source":            source_info,
        "score":             normalised_score,
        "price":             summary.get("grand_total_inr", 0),
        "technical_matches": line_items,
        "detailed_score": {
            "recommendation": bid_viability.get("recommendation", "N/A"),
            "component_scores": {
                "technical_match": avg_tech_match,
                **component_scores,
            },
        },
    }


@app.route('/')
def index():
    return render_template('index.html')


@app.route("/api/agents/all")
def get_all_agents():
    from services.supabase_client import get_from_table
    agents = {}
    try:
        scoring = get_from_table("scoring_results")
        if scoring:
            agents["scoring_agent"] = scoring[-1]

        tenders = get_from_table("tenders")
        if tenders:
            agents["sales_agent"] = {
                "tenders_in_window": len(tenders),
                "all_tenders": [
                    {"name": t.get("project_name", ""), "deadline": t.get("submission_deadline", "")}
                    for t in tenders
                ],
                "selected_rfp": tenders[0].get("project_name", ""),
            }

        tech = get_from_table("technical_results")
        if tech:
            agents["technical_agent"] = tech[-1].get("full_output", tech[-1])

        pricing = get_from_table("pricing_results")
        if pricing:
            agents["pricing_agent"] = pricing[-1].get("full_output", pricing[-1])
    except Exception as e:
        print(f"⚠️  Supabase fetch failed: {e}")

    return jsonify(agents)


@app.route("/agents_all")
def agents_all_page():
    return render_template("agents_all.html")


@app.route('/api/analyze-url', methods=['POST'])
def analyze_url():
    """
    Accepts:
      { "urls": ["https://site1.com", "https://site2.com"] }  ← multi-URL (new)
      { "url": "https://site1.com" }                          ← single URL (legacy)

    The sales agent scrapes ALL provided URLs, pools every tender found,
    filters to 3-month window, selects the single best one across all sources.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400

        # Normalise input
        if 'urls' in data and isinstance(data['urls'], list):
            urls = [u.strip() for u in data['urls'] if u.strip()]
        elif 'url' in data and data['url']:
            urls = [data['url'].strip()]
        else:
            return jsonify({'error': 'Provide "urls" (array) or "url" (string)'}), 400

        if not urls:
            return jsonify({'error': 'At least one URL is required'}), 400

        source_info = {
            'type':      'url',
            'urls':      urls,
            'url':       urls[0],
            'url_count': len(urls),
            'name':      data.get('name', f'Web Tender ({len(urls)} source{"s" if len(urls) > 1 else ""})'),
            'issuer':    data.get('issuer', 'Unknown'),
            'deadline':  data.get('deadline', ''),
            'category':  data.get('category', 'General'),
        }

        result = process_tender_urls(urls, source_info)
        result = json.loads(json.dumps(result, default=str))
        return jsonify({'success': True, 'data': result})

    except Exception as e:
        print(f"Error in analyze-url: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analyze-pdf', methods=['POST'])
def analyze_pdf():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        if not allowed_file(file.filename):
            return jsonify({'error': 'Only PDF files are allowed'}), 400

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        try:
            tender_text = extract_text_from_pdf(filepath)
            if not tender_text or len(tender_text) < 100:
                return jsonify({'error': 'Could not extract sufficient text from PDF'}), 400

            source_info = {
                'type':     'pdf',
                'filename': filename,
                'name':     request.form.get('name', filename),
                'issuer':   request.form.get('issuer', 'Unknown'),
                'deadline': request.form.get('deadline', ''),
                'category': request.form.get('category', 'General')
            }

            result = process_tender_data(tender_text, source_info)
            result = json.loads(json.dumps(result, default=str))
            return jsonify({'success': True, 'data': result})

        finally:
            if os.path.exists(filepath):
                os.remove(filepath)

    except Exception as e:
        print(f"Error in analyze-pdf: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/download-report', methods=['POST'])
def download_report():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        from pdf_generator_v2 import generate_rfp_pdf
        rfp_data = data.get("final_response") or data
        pdf_bytes = generate_rfp_pdf(rfp_data)
        output_filename = f"rfp_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        return send_file(
            io.BytesIO(pdf_bytes),
            as_attachment=True,
            download_name=output_filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        print(f"Error in download-report: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'database_loaded': PRODUCT_DB is not None,
        'products_count': len(PRODUCT_DB) if PRODUCT_DB is not None else 0,
        'test_services_loaded': TEST_SERVICES_DB is not None,
        'test_services_count': len(TEST_SERVICES_DB) if TEST_SERVICES_DB is not None else 0,
    })


if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    print("\n" + "="*60)
    print("🚀 RFP Tender Analysis Web Application")
    print("="*60)
    print(f"📊 Products: {len(PRODUCT_DB) if PRODUCT_DB is not None else 0}")
    print(f"🧪 Test services: {len(TEST_SERVICES_DB) if TEST_SERVICES_DB is not None else 0}")
    print("🌐 Starting server at http://localhost:5001")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5001)