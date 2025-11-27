/**
 * Email AI Agent - Frontend JavaScript
 * Modern, responsive UI interactions
 */

// API Base URL
const API_BASE = '';

// State
let currentEmailId = null;
let currentCvId = null;
let emails = [];
let cvEvaluations = [];
let monitorRunning = false;
let socket = null;
let wsConnected = false;

// DOM Elements
const pageTitle = document.getElementById('page-title');
const pageSubtitle = document.getElementById('page-subtitle');
const navItems = document.querySelectorAll('.nav-item');
const pages = document.querySelectorAll('.page');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initCompose();
    initInbox();
    initMonitor();
    initModals();
    initCvEvaluation();
    initWebSocket();  // Sử dụng WebSocket thay vì SSE
    loadEmails();
    loadCvEvaluations();
    checkMonitorStatus();
});

// ==================== Navigation ====================

function initNavigation() {
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            navigateTo(page);
        });
    });
}

function navigateTo(page) {
    // Update nav
    navItems.forEach(item => {
        item.classList.toggle('active', item.dataset.page === page);
    });
    
    // Update pages
    pages.forEach(p => {
        p.classList.toggle('active', p.id === `page-${page}`);
    });
    
    // Update header
    const titles = {
        compose: { title: 'Soạn Email Mới', subtitle: 'Sử dụng AI để tạo email chuyên nghiệp' },
        inbox: { title: 'Email Đã Gửi', subtitle: 'Quản lý và theo dõi các email đã gửi' },
        cv: { title: 'Đánh giá CV', subtitle: 'AI đánh giá CV ứng viên và tự động gửi thư mời' },
        monitor: { title: 'Giám sát phản hồi', subtitle: 'Theo dõi và phân tích phản hồi tự động' },
        settings: { title: 'Cài đặt', subtitle: 'Cấu hình và hướng dẫn sử dụng' }
    };
    
    if (titles[page]) {
        pageTitle.textContent = titles[page].title;
        pageSubtitle.textContent = titles[page].subtitle;
    }
    
    // Refresh data
    if (page === 'inbox') {
        loadEmails();
    }
    if (page === 'cv') {
        loadCvEvaluations();
    }
}

// ==================== Compose Page ====================

function initCompose() {
    const previewBtn = document.getElementById('preview-btn');
    const sendBtn = document.getElementById('send-btn');
    const closePreview = document.getElementById('close-preview');
    const previewSection = document.getElementById('preview-section');
    const composeContainer = document.querySelector('.compose-container');
    
    previewBtn.addEventListener('click', previewEmail);
    sendBtn.addEventListener('click', sendEmail);
    
    closePreview.addEventListener('click', () => {
        previewSection.classList.remove('active');
        composeContainer.classList.remove('with-preview');
    });
}

async function previewEmail() {
    const data = getComposeData();
    
    if (!validateComposeData(data)) return;
    
    const previewSection = document.getElementById('preview-section');
    const composeContainer = document.querySelector('.compose-container');
    const previewLoading = document.getElementById('preview-loading');
    const previewContent = document.getElementById('preview-content');
    
    // Show preview section
    previewSection.classList.add('active');
    composeContainer.classList.add('with-preview');
    previewLoading.style.display = 'flex';
    previewContent.style.display = 'none';
    
    try {
        const response = await fetch(`${API_BASE}/api/preview-email`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            document.getElementById('preview-subject-text').textContent = result.subject;
            document.getElementById('preview-body-text').textContent = result.body;
            previewLoading.style.display = 'none';
            previewContent.style.display = 'block';
        } else {
            showToast('error', 'Lỗi', result.error || 'Không thể tạo email');
            previewSection.classList.remove('active');
            composeContainer.classList.remove('with-preview');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
        previewSection.classList.remove('active');
        composeContainer.classList.remove('with-preview');
    }
}

async function sendEmail() {
    const data = getComposeData();
    
    if (!validateComposeData(data)) return;
    
    const sendBtn = document.getElementById('send-btn');
    sendBtn.disabled = true;
    sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang gửi...';
    
    try {
        const response = await fetch(`${API_BASE}/api/send-email`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showToast('success', 'Thành công!', 'Email đã được gửi đi');
            clearComposeForm();
            loadEmails();
            
            // Close preview
            const previewSection = document.getElementById('preview-section');
            const composeContainer = document.querySelector('.compose-container');
            previewSection.classList.remove('active');
            composeContainer.classList.remove('with-preview');
        } else {
            showToast('error', 'Lỗi', result.error || 'Không thể gửi email');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Gửi Email';
    }
}

function getComposeData() {
    return {
        sender_name: document.getElementById('sender-name').value.trim(),
        notification_email: document.getElementById('notification-email').value.trim(),
        recipient_name: document.getElementById('recipient-name').value.trim(),
        recipient_email: document.getElementById('recipient-email').value.trim(),
        purpose: document.getElementById('email-purpose').value.trim(),
        tone: document.querySelector('input[name="tone"]:checked').value,
        additional_context: document.getElementById('additional-context').value.trim()
    };
}

function validateComposeData(data) {
    if (!data.sender_name) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập tên của bạn');
        return false;
    }
    if (!data.recipient_name) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập tên người nhận');
        return false;
    }
    if (!data.recipient_email) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập email người nhận');
        return false;
    }
    if (!isValidEmail(data.recipient_email)) {
        showToast('error', 'Email không hợp lệ', 'Vui lòng nhập email hợp lệ');
        return false;
    }
    if (!data.purpose) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập mục đích email');
        return false;
    }
    return true;
}

function isValidEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function clearComposeForm() {
    document.getElementById('sender-name').value = '';
    document.getElementById('notification-email').value = '';
    document.getElementById('recipient-name').value = '';
    document.getElementById('recipient-email').value = '';
    document.getElementById('email-purpose').value = '';
    document.getElementById('additional-context').value = '';
    document.querySelector('input[name="tone"][value="professional"]').checked = true;
}

// ==================== Inbox Page ====================

function initInbox() {
    const searchInput = document.getElementById('search-emails');
    const filterBtns = document.querySelectorAll('.btn-filter');
    
    searchInput.addEventListener('input', filterEmails);
    
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            filterEmails();
        });
    });
    
    document.getElementById('refresh-btn').addEventListener('click', loadEmails);
}

async function loadEmails() {
    try {
        const response = await fetch(`${API_BASE}/api/emails`);
        const result = await response.json();
        
        if (result.success) {
            emails = result.emails;
            renderEmails();
            updatePendingCount();
        }
    } catch (error) {
        console.error('Failed to load emails:', error);
    }
}

function renderEmails() {
    const emailList = document.getElementById('email-list');
    const emptyState = document.getElementById('empty-state');
    const searchTerm = document.getElementById('search-emails').value.toLowerCase();
    const filter = document.querySelector('.btn-filter.active').dataset.filter;
    
    // Filter emails
    let filteredEmails = emails.filter(email => {
        const matchesSearch = 
            email.recipient_name.toLowerCase().includes(searchTerm) ||
            email.recipient_email.toLowerCase().includes(searchTerm) ||
            email.subject.toLowerCase().includes(searchTerm) ||
            email.purpose.toLowerCase().includes(searchTerm);
        
        const matchesFilter = 
            filter === 'all' ||
            (filter === 'pending' && !email.response_received) ||
            (filter === 'responded' && email.response_received);
        
        return matchesSearch && matchesFilter;
    });
    
    // Clear list (except empty state)
    const items = emailList.querySelectorAll('.email-item');
    items.forEach(item => item.remove());
    
    if (filteredEmails.length === 0) {
        emptyState.style.display = 'block';
        return;
    }
    
    emptyState.style.display = 'none';
    
    // Render emails
    filteredEmails.forEach(email => {
        const item = createEmailItem(email);
        emailList.insertBefore(item, emptyState);
    });
}

function createEmailItem(email) {
    const item = document.createElement('div');
    item.className = 'email-item';
    item.onclick = () => showEmailDetail(email);
    
    const initials = email.recipient_name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
    const date = new Date(email.sent_at).toLocaleDateString('vi-VN');
    
    let statusBadge = '';
    if (email.response_received) {
        const analysis = email.analysis;
        const decision = analysis?.decision || 'responded';
        const decisionText = {
            'agreed': 'Đồng ý',
            'disagreed': 'Không đồng ý',
            'undecided': 'Chưa quyết định',
            'needs_more_info': 'Cần thêm thông tin'
        }[decision] || 'Đã phản hồi';
        
        statusBadge = `<span class="status-badge ${decision}">${decisionText}</span>`;
    } else {
        statusBadge = '<span class="status-badge pending"><i class="fas fa-clock"></i> Chờ phản hồi</span>';
    }
    
    item.innerHTML = `
        <div class="email-avatar">${initials}</div>
        <div class="email-content">
            <div class="email-header">
                <span class="email-recipient">${email.recipient_name}</span>
                <span class="email-date">${date}</span>
            </div>
            <div class="email-subject">${email.subject}</div>
            <div class="email-purpose">${email.purpose}</div>
        </div>
        <div class="email-status">${statusBadge}</div>
    `;
    
    return item;
}

function filterEmails() {
    renderEmails();
}

function updatePendingCount() {
    const pendingCount = emails.filter(e => !e.response_received).length;
    document.getElementById('pending-count').textContent = pendingCount;
}

// ==================== Monitor Page ====================

function initMonitor() {
    document.getElementById('start-monitor-btn').addEventListener('click', startMonitor);
    document.getElementById('stop-monitor-btn').addEventListener('click', stopMonitor);
    document.getElementById('check-once-btn').addEventListener('click', checkResponsesOnce);
    document.getElementById('check-imap-btn').addEventListener('click', checkImapConnection);
}

async function checkImapConnection() {
    const btn = document.getElementById('check-imap-btn');
    const statusDiv = document.getElementById('imap-status');
    
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang kiểm tra...';
    
    statusDiv.innerHTML = `
        <div class="imap-status-icon pending">
            <i class="fas fa-spinner fa-spin"></i>
        </div>
        <div class="imap-status-text">
            <h4>Đang kiểm tra...</h4>
            <p>Vui lòng chờ trong giây lát</p>
        </div>
    `;
    
    try {
        const response = await fetch(`${API_BASE}/api/check-imap`);
        const result = await response.json();
        
        if (result.success) {
            statusDiv.innerHTML = `
                <div class="imap-status-icon success">
                    <i class="fas fa-check-circle"></i>
                </div>
                <div class="imap-status-text">
                    <h4 style="color: #10b981;">Kết nối thành công!</h4>
                    <p>${result.details}</p>
                </div>
            `;
            addActivityLog('success', 'IMAP OK', 'Kết nối IMAP hoạt động bình thường');
        } else {
            statusDiv.innerHTML = `
                <div class="imap-status-icon error">
                    <i class="fas fa-times-circle"></i>
                </div>
                <div class="imap-status-text">
                    <h4 style="color: #ef4444;">${result.message}</h4>
                    <p>${result.details}</p>
                </div>
            `;
            addActivityLog('warning', 'IMAP Error', result.details);
        }
    } catch (error) {
        statusDiv.innerHTML = `
            <div class="imap-status-icon error">
                <i class="fas fa-times-circle"></i>
            </div>
            <div class="imap-status-text">
                <h4 style="color: #ef4444;">Lỗi kết nối</h4>
                <p>Không thể kết nối đến server</p>
            </div>
        `;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-sync-alt"></i> Kiểm tra';
    }
}

async function checkMonitorStatus() {
    try {
        const response = await fetch(`${API_BASE}/api/monitor/status`);
        const result = await response.json();
        
        if (result.success) {
            updateMonitorUI(result.running);
        }
    } catch (error) {
        console.error('Failed to check monitor status:', error);
    }
}

async function startMonitor() {
    const btn = document.getElementById('start-monitor-btn');
    btn.disabled = true;
    
    try {
        const response = await fetch(`${API_BASE}/api/monitor/start`, { method: 'POST' });
        const result = await response.json();
        
        if (result.success) {
            updateMonitorUI(true);
            showToast('success', 'Đã bắt đầu', 'Hệ thống giám sát đang hoạt động');
            addActivityLog('success', 'Bắt đầu giám sát', 'Hệ thống đang theo dõi phản hồi email');
        } else {
            showToast('error', 'Lỗi', result.message || result.error);
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
    }
}

async function stopMonitor() {
    const btn = document.getElementById('stop-monitor-btn');
    btn.disabled = true;
    
    try {
        const response = await fetch(`${API_BASE}/api/monitor/stop`, { method: 'POST' });
        const result = await response.json();
        
        if (result.success) {
            updateMonitorUI(false);
            showToast('info', 'Đã dừng', 'Hệ thống giám sát đã dừng');
            addActivityLog('warning', 'Dừng giám sát', 'Hệ thống đã ngừng theo dõi');
        } else {
            showToast('error', 'Lỗi', result.error);
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
    }
}

async function checkResponsesOnce() {
    const btn = document.getElementById('check-once-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang kiểm tra...';
    
    try {
        const response = await fetch(`${API_BASE}/api/check-responses`, { method: 'POST' });
        const result = await response.json();
        
        if (result.success) {
            showToast('success', 'Hoàn tất', 'Đã kiểm tra phản hồi');
            addActivityLog('info', 'Kiểm tra thủ công', 'Đã quét hộp thư để tìm phản hồi');
            loadEmails();
        } else {
            showToast('error', 'Lỗi', result.error);
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-sync"></i> Kiểm tra ngay';
    }
}

function updateMonitorUI(running) {
    monitorRunning = running;
    
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');
    const statusIcon = document.querySelector('.status-icon');
    const statusTextLarge = document.getElementById('status-text-large');
    const startBtn = document.getElementById('start-monitor-btn');
    const stopBtn = document.getElementById('stop-monitor-btn');
    
    if (running) {
        statusDot.classList.add('running');
        statusText.textContent = 'Đang chạy';
        statusIcon.className = 'status-icon running';
        statusIcon.innerHTML = '<i class="fas fa-play-circle"></i>';
        statusTextLarge.textContent = 'Đang chạy';
        startBtn.style.display = 'none';
        stopBtn.style.display = 'inline-flex';
    } else {
        statusDot.classList.remove('running');
        statusText.textContent = 'Đang dừng';
        statusIcon.className = 'status-icon stopped';
        statusIcon.innerHTML = '<i class="fas fa-stop-circle"></i>';
        statusTextLarge.textContent = 'Đã dừng';
        startBtn.style.display = 'inline-flex';
        stopBtn.style.display = 'none';
    }
}

function addActivityLog(type, title, message) {
    const log = document.getElementById('activity-log');
    const empty = log.querySelector('.log-empty');
    if (empty) empty.remove();
    
    const iconMap = {
        success: 'fa-check',
        info: 'fa-info',
        warning: 'fa-exclamation'
    };
    
    const item = document.createElement('div');
    item.className = 'log-item';
    item.innerHTML = `
        <div class="log-icon ${type}">
            <i class="fas ${iconMap[type]}"></i>
        </div>
        <div class="log-content">
            <h4>${title}</h4>
            <p>${message}</p>
        </div>
        <span class="log-time">${new Date().toLocaleTimeString('vi-VN')}</span>
    `;
    
    log.insertBefore(item, log.firstChild);
}

// ==================== Modals ====================

function initModals() {
    // Email detail modal
    const emailModal = document.getElementById('email-modal');
    const closeModal = document.getElementById('close-modal');
    const modalOverlay = emailModal.querySelector('.modal-overlay');
    
    closeModal.addEventListener('click', () => emailModal.classList.remove('active'));
    modalOverlay.addEventListener('click', () => emailModal.classList.remove('active'));
    
    // Response modal
    const responseModal = document.getElementById('response-modal');
    const closeResponseBtns = responseModal.querySelectorAll('.close-response-modal');
    const responseOverlay = responseModal.querySelector('.modal-overlay');
    
    closeResponseBtns.forEach(btn => {
        btn.addEventListener('click', () => responseModal.classList.remove('active'));
    });
    responseOverlay.addEventListener('click', () => responseModal.classList.remove('active'));
    
    // Manual response button
    document.getElementById('manual-response-btn').addEventListener('click', () => {
        emailModal.classList.remove('active');
        responseModal.classList.add('active');
    });
    
    // Analyze response
    document.getElementById('analyze-response-btn').addEventListener('click', analyzeManualResponse);
}

function showEmailDetail(email) {
    currentEmailId = email.id;
    const modal = document.getElementById('email-modal');
    const modalBody = document.getElementById('modal-body');
    
    let analysisHtml = '';
    if (email.analysis) {
        const a = email.analysis;
        const sentimentClass = a.sentiment === 'positive' ? 'positive' : 
                              a.sentiment === 'negative' ? 'negative' : 'neutral';
        
        analysisHtml = `
            <div class="email-detail-section">
                <h4>Phân tích phản hồi</h4>
                <div class="analysis-result">
                    <div class="analysis-grid">
                        <div class="analysis-item">
                            <label>Cảm xúc</label>
                            <span class="${sentimentClass}">${a.sentiment || 'N/A'}</span>
                        </div>
                        <div class="analysis-item">
                            <label>Quyết định</label>
                            <span>${a.decision || 'N/A'}</span>
                        </div>
                        <div class="analysis-item">
                            <label>Độ tin cậy</label>
                            <span>${a.confidence_score ? Math.round(a.confidence_score * 100) + '%' : 'N/A'}</span>
                        </div>
                    </div>
                    <div class="analysis-summary">
                        <h5>Tóm tắt</h5>
                        <p>${a.summary || 'Không có tóm tắt'}</p>
                    </div>
                </div>
            </div>
        `;
    }
    
    modalBody.innerHTML = `
        <div class="email-detail-section">
            <h4>Người nhận</h4>
            <p><strong>${email.recipient_name}</strong> (${email.recipient_email})</p>
        </div>
        <div class="email-detail-section">
            <h4>Mục đích</h4>
            <p>${email.purpose}</p>
        </div>
        <div class="email-detail-section">
            <h4>Tiêu đề</h4>
            <p>${email.subject}</p>
        </div>
        <div class="email-detail-section">
            <h4>Nội dung</h4>
            <div class="body-content">${email.body}</div>
        </div>
        <div class="email-detail-section">
            <h4>Trạng thái</h4>
            <p>${email.response_received ? 
                '<span class="status-badge responded"><i class="fas fa-check"></i> Đã nhận phản hồi</span>' : 
                '<span class="status-badge pending"><i class="fas fa-clock"></i> Chờ phản hồi</span>'
            }</p>
        </div>
        ${analysisHtml}
    `;
    
    // Show/hide manual response button
    const manualBtn = document.getElementById('manual-response-btn');
    manualBtn.style.display = email.response_received ? 'none' : 'inline-flex';
    
    modal.classList.add('active');
}

async function analyzeManualResponse() {
    const responseSubject = document.getElementById('response-subject').value.trim();
    const responseText = document.getElementById('response-text').value.trim();
    
    if (!responseText) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập nội dung phản hồi');
        return;
    }
    
    const btn = document.getElementById('analyze-response-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang phân tích...';
    
    try {
        const response = await fetch(`${API_BASE}/api/analyze-response`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                email_id: currentEmailId,
                response_subject: responseSubject || 'Re: Response',
                response_text: responseText
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            showToast('success', 'Phân tích hoàn tất', 
                `Quyết định: ${result.analysis.decision}, Cảm xúc: ${result.analysis.sentiment}`);
            
            document.getElementById('response-modal').classList.remove('active');
            document.getElementById('response-subject').value = '';
            document.getElementById('response-text').value = '';
            
            loadEmails();
            
            addActivityLog('success', 'Phân tích phản hồi', 
                `Đã phân tích phản hồi - ${result.analysis.decision}`);
        } else {
            showToast('error', 'Lỗi', result.error);
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-brain"></i> Phân tích';
    }
}

// ==================== WebSocket Realtime ====================

function initWebSocket() {
    // Load Socket.IO client library dynamically
    const script = document.createElement('script');
    script.src = 'https://cdn.socket.io/4.7.2/socket.io.min.js';
    script.onload = () => {
        connectWebSocket();
    };
    document.head.appendChild(script);
}

function connectWebSocket() {
    try {
        socket = io(window.location.origin, {
            transports: ['websocket', 'polling'],
            reconnection: true,
            reconnectionAttempts: 10,
            reconnectionDelay: 1000
        });
        
        socket.on('connect', () => {
            wsConnected = true;
            console.log('🔌 WebSocket connected');
            updateConnectionStatus(true);
            addActivityLog('success', 'Realtime kết nối', 'Kết nối WebSocket thành công');
        });
        
        socket.on('disconnect', () => {
            wsConnected = false;
            console.log('🔌 WebSocket disconnected');
            updateConnectionStatus(false);
        });
        
        socket.on('connected', (data) => {
            console.log('Server confirmed connection:', data);
        });
        
        // Realtime response received
        socket.on('response_received', (data) => {
            console.log('📩 Realtime response received:', data);
            handleResponseReceived(data);
        });
        
        // CV evaluation result
        socket.on('cv_evaluated', (data) => {
            console.log('📋 CV evaluation received:', data);
            handleCvEvaluated(data);
        });
        
        // Check response complete
        socket.on('check_complete', (data) => {
            if (data.success) {
                addActivityLog('info', 'Kiểm tra hoàn tất', 'Đã quét hộp thư');
            }
        });
        
        socket.on('connect_error', (error) => {
            console.log('WebSocket connection error, falling back to SSE:', error);
            // Fallback to SSE if WebSocket fails
            initEventSource();
        });
        
    } catch (error) {
        console.error('WebSocket initialization failed:', error);
        // Fallback to SSE
        initEventSource();
    }
}

function updateConnectionStatus(connected) {
    const statusElement = document.getElementById('ws-status');
    if (statusElement) {
        statusElement.className = `ws-status ${connected ? 'connected' : 'disconnected'}`;
        statusElement.innerHTML = connected 
            ? '<i class="fas fa-wifi"></i> Realtime' 
            : '<i class="fas fa-wifi"></i> Offline';
    }
}

function checkResponsesRealtime() {
    if (socket && wsConnected) {
        socket.emit('check_responses_now');
        addActivityLog('info', 'Kiểm tra realtime', 'Đang quét hộp thư...');
    } else {
        // Fallback to HTTP
        checkResponsesOnce();
    }
}

function handleCvEvaluated(data) {
    showToast('info', 'CV đã đánh giá', 
        `${data.candidate_name}: ${data.overall_score}% - ${data.is_qualified ? 'Đạt' : 'Chưa đạt'}`);
    
    if (data.email_sent) {
        addActivityLog('success', 'Gửi thư mời tự động', 
            `Đã gửi thư mời phỏng vấn đến ${data.candidate_name}`);
    }
    
    loadCvEvaluations();
}

// ==================== Server-Sent Events (Fallback) ====================

function initEventSource() {
    if (wsConnected) return; // Skip if WebSocket is working
    
    try {
        const eventSource = new EventSource(`${API_BASE}/api/events`);
        
        eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            
            if (data.type === 'response_received') {
                handleResponseReceived(data);
            }
        };
        
        eventSource.onerror = () => {
            console.log('SSE connection lost, reconnecting...');
        };
    } catch (error) {
        console.error('SSE not supported:', error);
    }
}

function handleResponseReceived(data) {
    showToast('success', 'Phản hồi mới!', 
        `${data.recipient_name} đã phản hồi - ${data.analysis.decision}`);
    
    addActivityLog('success', 'Nhận phản hồi', 
        `${data.recipient_name} đã phản hồi email của bạn`);
    
    // Update notification badge
    const badge = document.getElementById('notification-badge');
    const count = parseInt(badge.textContent || '0') + 1;
    badge.textContent = count;
    badge.style.display = 'flex';
    
    loadEmails();
}

// ==================== Toast Notifications ====================

function showToast(type, title, message) {
    const container = document.getElementById('toast-container');
    
    const iconMap = {
        success: 'fa-check-circle',
        error: 'fa-exclamation-circle',
        info: 'fa-info-circle'
    };
    
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <i class="fas ${iconMap[type]}"></i>
        <div class="toast-content">
            <h4>${title}</h4>
            <p>${message}</p>
        </div>
        <button class="toast-close" onclick="this.parentElement.remove()">
            <i class="fas fa-times"></i>
        </button>
    `;
    
    container.appendChild(toast);
    
    // Auto remove after 5 seconds
    setTimeout(() => {
        if (toast.parentElement) {
            toast.remove();
        }
    }, 5000);
}

// Global function for navigation
window.navigateTo = navigateTo;

// ==================== CV Evaluation ====================

// CV file state
let uploadedCvFile = null;
let uploadedCvContent = '';

function initCvEvaluation() {
    // Evaluate button
    document.getElementById('evaluate-cv-btn').addEventListener('click', evaluateCv);
    
    // Clear form button
    document.getElementById('clear-cv-btn').addEventListener('click', clearCvForm);
    
    // Refresh button
    document.getElementById('refresh-cv-btn').addEventListener('click', loadCvEvaluations);
    
    // CV Upload handlers
    initCvUpload();
    
    // CV Modal
    const cvModal = document.getElementById('cv-modal');
    const closeCvModal = document.getElementById('close-cv-modal');
    const cvModalOverlay = cvModal.querySelector('.modal-overlay');
    
    closeCvModal.addEventListener('click', () => cvModal.classList.remove('active'));
    cvModalOverlay.addEventListener('click', () => cvModal.classList.remove('active'));
    
    // CV Email Preview Modal
    const cvEmailModal = document.getElementById('cv-email-preview-modal');
    const closeCvPreviewBtns = cvEmailModal.querySelectorAll('.close-cv-preview');
    const cvEmailOverlay = cvEmailModal.querySelector('.modal-overlay');
    
    closeCvPreviewBtns.forEach(btn => {
        btn.addEventListener('click', () => cvEmailModal.classList.remove('active'));
    });
    cvEmailOverlay.addEventListener('click', () => cvEmailModal.classList.remove('active'));
    
    // Confirm send email button
    document.getElementById('confirm-send-cv-email').addEventListener('click', sendCvEmail);
}

// ==================== CV File Upload ====================

function initCvUpload() {
    const uploadArea = document.getElementById('cv-upload-area');
    const fileInput = document.getElementById('cv-file-input');
    const removeBtn = document.getElementById('remove-file-btn');
    
    // Click to upload
    uploadArea.addEventListener('click', (e) => {
        if (e.target.id !== 'remove-file-btn' && !e.target.closest('#remove-file-btn')) {
            fileInput.click();
        }
    });
    
    // File selected
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleCvFile(e.target.files[0]);
        }
    });
    
    // Drag and drop
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('drag-over');
    });
    
    uploadArea.addEventListener('dragleave', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
    });
    
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
        
        if (e.dataTransfer.files.length > 0) {
            handleCvFile(e.dataTransfer.files[0]);
        }
    });
    
    // Remove file
    removeBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        removeCvFile();
    });
}

function handleCvFile(file) {
    // Validate file type
    const allowedTypes = ['application/pdf', 'application/msword', 
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain'];
    const allowedExtensions = ['.pdf', '.doc', '.docx', '.txt'];
    
    const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
    
    if (!allowedExtensions.includes(fileExtension)) {
        showToast('error', 'File không hợp lệ', 'Chỉ hỗ trợ file PDF, DOC, DOCX, TXT');
        return;
    }
    
    // Validate file size (5MB max)
    if (file.size > 5 * 1024 * 1024) {
        showToast('error', 'File quá lớn', 'File không được vượt quá 5MB');
        return;
    }
    
    uploadedCvFile = file;
    
    // Show progress
    showUploadProgress();
    
    // Upload and extract text
    uploadCvFile(file);
}

function showUploadProgress() {
    document.getElementById('upload-placeholder').style.display = 'none';
    document.getElementById('upload-progress').style.display = 'block';
    document.getElementById('upload-success').style.display = 'none';
    
    // Animate progress bar
    let progress = 0;
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');
    
    const interval = setInterval(() => {
        progress += Math.random() * 30;
        if (progress > 90) progress = 90;
        progressFill.style.width = progress + '%';
        progressText.textContent = `Đang xử lý... ${Math.round(progress)}%`;
    }, 200);
    
    // Store interval ID to clear later
    document.getElementById('upload-progress').dataset.interval = interval;
}

async function uploadCvFile(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch(`${API_BASE}/api/cv/upload`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        // Clear progress interval
        clearInterval(document.getElementById('upload-progress').dataset.interval);
        
        if (result.success) {
            uploadedCvContent = result.content;
            showUploadSuccess(file.name);
            
            // Auto-fill CV content textarea
            document.getElementById('cv-content').value = result.content;
            
            showToast('success', 'Upload thành công', `Đã trích xuất nội dung từ ${file.name}`);
        } else {
            showUploadError();
            showToast('error', 'Lỗi xử lý file', result.error || 'Không thể đọc nội dung file');
        }
    } catch (error) {
        clearInterval(document.getElementById('upload-progress').dataset.interval);
        showUploadError();
        showToast('error', 'Lỗi kết nối', 'Không thể upload file');
    }
}

function showUploadSuccess(fileName) {
    document.getElementById('upload-placeholder').style.display = 'none';
    document.getElementById('upload-progress').style.display = 'none';
    document.getElementById('upload-success').style.display = 'flex';
    document.getElementById('uploaded-file-name').textContent = fileName;
    document.getElementById('progress-fill').style.width = '100%';
}

function showUploadError() {
    document.getElementById('upload-placeholder').style.display = 'block';
    document.getElementById('upload-progress').style.display = 'none';
    document.getElementById('upload-success').style.display = 'none';
    uploadedCvFile = null;
    uploadedCvContent = '';
}

function removeCvFile() {
    uploadedCvFile = null;
    uploadedCvContent = '';
    document.getElementById('cv-file-input').value = '';
    document.getElementById('cv-content').value = '';
    
    document.getElementById('upload-placeholder').style.display = 'block';
    document.getElementById('upload-progress').style.display = 'none';
    document.getElementById('upload-success').style.display = 'none';
    
    showToast('info', 'Đã xóa file', 'Bạn có thể upload file mới hoặc dán nội dung CV');
}

function getCvFormData() {
    return {
        candidate_name: document.getElementById('cv-candidate-name').value.trim(),
        candidate_email: document.getElementById('cv-candidate-email').value.trim(),
        job_title: document.getElementById('cv-job-title').value.trim(),
        company_name: document.getElementById('cv-company-name').value.trim(),
        job_requirements: document.getElementById('cv-job-requirements').value.trim(),
        cv_content: document.getElementById('cv-content').value.trim()
    };
}

function validateCvFormData(data) {
    if (!data.candidate_name) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập tên ứng viên');
        return false;
    }
    if (!data.candidate_email) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập email ứng viên');
        return false;
    }
    if (!isValidEmail(data.candidate_email)) {
        showToast('error', 'Email không hợp lệ', 'Vui lòng nhập email hợp lệ');
        return false;
    }
    if (!data.job_title) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập vị trí tuyển dụng');
        return false;
    }
    if (!data.job_requirements) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập yêu cầu công việc');
        return false;
    }
    if (!data.cv_content) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập nội dung CV');
        return false;
    }
    return true;
}

function clearCvForm() {
    document.getElementById('cv-candidate-name').value = '';
    document.getElementById('cv-candidate-email').value = '';
    document.getElementById('cv-job-title').value = '';
    document.getElementById('cv-company-name').value = '';
    document.getElementById('cv-job-requirements').value = '';
    document.getElementById('cv-content').value = '';
    
    // Reset upload area
    removeCvFile();
}

async function evaluateCv() {
    const data = getCvFormData();
    
    if (!validateCvFormData(data)) return;
    
    const btn = document.getElementById('evaluate-cv-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang đánh giá...';
    
    try {
        const response = await fetch(`${API_BASE}/api/cv/evaluate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            const evalData = result.evaluation;
            showToast('success', 'Đánh giá hoàn tất!', 
                `Điểm: ${evalData.overall_score}% - ${evalData.is_qualified ? 'ĐẠT YÊU CẦU' : 'CHƯA ĐẠT'}`);
            
            // Show result modal
            showCvDetailModal(evalData);
            
            // Reload list
            loadCvEvaluations();
            
            // Clear form if qualified and email sent
            if (evalData.is_qualified && evalData.email_sent) {
                clearCvForm();
                showToast('info', 'Email đã gửi', 'Thư mời phỏng vấn đã được gửi tự động đến ứng viên');
            }
        } else {
            showToast('error', 'Lỗi', result.error || 'Không thể đánh giá CV');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-brain"></i> Đánh giá CV';
    }
}

async function loadCvEvaluations() {
    try {
        const response = await fetch(`${API_BASE}/api/cv/list`);
        const result = await response.json();
        
        if (result.success) {
            cvEvaluations = result.evaluations;
            renderCvEvaluations();
            updateCvStats();
        }
    } catch (error) {
        console.error('Failed to load CV evaluations:', error);
    }
}

function renderCvEvaluations() {
    const cvList = document.getElementById('cv-list');
    const emptyState = document.getElementById('cv-empty-state');
    
    // Clear list (except empty state)
    const items = cvList.querySelectorAll('.cv-item');
    items.forEach(item => item.remove());
    
    if (cvEvaluations.length === 0) {
        emptyState.style.display = 'block';
        return;
    }
    
    emptyState.style.display = 'none';
    
    // Render CV evaluations
    cvEvaluations.forEach(cv => {
        const item = createCvItem(cv);
        cvList.insertBefore(item, emptyState);
    });
}

function createCvItem(cv) {
    const item = document.createElement('div');
    item.className = `cv-item ${cv.is_qualified ? 'qualified' : 'not-qualified'}`;
    item.onclick = () => showCvDetailModal(cv);
    
    const scoreClass = cv.overall_score >= 85 ? 'high' : (cv.overall_score >= 60 ? 'medium' : 'low');
    
    item.innerHTML = `
        <div class="cv-item-info">
            <div class="cv-item-name">${cv.candidate_name}</div>
            <div class="cv-item-job">${cv.job_title}</div>
        </div>
        <div class="cv-item-score ${scoreClass}">
            <span class="score-value">${cv.overall_score}%</span>
            <span class="score-label">${cv.is_qualified ? 'Đạt' : 'Chưa đạt'}</span>
        </div>
        <div class="cv-item-status ${cv.email_sent ? 'sent' : 'not-sent'}">
            <i class="fas ${cv.email_sent ? 'fa-envelope-circle-check' : 'fa-envelope'}"></i>
        </div>
    `;
    
    return item;
}

function updateCvStats() {
    const total = cvEvaluations.length;
    const qualified = cvEvaluations.filter(cv => cv.is_qualified).length;
    const emailed = cvEvaluations.filter(cv => cv.email_sent).length;
    
    document.getElementById('total-cv-count').textContent = total;
    document.getElementById('qualified-cv-count').textContent = qualified;
    document.getElementById('emailed-cv-count').textContent = emailed;
    document.getElementById('qualified-count').textContent = qualified;
}

function showCvDetailModal(cv) {
    currentCvId = cv.id;
    const modal = document.getElementById('cv-modal');
    const modalBody = document.getElementById('cv-modal-body');
    const modalFooter = document.getElementById('cv-modal-footer');
    
    // Parse evaluation result
    let evalResult = cv.evaluation_result;
    if (typeof evalResult === 'string') {
        try {
            evalResult = JSON.parse(evalResult);
        } catch (e) {
            evalResult = {};
        }
    }
    
    // Build strengths list
    let strengthsHtml = '';
    if (evalResult.strengths && evalResult.strengths.length > 0) {
        strengthsHtml = evalResult.strengths.map(s => `<li>${s}</li>`).join('');
    } else {
        strengthsHtml = '<li>Không có thông tin</li>';
    }
    
    // Build weaknesses list
    let weaknessesHtml = '';
    if (evalResult.weaknesses && evalResult.weaknesses.length > 0) {
        weaknessesHtml = evalResult.weaknesses.map(w => `<li>${w}</li>`).join('');
    } else {
        weaknessesHtml = '<li>Không có thông tin</li>';
    }
    
    modalBody.innerHTML = `
        <div class="cv-score-display">
            <div class="cv-score-circle ${cv.is_qualified ? 'qualified' : 'not-qualified'}">
                <span class="score-number">${cv.overall_score}</span>
                <span class="score-percent">%</span>
            </div>
            <div class="cv-score-info">
                <h3>${cv.is_qualified ? '✅ ĐẠT YÊU CẦU' : '❌ CHƯA ĐẠT YÊU CẦU'}</h3>
                <p>${evalResult.summary || 'Không có tóm tắt'}</p>
            </div>
        </div>
        
        <div class="cv-detail-section">
            <h4>Thông tin ứng viên</h4>
            <div class="cv-evaluation-details">
                <div class="evaluation-item">
                    <label>Họ và tên</label>
                    <span>${cv.candidate_name}</span>
                </div>
                <div class="evaluation-item">
                    <label>Email</label>
                    <span>${cv.candidate_email}</span>
                </div>
                <div class="evaluation-item">
                    <label>Vị trí ứng tuyển</label>
                    <span>${cv.job_title}</span>
                </div>
                <div class="evaluation-item">
                    <label>Công ty</label>
                    <span>${cv.company_name || 'Không xác định'}</span>
                </div>
            </div>
        </div>
        
        <div class="cv-detail-section">
            <h4>Chi tiết đánh giá</h4>
            <div class="cv-evaluation-details">
                <div class="evaluation-item">
                    <label>Kỹ năng kỹ thuật</label>
                    <span>${evalResult.technical_skills || 0}/30</span>
                </div>
                <div class="evaluation-item">
                    <label>Kinh nghiệm</label>
                    <span>${evalResult.experience || 0}/25</span>
                </div>
                <div class="evaluation-item">
                    <label>Học vấn</label>
                    <span>${evalResult.education || 0}/20</span>
                </div>
                <div class="evaluation-item">
                    <label>Kỹ năng mềm</label>
                    <span>${evalResult.soft_skills || 0}/15</span>
                </div>
                <div class="evaluation-item">
                    <label>Độ phù hợp</label>
                    <span>${evalResult.overall_fit || 0}/10</span>
                </div>
                <div class="evaluation-item">
                    <label>Đề xuất</label>
                    <span>${evalResult.recommendation || 'Không có'}</span>
                </div>
            </div>
        </div>
        
        <div class="cv-strengths-weaknesses">
            <div class="strengths-box">
                <h5><i class="fas fa-plus-circle"></i> Điểm mạnh</h5>
                <ul>${strengthsHtml}</ul>
            </div>
            <div class="weaknesses-box">
                <h5><i class="fas fa-minus-circle"></i> Điểm yếu</h5>
                <ul>${weaknessesHtml}</ul>
            </div>
        </div>
        
        <div class="cv-status-badges">
            <span class="cv-status-badge ${cv.is_qualified ? 'qualified' : 'not-qualified'}">
                <i class="fas ${cv.is_qualified ? 'fa-check' : 'fa-times'}"></i>
                ${cv.is_qualified ? 'Đạt yêu cầu (≥85%)' : 'Chưa đạt yêu cầu (<85%)'}
            </span>
            <span class="cv-status-badge ${cv.email_sent ? 'email-sent' : 'email-not-sent'}">
                <i class="fas ${cv.email_sent ? 'fa-envelope-circle-check' : 'fa-envelope'}"></i>
                ${cv.email_sent ? 'Đã gửi email' : 'Chưa gửi email'}
            </span>
        </div>
    `;
    
    // Footer buttons
    let footerHtml = '';
    if (!cv.email_sent && cv.is_qualified) {
        footerHtml = `
            <button class="btn btn-secondary" onclick="document.getElementById('cv-modal').classList.remove('active')">Đóng</button>
            <button class="btn btn-primary" onclick="previewCvEmail(${cv.id})">
                <i class="fas fa-envelope"></i> Gửi thư mời
            </button>
        `;
    } else if (cv.email_sent) {
        footerHtml = `
            <button class="btn btn-secondary" onclick="document.getElementById('cv-modal').classList.remove('active')">Đóng</button>
            <button class="btn btn-warning" onclick="allowResendEmail(${cv.id})">
                <i class="fas fa-redo"></i> Cho phép gửi lại
            </button>
        `;
    } else {
        footerHtml = `
            <button class="btn btn-secondary" onclick="document.getElementById('cv-modal').classList.remove('active')">Đóng</button>
        `;
    }
    
    modalFooter.innerHTML = footerHtml;
    modal.classList.add('active');
}

async function previewCvEmail(cvId) {
    currentCvId = cvId;
    const previewModal = document.getElementById('cv-email-preview-modal');
    const loading = document.getElementById('cv-email-loading');
    const content = document.getElementById('cv-email-content');
    
    // Close detail modal, show preview modal
    document.getElementById('cv-modal').classList.remove('active');
    previewModal.classList.add('active');
    loading.style.display = 'flex';
    content.style.display = 'none';
    
    try {
        const response = await fetch(`${API_BASE}/api/cv/preview-email`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cv_id: cvId })
        });
        
        const result = await response.json();
        
        if (result.success) {
            document.getElementById('cv-email-subject').textContent = result.subject;
            document.getElementById('cv-email-body').textContent = result.body;
            loading.style.display = 'none';
            content.style.display = 'block';
        } else {
            showToast('error', 'Lỗi', result.error || 'Không thể tạo email');
            previewModal.classList.remove('active');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
        previewModal.classList.remove('active');
    }
}

async function sendCvEmail() {
    const btn = document.getElementById('confirm-send-cv-email');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang gửi...';
    
    try {
        const response = await fetch(`${API_BASE}/api/cv/send-email/${currentCvId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const result = await response.json();
        
        if (result.success) {
            showToast('success', 'Thành công!', 'Email mời phỏng vấn đã được gửi');
            document.getElementById('cv-email-preview-modal').classList.remove('active');
            loadCvEvaluations();
        } else {
            showToast('error', 'Lỗi', result.error || 'Không thể gửi email');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane"></i> Gửi Email';
    }
}

async function allowResendEmail(cvId) {
    try {
        const response = await fetch(`${API_BASE}/api/cv/allow-resend/${cvId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const result = await response.json();
        
        if (result.success) {
            showToast('success', 'Thành công!', 'Đã cho phép gửi lại email');
            document.getElementById('cv-modal').classList.remove('active');
            loadCvEvaluations();
        } else {
            showToast('error', 'Lỗi', result.error || 'Không thể cập nhật');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    }
}

// Make functions globally available
window.previewCvEmail = previewCvEmail;
window.allowResendEmail = allowResendEmail;
