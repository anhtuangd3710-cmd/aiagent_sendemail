"""
Email AI Agent - Flask Web Application
Modern UI for email automation with Azure OpenAI or Google Gemini
With Realtime WebSocket support, Authentication, and Auto-start Monitor
"""
from flask import Flask, render_template, request, jsonify, Response, make_response
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import json
import threading
import queue
import atexit
import os
from datetime import datetime

from services.email_service import EmailService
from services.email_monitor import EmailMonitor, ManualResponseProcessor
from services.auth_service import AuthService, login_required, admin_required
from config.settings import SENDER_EMAIL, AI_PROVIDER, AUTO_START_MONITOR

# Import Database Service based on DATABASE_URL
DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    from services.database_postgres import DatabaseServicePostgres as DatabaseService
    print("🗄️ Using PostgreSQL (Neon Database)")
else:
    from services.database import DatabaseService
    print("🗄️ Using SQLite")

# Import AI services based on provider
if AI_PROVIDER == "gemini":
    from services.ai_agent_gemini import AIAgentGemini as AIAgent
    from services.cv_evaluator_gemini import CVEvaluatorGemini as CVEvaluator
    print("🤖 Using Google Gemini AI")
else:
    from services.ai_agent import AIAgent
    from services.cv_evaluator import CVEvaluator
    print("🤖 Using Azure OpenAI")

app = Flask(__name__)
app.secret_key = 'email-agent-secret-key-change-in-production'
CORS(app, supports_credentials=True)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Initialize services
email_service = EmailService()
ai_agent = AIAgent()
database = DatabaseService()
cv_evaluator = CVEvaluator()
auth_service = AuthService(database)

# Store auth_service in app config for decorators
app.config['auth_service'] = auth_service

# Event queue for real-time updates (kept for backward compatibility)
event_queue = queue.Queue()

# Monitor instance - will be auto-started
monitor = None
monitor_auto_started = False

# Connected clients count
connected_clients = 0


def notification_callback(email_record, response, analysis):
    """Callback when a response is received - emit via WebSocket"""
    event_data = {
        "type": "response_received",
        "email_id": email_record['id'],
        "recipient_name": email_record['recipient_name'],
        "recipient_email": email_record['recipient_email'],
        "analysis": analysis,
        "timestamp": datetime.now().isoformat()
    }
    
    # Emit to all connected WebSocket clients
    socketio.emit('response_received', event_data)
    
    # Also put in queue for SSE fallback
    event_queue.put(event_data)


def cv_notification_callback(cv_evaluation, email_sent=False):
    """Callback for CV evaluation events"""
    event_data = {
        "type": "cv_evaluated",
        "cv_id": cv_evaluation.get('id'),
        "candidate_name": cv_evaluation.get('candidate_name'),
        "overall_score": cv_evaluation.get('overall_score'),
        "is_qualified": cv_evaluation.get('is_qualified'),
        "email_sent": email_sent,
        "timestamp": datetime.now().isoformat()
    }
    socketio.emit('cv_evaluated', event_data)


def auto_start_monitor():
    """Auto-start the email monitor on application startup"""
    global monitor, monitor_auto_started
    
    if monitor_auto_started:
        return
    
    try:
        monitor = EmailMonitor(
            email_service,
            ai_agent,
            database,
            notification_callback=notification_callback
        )
        monitor.start()
        monitor_auto_started = True
        print("✅ Email monitor auto-started successfully")
    except Exception as e:
        print(f"⚠️ Failed to auto-start monitor: {e}")


def stop_monitor_on_exit():
    """Stop monitor when application exits"""
    global monitor
    if monitor:
        try:
            monitor.stop()
            print("Monitor stopped on exit")
        except:
            pass


# Register cleanup
atexit.register(stop_monitor_on_exit)


# WebSocket Events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    global connected_clients
    connected_clients += 1
    
    # Auto-start monitor on first client connection
    if not monitor_auto_started:
        auto_start_monitor()
    
    emit('connected', {
        'status': 'connected', 
        'clients': connected_clients,
        'monitor_running': monitor is not None and monitor._running if monitor else False
    })
    print(f"Client connected. Total clients: {connected_clients}")


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    global connected_clients
    connected_clients -= 1
    print(f"Client disconnected. Total clients: {connected_clients}")


@socketio.on('check_responses_now')
def handle_check_responses():
    """Handle immediate response check request from client"""
    try:
        temp_monitor = EmailMonitor(
            email_service,
            ai_agent,
            database,
            notification_callback=notification_callback
        )
        temp_monitor.check_responses()
        emit('check_complete', {'success': True, 'message': 'Response check completed'})
    except Exception as e:
        emit('check_complete', {'success': False, 'error': str(e)})


# ==================== Authentication Routes ====================

@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register a new user"""
    try:
        data = request.json
        result = auth_service.register(
            username=data.get('username'),
            email=data.get('email'),
            password=data.get('password'),
            full_name=data.get('full_name')
        )
        
        if result['success']:
            return jsonify(result), 201
        return jsonify(result), 400
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login user"""
    try:
        data = request.json
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent')
        
        result = auth_service.login(
            username_or_email=data.get('username') or data.get('email'),
            password=data.get('password'),
            ip_address=ip_address,
            user_agent=user_agent
        )
        
        if result['success']:
            response = make_response(jsonify(result))
            # Set cookie for browser
            response.set_cookie(
                'auth_token', 
                result['token'],
                httponly=True,
                secure=False,  # Set True in production with HTTPS
                samesite='Lax',
                max_age=7*24*60*60  # 7 days
            )
            return response
        return jsonify(result), 401
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout user"""
    try:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            token = request.cookies.get('auth_token')
        
        if token:
            auth_service.logout(token)
        
        response = make_response(jsonify({"success": True, "message": "Đăng xuất thành công"}))
        response.delete_cookie('auth_token')
        return response
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    """Get current user info"""
    try:
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            token = request.cookies.get('auth_token')
        
        if not token:
            return jsonify({"success": False, "error": "Chưa đăng nhập"}), 401
        
        user = auth_service.validate_token(token)
        if not user:
            return jsonify({"success": False, "error": "Phiên đăng nhập hết hạn"}), 401
        
        return jsonify({"success": True, "user": user})
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auth/change-password', methods=['POST'])
@login_required
def change_password():
    """Change user password"""
    try:
        data = request.json
        result = auth_service.change_password(
            user_id=request.current_user['id'],
            old_password=data.get('old_password'),
            new_password=data.get('new_password')
        )
        
        if result['success']:
            return jsonify(result)
        return jsonify(result), 400
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auth/profile', methods=['PUT'])
@login_required
def update_profile():
    """Update user profile"""
    try:
        data = request.json
        result = auth_service.update_profile(
            user_id=request.current_user['id'],
            full_name=data.get('full_name'),
            email=data.get('email')
        )
        
        if result['success']:
            return jsonify(result)
        return jsonify(result), 400
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/admin/users', methods=['GET'])
@admin_required
def get_all_users():
    """Get all users (admin only)"""
    try:
        users = auth_service.get_all_users()
        return jsonify({"success": True, "users": users})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== User Settings API ====================

@app.route('/api/user/settings', methods=['GET'])
@login_required
def get_user_settings():
    """Get current user's settings"""
    try:
        settings = database.get_user_settings(request.current_user['id'])
        if settings:
            # Mask sensitive data
            masked_settings = dict(settings)
            if masked_settings.get('azure_openai_api_key'):
                masked_settings['azure_openai_api_key'] = '***' + masked_settings['azure_openai_api_key'][-4:]
            if masked_settings.get('gemini_api_key'):
                masked_settings['gemini_api_key'] = '***' + masked_settings['gemini_api_key'][-4:]
            if masked_settings.get('sender_password'):
                masked_settings['sender_password'] = '********'
            return jsonify({"success": True, "settings": masked_settings})
        return jsonify({"success": True, "settings": None})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/user/settings', methods=['POST', 'PUT'])
@login_required
def save_user_settings():
    """Save user settings"""
    try:
        data = request.json
        settings_id = database.save_user_settings(request.current_user['id'], data)
        return jsonify({
            "success": True,
            "message": "Cài đặt đã được lưu",
            "settings_id": settings_id
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/user/settings/full', methods=['GET'])
@login_required
def get_user_settings_full():
    """Get full settings (unmasked) for internal use"""
    try:
        settings = database.get_user_settings(request.current_user['id'])
        return jsonify({"success": True, "settings": settings})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ==================== Main Routes ====================

@app.route('/')
def index():
    """Main page - requires login"""
    return render_template('index.html')


@app.route('/login')
def login_page():
    """Login page"""
    return render_template('login.html')


@app.route('/api/send-email', methods=['POST'])
@login_required
def send_email():
    """Send an AI-generated email with optional attachments"""
    try:
        # Check if this is a multipart form (with attachments) or JSON
        if request.content_type and 'multipart/form-data' in request.content_type:
            # Handle form data with attachments
            data = request.form.to_dict()
            files = request.files.getlist('attachments')
        else:
            data = request.json
            files = []
        
        # Get user settings for email
        user_settings = database.get_user_settings(request.current_user['id'])
        sender_email_config = user_settings.get('sender_email') if user_settings else SENDER_EMAIL
        
        sender_name = data.get('sender_name')
        recipient_name = data.get('recipient_name')
        recipient_email = data.get('recipient_email')
        purpose = data.get('purpose')
        tone = data.get('tone', 'professional')
        language = data.get('language', 'vi')
        additional_context = data.get('additional_context')
        notification_email = data.get('notification_email') or sender_email_config or SENDER_EMAIL
        
        # Check if custom subject/body provided (from preview)
        custom_subject = data.get('custom_subject')
        custom_body = data.get('custom_body')
        
        # Validate required fields
        if not all([sender_name, recipient_name, recipient_email, purpose]):
            return jsonify({
                "success": False,
                "error": "Missing required fields"
            }), 400
        
        # Generate email using AI or use custom content
        if custom_subject and custom_body:
            generated_email = {
                'subject': custom_subject,
                'body': custom_body
            }
        else:
            generated_email = ai_agent.generate_email(
                sender_name=sender_name,
                recipient_name=recipient_name,
                recipient_email=recipient_email,
                purpose=purpose,
                tone=tone,
                language=language,
                additional_context=additional_context
            )
        
        # Process attachments
        attachments = []
        for file in files:
            if file and file.filename:
                # Read file content
                content = file.read()
                # Get content type
                content_type = file.content_type or 'application/octet-stream'
                
                attachments.append({
                    'filename': file.filename,
                    'content': content,
                    'content_type': content_type
                })
        
        # Send the email with attachments
        success = email_service.send_email(
            recipient_email=recipient_email,
            subject=generated_email['subject'],
            body=generated_email['body'],
            attachments=attachments if attachments else None
        )
        
        if success:
            # Save to database
            email_id = database.save_sent_email(
                sender_name=sender_name,
                sender_email=notification_email,
                recipient_name=recipient_name,
                recipient_email=recipient_email,
                subject=generated_email['subject'],
                body=generated_email['body'],
                purpose=purpose
            )
            
            return jsonify({
                "success": True,
                "email_id": email_id,
                "subject": generated_email['subject'],
                "body": generated_email['body'],
                "message": "Email sent successfully!"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Failed to send email. Please check your email configuration."
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/preview-email', methods=['POST'])
@login_required
def preview_email():
    """Preview AI-generated email without sending"""
    try:
        data = request.json
        
        sender_name = data.get('sender_name')
        recipient_name = data.get('recipient_name')
        recipient_email = data.get('recipient_email')
        purpose = data.get('purpose')
        tone = data.get('tone', 'professional')
        language = data.get('language', 'vi')
        additional_context = data.get('additional_context')
        
        if not all([sender_name, recipient_name, recipient_email, purpose]):
            return jsonify({
                "success": False,
                "error": "Missing required fields"
            }), 400
        
        # Generate email using AI
        generated_email = ai_agent.generate_email(
            sender_name=sender_name,
            recipient_name=recipient_name,
            recipient_email=recipient_email,
            purpose=purpose,
            tone=tone,
            language=language,
            additional_context=additional_context
        )
        
        return jsonify({
            "success": True,
            "subject": generated_email['subject'],
            "body": generated_email['body']
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/emails', methods=['GET'])
@login_required
def get_emails():
    """Get all tracked emails"""
    try:
        emails = database.get_all_emails()
        
        # Parse analysis JSON for each email
        for email in emails:
            if email.get('analysis'):
                try:
                    email['analysis'] = json.loads(email['analysis'])
                except:
                    pass
        
        return jsonify({
            "success": True,
            "emails": emails
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/emails/<int:email_id>', methods=['GET'])
@login_required
def get_email(email_id):
    """Get a specific email by ID"""
    try:
        email = database.get_email_by_id(email_id)
        
        if email:
            return jsonify({
                "success": True,
                "email": email
            })
        else:
            return jsonify({
                "success": False,
                "error": "Email not found"
            }), 404
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/emails/<int:email_id>', methods=['DELETE'])
@login_required
def delete_email(email_id):
    """Delete a specific email by ID"""
    try:
        database.delete_email(email_id)
        return jsonify({
            "success": True,
            "message": "Email deleted successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/emails/delete-multiple', methods=['POST'])
@login_required
def delete_multiple_emails():
    """Delete multiple emails by IDs"""
    try:
        data = request.json
        email_ids = data.get('email_ids', [])
        
        if not email_ids:
            return jsonify({
                "success": False,
                "error": "No email IDs provided"
            }), 400
        
        deleted_count = database.delete_emails(email_ids)
        return jsonify({
            "success": True,
            "message": f"Deleted {deleted_count} emails",
            "deleted_count": deleted_count
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/emails/delete-all', methods=['DELETE'])
@login_required
def delete_all_emails():
    """Delete all sent emails"""
    try:
        deleted_count = database.delete_all_emails()
        return jsonify({
            "success": True,
            "message": f"Deleted all {deleted_count} emails",
            "deleted_count": deleted_count
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/cv/delete-all', methods=['DELETE'])
@login_required
def delete_all_cv_evaluations():
    """Delete all CV evaluations"""
    try:
        deleted_count = database.delete_all_cv_evaluations()
        return jsonify({
            "success": True,
            "message": f"Deleted all {deleted_count} CV evaluations",
            "deleted_count": deleted_count
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/cv/<int:cv_id>', methods=['DELETE'])
@login_required
def delete_cv_evaluation(cv_id):
    """Delete a specific CV evaluation by ID"""
    try:
        database.delete_cv_evaluation(cv_id)
        return jsonify({
            "success": True,
            "message": "CV evaluation deleted successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/cv/delete-multiple', methods=['POST'])
@login_required
def delete_multiple_cv_evaluations():
    """Delete multiple CV evaluations by IDs"""
    try:
        data = request.json
        cv_ids = data.get('cv_ids', [])
        
        if not cv_ids:
            return jsonify({
                "success": False,
                "error": "No CV IDs provided"
            }), 400
        
        deleted_count = database.delete_cv_evaluations(cv_ids)
        return jsonify({
            "success": True,
            "message": f"Deleted {deleted_count} CV evaluations",
            "deleted_count": deleted_count
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/data/delete-all', methods=['DELETE'])
@login_required
def delete_all_data():
    """Delete all emails and CV evaluations"""
    try:
        email_count = database.delete_all_emails()
        cv_count = database.delete_all_cv_evaluations()
        return jsonify({
            "success": True,
            "message": f"Deleted {email_count} emails and {cv_count} CV evaluations",
            "deleted_emails": email_count,
            "deleted_cvs": cv_count
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/data/stats', methods=['GET'])
@login_required
def get_data_stats():
    """Get statistics about emails and CV evaluations"""
    try:
        email_count = database.get_email_count()
        cv_count = database.get_cv_count()
        return jsonify({
            "success": True,
            "email_count": email_count,
            "cv_count": cv_count
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/check-responses', methods=['POST'])
@login_required
def check_responses():
    """Check for responses once"""
    try:
        temp_monitor = EmailMonitor(
            email_service,
            ai_agent,
            database,
            notification_callback=notification_callback
        )
        temp_monitor.check_responses()
        
        return jsonify({
            "success": True,
            "message": "Response check completed"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/check-imap', methods=['GET'])
@login_required
def check_imap():
    """Check IMAP connection status"""
    try:
        result = email_service.check_imap_connection()
        return jsonify(result)
    except Exception as e:
        return jsonify({
            "success": False,
            "message": "Error checking IMAP",
            "details": str(e)
        })


@app.route('/api/monitor/start', methods=['POST'])
@login_required
def start_monitor():
    """Start the email monitoring service"""
    global monitor
    
    try:
        if monitor and monitor._running:
            return jsonify({
                "success": False,
                "message": "Monitor is already running"
            })
        
        monitor = EmailMonitor(
            email_service,
            ai_agent,
            database,
            notification_callback=notification_callback
        )
        monitor.start()
        
        return jsonify({
            "success": True,
            "message": "Monitor started successfully"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/monitor/stop', methods=['POST'])
@login_required
def stop_monitor():
    """Stop the email monitoring service"""
    global monitor
    
    try:
        if monitor:
            monitor.stop()
            monitor = None
            
        return jsonify({
            "success": True,
            "message": "Monitor stopped successfully"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/monitor/status', methods=['GET'])
@login_required
def monitor_status():
    """Get monitor status"""
    global monitor
    
    return jsonify({
        "success": True,
        "running": monitor is not None and monitor._running
    })


@app.route('/api/analyze-response', methods=['POST'])
@login_required
def analyze_response():
    """Manually analyze a response"""
    try:
        data = request.json
        
        email_id = data.get('email_id')
        response_text = data.get('response_text')
        response_subject = data.get('response_subject', 'Re: Response')
        
        if not email_id or not response_text:
            return jsonify({
                "success": False,
                "error": "Missing required fields"
            }), 400
        
        processor = ManualResponseProcessor(
            email_service,
            ai_agent,
            database
        )
        
        result = processor.process_response(
            sent_email_id=email_id,
            response_text=response_text,
            response_subject=response_subject
        )
        
        return jsonify({
            "success": True,
            "analysis": result['analysis'],
            "notification": result['notification'],
            "notification_sent": result['notification_sent']
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/events')
def events():
    """Server-Sent Events for real-time updates"""
    def generate():
        while True:
            try:
                event = event_queue.get(timeout=30)
                yield f"data: {json.dumps(event)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')


# ==================== CV Evaluation API ====================

@app.route('/api/cv/upload', methods=['POST'])
@login_required
def upload_cv_file():
    """Upload và trích xuất nội dung từ file CV"""
    try:
        if 'file' not in request.files:
            return jsonify({
                "success": False,
                "error": "Không tìm thấy file"
            }), 400
        
        file = request.files['file']
        
        if file.filename == '':
            return jsonify({
                "success": False,
                "error": "Chưa chọn file"
            }), 400
        
        # Get file extension
        filename = file.filename
        file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        
        # Validate extension
        allowed_extensions = ['pdf', 'doc', 'docx', 'txt']
        if file_ext not in allowed_extensions:
            return jsonify({
                "success": False,
                "error": f"Định dạng file không hỗ trợ. Chỉ chấp nhận: {', '.join(allowed_extensions)}"
            }), 400
        
        # Read file content
        file_content = file.read()
        
        # Extract text based on file type
        extracted_text = ""
        
        if file_ext == 'txt':
            # Plain text file
            try:
                extracted_text = file_content.decode('utf-8')
            except UnicodeDecodeError:
                extracted_text = file_content.decode('latin-1')
                
        elif file_ext == 'pdf':
            # PDF file
            try:
                import PyPDF2
                import io
                
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
                text_parts = []
                
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
                
                extracted_text = '\n'.join(text_parts)
                
            except ImportError:
                return jsonify({
                    "success": False,
                    "error": "Thư viện PyPDF2 chưa được cài đặt. Chạy: pip install PyPDF2"
                }), 500
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": f"Lỗi đọc file PDF: {str(e)}"
                }), 500
                
        elif file_ext in ['doc', 'docx']:
            # Word document
            try:
                from docx import Document
                import io
                
                doc = Document(io.BytesIO(file_content))
                text_parts = []
                
                for para in doc.paragraphs:
                    if para.text.strip():
                        text_parts.append(para.text)
                
                # Also extract from tables
                for table in doc.tables:
                    for row in table.rows:
                        row_text = ' | '.join(cell.text.strip() for cell in row.cells if cell.text.strip())
                        if row_text:
                            text_parts.append(row_text)
                
                extracted_text = '\n'.join(text_parts)
                
            except ImportError:
                return jsonify({
                    "success": False,
                    "error": "Thư viện python-docx chưa được cài đặt. Chạy: pip install python-docx"
                }), 500
            except Exception as e:
                return jsonify({
                    "success": False,
                    "error": f"Lỗi đọc file Word: {str(e)}"
                }), 500
        
        # Check if we got any content
        if not extracted_text.strip():
            return jsonify({
                "success": False,
                "error": "Không thể trích xuất nội dung từ file. File có thể trống hoặc chứa hình ảnh."
            }), 400
        
        return jsonify({
            "success": True,
            "content": extracted_text,
            "filename": filename,
            "file_type": file_ext
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/cv/evaluate', methods=['POST'])
@login_required
def evaluate_cv():
    """Đánh giá CV ứng viên"""
    try:
        data = request.json
        
        candidate_name = data.get('candidate_name')
        candidate_email = data.get('candidate_email')
        job_title = data.get('job_title')
        job_requirements = data.get('job_requirements')
        cv_content = data.get('cv_content')
        company_name = data.get('company_name', '')
        auto_send = data.get('auto_send', True)  # Tự động gửi email nếu >= 85%
        
        if not all([candidate_name, candidate_email, job_title, job_requirements, cv_content]):
            return jsonify({
                "success": False,
                "error": "Thiếu thông tin bắt buộc"
            }), 400
        
        # Đánh giá CV
        evaluation = cv_evaluator.evaluate_cv(
            cv_content=cv_content,
            job_title=job_title,
            job_requirements=job_requirements,
            company_name=company_name
        )
        
        # Lưu kết quả đánh giá
        cv_id = database.save_cv_evaluation(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            job_title=job_title,
            job_requirements=job_requirements,
            cv_content=cv_content,
            company_name=company_name,
            overall_score=evaluation.get('overall_score', 0),
            is_qualified=evaluation.get('is_qualified', False),
            evaluation_result=evaluation
        )
        
        result = {
            "success": True,
            "cv_id": cv_id,
            "evaluation": evaluation,
            "is_qualified": evaluation.get('is_qualified', False),
            "overall_score": evaluation.get('overall_score', 0)
        }
        
        # Tự động gửi email nếu đạt >= 85% và auto_send = True
        if auto_send and evaluation.get('is_qualified', False):
            email_result = send_cv_invitation_email(cv_id, evaluation, candidate_name, 
                                                     candidate_email, job_title, company_name)
            result['email_sent'] = email_result.get('success', False)
            result['email_id'] = email_result.get('email_id')
            result['message'] = "Ứng viên đạt yêu cầu! Email mời phỏng vấn đã được gửi."
        elif evaluation.get('is_qualified', False):
            result['message'] = "Ứng viên đạt yêu cầu! Bạn có thể gửi email mời phỏng vấn."
        else:
            result['message'] = f"Ứng viên chưa đạt yêu cầu (Điểm: {evaluation.get('overall_score', 0)}/100, cần >= 85)"
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


def send_cv_invitation_email(cv_id, evaluation, candidate_name, candidate_email, job_title, company_name):
    """Helper function to send invitation email"""
    try:
        # Tạo email mời phỏng vấn
        email_content = cv_evaluator.generate_interview_invitation(
            candidate_name=candidate_name,
            candidate_email=candidate_email,
            job_title=job_title,
            company_name=company_name or "Công ty",
            evaluation_result=evaluation
        )
        
        # Gửi email
        success = email_service.send_email(
            recipient_email=candidate_email,
            subject=email_content['subject'],
            body=email_content['body']
        )
        
        if success:
            # Lưu vào database
            email_id = database.save_sent_email(
                sender_name="HR " + (company_name or ""),
                sender_email=SENDER_EMAIL,
                recipient_name=candidate_name,
                recipient_email=candidate_email,
                subject=email_content['subject'],
                body=email_content['body'],
                purpose=f"Mời phỏng vấn vị trí {job_title}"
            )
            
            # Cập nhật trạng thái CV
            database.update_cv_evaluation_email_sent(cv_id, email_id)
            
            return {"success": True, "email_id": email_id}
        
        return {"success": False, "error": "Không thể gửi email"}
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.route('/api/cv/send-email/<int:cv_id>', methods=['POST'])
@login_required
def send_cv_email(cv_id):
    """Gửi/gửi lại email cho ứng viên"""
    try:
        cv_data = database.get_cv_evaluation_by_id(cv_id)
        
        if not cv_data:
            return jsonify({
                "success": False,
                "error": "Không tìm thấy CV"
            }), 404
        
        data = request.json or {}
        email_type = data.get('email_type', 'invitation')  # invitation or rejection
        
        if email_type == 'invitation':
            email_content = cv_evaluator.generate_interview_invitation(
                candidate_name=cv_data['candidate_name'],
                candidate_email=cv_data['candidate_email'],
                job_title=cv_data['job_title'],
                company_name=cv_data['company_name'] or "Công ty",
                evaluation_result=cv_data.get('evaluation_result', {}),
                interview_details=data.get('interview_details')
            )
        else:
            email_content = cv_evaluator.generate_rejection_email(
                candidate_name=cv_data['candidate_name'],
                job_title=cv_data['job_title'],
                company_name=cv_data['company_name'] or "Công ty",
                evaluation_result=cv_data.get('evaluation_result', {})
            )
        
        # Gửi email
        success = email_service.send_email(
            recipient_email=cv_data['candidate_email'],
            subject=email_content['subject'],
            body=email_content['body']
        )
        
        if success:
            email_id = database.save_sent_email(
                sender_name="HR " + (cv_data['company_name'] or ""),
                sender_email=SENDER_EMAIL,
                recipient_name=cv_data['candidate_name'],
                recipient_email=cv_data['candidate_email'],
                subject=email_content['subject'],
                body=email_content['body'],
                purpose=f"{'Mời phỏng vấn' if email_type == 'invitation' else 'Thông báo kết quả'} - {cv_data['job_title']}"
            )
            
            database.update_cv_evaluation_email_sent(cv_id, email_id)
            
            return jsonify({
                "success": True,
                "email_id": email_id,
                "message": "Email đã được gửi thành công!"
            })
        else:
            return jsonify({
                "success": False,
                "error": "Không thể gửi email"
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/cv/allow-resend/<int:cv_id>', methods=['POST'])
@login_required
def allow_resend_cv_email(cv_id):
    """Cho phép gửi lại email cho CV (sau khi đã có phản hồi)"""
    try:
        database.allow_resend_email(cv_id)
        return jsonify({
            "success": True,
            "message": "Đã cho phép gửi lại email"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/cv/list', methods=['GET'])
@login_required
def list_cv_evaluations():
    """Lấy danh sách tất cả CV đã đánh giá"""
    try:
        evaluations = database.get_all_cv_evaluations()
        return jsonify({
            "success": True,
            "evaluations": evaluations
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/cv/<int:cv_id>', methods=['GET'])
@login_required
def get_cv_evaluation(cv_id):
    """Lấy chi tiết một CV đánh giá"""
    try:
        cv_data = database.get_cv_evaluation_by_id(cv_id)
        
        if cv_data:
            # Lấy thông tin email liên quan nếu có
            if cv_data.get('sent_email_id'):
                email_data = database.get_email_by_id(cv_data['sent_email_id'])
                cv_data['email_info'] = email_data
            
            return jsonify({
                "success": True,
                "cv": cv_data
            })
        else:
            return jsonify({
                "success": False,
                "error": "Không tìm thấy CV"
            }), 404
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/cv/preview-email', methods=['POST'])
@login_required
def preview_cv_email():
    """Xem trước email sẽ gửi cho ứng viên"""
    try:
        data = request.json
        
        candidate_name = data.get('candidate_name')
        candidate_email = data.get('candidate_email')
        job_title = data.get('job_title')
        company_name = data.get('company_name', 'Công ty')
        email_type = data.get('email_type', 'invitation')
        evaluation_result = data.get('evaluation_result', {})
        interview_details = data.get('interview_details')
        
        if email_type == 'invitation':
            email_content = cv_evaluator.generate_interview_invitation(
                candidate_name=candidate_name,
                candidate_email=candidate_email,
                job_title=job_title,
                company_name=company_name,
                evaluation_result=evaluation_result,
                interview_details=interview_details
            )
        else:
            email_content = cv_evaluator.generate_rejection_email(
                candidate_name=candidate_name,
                job_title=job_title,
                company_name=company_name,
                evaluation_result=evaluation_result
            )
        
        return jsonify({
            "success": True,
            "subject": email_content['subject'],
            "body": email_content['body']
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route('/api/system-info', methods=['GET'])
def get_system_info():
    """Get system information including AI provider"""
    from config.settings import AI_PROVIDER, GEMINI_MODEL
    
    return jsonify({
        "success": True,
        "ai_provider": AI_PROVIDER,
        "ai_model": GEMINI_MODEL if AI_PROVIDER == "gemini" else "Azure OpenAI",
        "sender_email": SENDER_EMAIL,
        "realtime_enabled": True
    })


if __name__ == '__main__':
    # Sử dụng SocketIO để chạy server với WebSocket support
    print("🚀 Starting Email AI Agent with Realtime WebSocket support...")
    print(f"🤖 AI Provider: {AI_PROVIDER.upper()}")
    print("📡 WebSocket enabled for instant notifications")
    
    # Auto-start monitor if configured
    if AUTO_START_MONITOR:
        print("🔄 Auto-starting email monitor...")
        auto_start_monitor()
    else:
        print("ℹ️ Monitor will start on first WebSocket connection")
    
    socketio.run(app, debug=True, port=5000, allow_unsafe_werkzeug=True)
