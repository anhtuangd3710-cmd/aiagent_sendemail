/**
 * Email AI Agent - Frontend JavaScript
 * Modern, responsive UI interactions with Authentication
 * Optimized for performance with caching, debouncing, and lazy loading
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
let currentUser = null;

// ==================== Performance Optimization ====================

// Cache configuration
const cache = {
    data: new Map(),
    timestamps: new Map(),
    ttl: {
        emails: 30000,        // 30 seconds for emails
        cvEvaluations: 60000, // 1 minute for CV evaluations
        userSettings: 120000, // 2 minutes for user settings
        dataStats: 60000,     // 1 minute for stats
        default: 30000
    },
    
    set(key, data, customTtl = null) {
        this.data.set(key, data);
        this.timestamps.set(key, Date.now());
        if (customTtl) {
            this.ttl[key] = customTtl;
        }
    },
    
    get(key) {
        const timestamp = this.timestamps.get(key);
        const ttl = this.ttl[key] || this.ttl.default;
        
        if (timestamp && (Date.now() - timestamp) < ttl) {
            return this.data.get(key);
        }
        
        // Expired, remove from cache
        this.data.delete(key);
        this.timestamps.delete(key);
        return null;
    },
    
    invalidate(key) {
        this.data.delete(key);
        this.timestamps.delete(key);
    },
    
    invalidateAll() {
        this.data.clear();
        this.timestamps.clear();
    }
};

// Debounce utility
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Throttle utility
function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Request deduplication
const pendingRequests = new Map();

async function deduplicatedFetch(url, options = {}) {
    const key = `${options.method || 'GET'}-${url}-${JSON.stringify(options.body || '')}`;
    
    // Check if there's already a pending request for this
    if (pendingRequests.has(key)) {
        return pendingRequests.get(key);
    }
    
    const promise = authFetch(url, options)
        .then(response => {
            pendingRequests.delete(key);
            return response;
        })
        .catch(error => {
            pendingRequests.delete(key);
            throw error;
        });
    
    pendingRequests.set(key, promise);
    return promise;
}

// DOM Elements
const pageTitle = document.getElementById('page-title');
const pageSubtitle = document.getElementById('page-subtitle');
const navItems = document.querySelectorAll('.nav-item');
const pages = document.querySelectorAll('.page');

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    // Check authentication first
    const isAuthenticated = await checkAuth();
    
    if (!isAuthenticated) {
        showLoginRequired();
        return;
    }
    
    initNavigation();
    initCompose();
    initInbox();
    initMonitor();
    initModals();
    initCvEvaluation();
    initProfile();
    initWebSocket();
    loadEmails();
    loadCvEvaluations();
    checkMonitorStatus();
    loadUserSettings();
});

// ==================== Authentication ====================

async function checkAuth() {
    const token = localStorage.getItem('auth_token');
    if (!token) {
        return false;
    }
    
    try {
        const response = await fetch(`${API_BASE}/api/auth/me`, {
            headers: {
                'Authorization': `Bearer ${token}`
            },
            credentials: 'include'
        });
        
        const data = await response.json();
        
        if (data.success && data.user) {
            currentUser = data.user;
            updateUserDisplay();
            return true;
        }
        
        // Token invalid, clear it
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user');
        return false;
    } catch (error) {
        console.error('Auth check failed:', error);
        return false;
    }
}

function updateUserDisplay() {
    if (currentUser) {
        const nameEl = document.getElementById('user-display-name');
        const emailEl = document.getElementById('user-display-email');
        
        if (nameEl) nameEl.textContent = currentUser.full_name || currentUser.username;
        if (emailEl) emailEl.textContent = currentUser.email;
        
        // Update profile form
        const profileUsername = document.getElementById('profile-username');
        const profileFullname = document.getElementById('profile-fullname');
        const profileEmail = document.getElementById('profile-email');
        
        if (profileUsername) profileUsername.value = currentUser.username;
        if (profileFullname) profileFullname.value = currentUser.full_name || '';
        if (profileEmail) profileEmail.value = currentUser.email;
    }
}

function showLoginRequired() {
    const overlay = document.createElement('div');
    overlay.className = 'login-required-overlay';
    overlay.innerHTML = `
        <div class="login-required-content">
            <i class="fas fa-lock"></i>
            <h2>Yêu cầu đăng nhập</h2>
            <p>Vui lòng đăng nhập để sử dụng Email AI Agent</p>
            <a href="/login" class="btn btn-primary">
                <i class="fas fa-sign-in-alt"></i> Đăng nhập
            </a>
        </div>
    `;
    document.body.appendChild(overlay);
}

async function logout() {
    const token = localStorage.getItem('auth_token');
    
    try {
        await fetch(`${API_BASE}/api/auth/logout`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            credentials: 'include'
        });
    } catch (error) {
        console.error('Logout error:', error);
    }
    
    localStorage.removeItem('auth_token');
    localStorage.removeItem('user');
    window.location.href = '/login';
}

// Add auth header to all fetch requests
function authFetch(url, options = {}) {
    const token = localStorage.getItem('auth_token');
    
    return fetch(url, {
        ...options,
        headers: {
            ...options.headers,
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
        },
        credentials: 'include'
    });
}

// ==================== Navigation ====================

function initNavigation() {
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            navigateTo(page);
            // Close mobile sidebar after navigation
            closeMobileSidebar();
        });
    });
    
    // Logout button
    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', logout);
    }
    
    // Initialize mobile menu
    initMobileMenu();
}

// ==================== Mobile Menu ====================

function initMobileMenu() {
    const menuToggle = document.getElementById('mobile-menu-toggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    
    if (menuToggle && sidebar && overlay) {
        // Toggle menu button
        menuToggle.addEventListener('click', () => {
            toggleMobileSidebar();
        });
        
        // Close on overlay click
        overlay.addEventListener('click', () => {
            closeMobileSidebar();
        });
        
        // Close on escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                closeMobileSidebar();
            }
        });
        
        // Close sidebar on window resize to desktop
        window.addEventListener('resize', () => {
            if (window.innerWidth > 768) {
                closeMobileSidebar();
            }
        });
    }
}

function toggleMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const menuToggle = document.getElementById('mobile-menu-toggle');
    
    if (sidebar && overlay) {
        const isOpen = sidebar.classList.contains('open');
        
        if (isOpen) {
            closeMobileSidebar();
        } else {
            sidebar.classList.add('open');
            overlay.classList.add('active');
            menuToggle.innerHTML = '<i class="fas fa-times"></i>';
            document.body.style.overflow = 'hidden';
        }
    }
}

function closeMobileSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    const menuToggle = document.getElementById('mobile-menu-toggle');
    
    if (sidebar && overlay) {
        sidebar.classList.remove('open');
        overlay.classList.remove('active');
        if (menuToggle) {
            menuToggle.innerHTML = '<i class="fas fa-bars"></i>';
        }
        document.body.style.overflow = '';
    }
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
        settings: { title: 'Cài đặt', subtitle: 'Cấu hình và hướng dẫn sử dụng' },
        profile: { title: 'Hồ sơ & API Keys', subtitle: 'Quản lý thông tin cá nhân và cấu hình API' }
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
    if (page === 'profile') {
        loadUserSettings();
        loadDataStats();
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
    
    // Nút gửi từ preview
    const sendFromPreviewBtn = document.getElementById('send-from-preview-btn');
    if (sendFromPreviewBtn) {
        sendFromPreviewBtn.addEventListener('click', sendEmailFromPreview);
    }
    
    // Nút tạo lại email trong preview
    const regenerateBtn = document.getElementById('regenerate-preview-btn');
    if (regenerateBtn) {
        regenerateBtn.addEventListener('click', () => {
            // Tạo lại email mới
            previewEmail();
        });
    }
    
    // Initialize file upload
    initFileUpload();
}

// File upload state
let selectedFiles = [];

function initFileUpload() {
    const fileInput = document.getElementById('email-attachments');
    const uploadArea = document.getElementById('file-upload-area');
    
    if (!fileInput || !uploadArea) return;
    
    // File input change
    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
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
        handleFiles(e.dataTransfer.files);
    });
}

function handleFiles(files) {
    const maxSize = 10 * 1024 * 1024; // 10MB
    const allowedTypes = [
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-powerpoint',
        'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        'text/plain',
        'text/csv',
        'image/jpeg',
        'image/png',
        'image/gif',
        'application/zip',
        'application/x-rar-compressed'
    ];
    
    for (let file of files) {
        // Check size
        if (file.size > maxSize) {
            showToast('warning', 'File quá lớn', `${file.name} vượt quá 10MB`);
            continue;
        }
        
        // Check if already added
        if (selectedFiles.some(f => f.name === file.name && f.size === file.size)) {
            continue;
        }
        
        selectedFiles.push(file);
    }
    
    renderAttachmentList();
}

function renderAttachmentList() {
    const list = document.getElementById('attachment-list');
    if (!list) return;
    
    if (selectedFiles.length === 0) {
        list.innerHTML = '';
        return;
    }
    
    list.innerHTML = selectedFiles.map((file, index) => `
        <div class="attachment-item">
            <div class="attachment-info">
                <i class="fas ${getFileIcon(file.type)}"></i>
                <span class="attachment-name">${file.name}</span>
                <span class="attachment-size">${formatFileSize(file.size)}</span>
            </div>
            <button type="button" class="btn-remove-attachment" onclick="removeAttachment(${index})">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `).join('');
}

function removeAttachment(index) {
    selectedFiles.splice(index, 1);
    renderAttachmentList();
}

function getFileIcon(mimeType) {
    if (mimeType.includes('pdf')) return 'fa-file-pdf';
    if (mimeType.includes('word') || mimeType.includes('document')) return 'fa-file-word';
    if (mimeType.includes('excel') || mimeType.includes('spreadsheet')) return 'fa-file-excel';
    if (mimeType.includes('powerpoint') || mimeType.includes('presentation')) return 'fa-file-powerpoint';
    if (mimeType.includes('image')) return 'fa-file-image';
    if (mimeType.includes('zip') || mimeType.includes('rar')) return 'fa-file-archive';
    if (mimeType.includes('text')) return 'fa-file-alt';
    return 'fa-file';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
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
        const response = await authFetch(`${API_BASE}/api/preview-email`, {
            method: 'POST',
            body: JSON.stringify(data)
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Sử dụng input/textarea để cho phép chỉnh sửa
            document.getElementById('preview-subject-input').value = result.subject;
            document.getElementById('preview-body-input').value = result.body;
            
            // Show attachments in preview
            const attachmentPreview = document.getElementById('preview-attachments');
            if (attachmentPreview && selectedFiles.length > 0) {
                attachmentPreview.innerHTML = `
                    <div class="preview-attachments-list">
                        <strong><i class="fas fa-paperclip"></i> Đính kèm (${selectedFiles.length}):</strong>
                        ${selectedFiles.map(f => `<span class="preview-attachment-tag">${f.name}</span>`).join('')}
                    </div>
                `;
            } else if (attachmentPreview) {
                attachmentPreview.innerHTML = '';
            }
            
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

// Gửi email từ preview với nội dung đã chỉnh sửa
async function sendEmailFromPreview() {
    const data = getComposeData();
    
    // Lấy nội dung đã chỉnh sửa từ preview
    const customSubject = document.getElementById('preview-subject-input').value.trim();
    const customBody = document.getElementById('preview-body-input').value.trim();
    
    if (!customSubject) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập tiêu đề email');
        return;
    }
    
    if (!customBody) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập nội dung email');
        return;
    }
    
    const sendBtn = document.getElementById('send-from-preview-btn');
    sendBtn.disabled = true;
    sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang gửi...';
    
    try {
        let response;
        
        if (selectedFiles.length > 0) {
            // Use FormData for file upload
            const formData = new FormData();
            formData.append('sender_name', data.sender_name);
            formData.append('recipient_name', data.recipient_name);
            formData.append('recipient_email', data.recipient_email);
            formData.append('purpose', data.purpose);
            formData.append('tone', data.tone);
            formData.append('language', data.language);
            if (data.additional_context) {
                formData.append('additional_context', data.additional_context);
            }
            if (data.notification_email) {
                formData.append('notification_email', data.notification_email);
            }
            
            // Thêm nội dung đã chỉnh sửa
            formData.append('custom_subject', customSubject);
            formData.append('custom_body', customBody);
            
            // Add files
            for (let file of selectedFiles) {
                formData.append('attachments', file);
            }
            
            const token = localStorage.getItem('auth_token');
            response = await fetch(`${API_BASE}/api/send-email`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                },
                credentials: 'include',
                body: formData
            });
        } else {
            // No attachments, use JSON với nội dung đã chỉnh sửa
            response = await authFetch(`${API_BASE}/api/send-email`, {
                method: 'POST',
                body: JSON.stringify({
                    ...data,
                    custom_subject: customSubject,
                    custom_body: customBody
                })
            });
        }
        
        const result = await response.json();
        
        if (result.success) {
            const attachmentMsg = selectedFiles.length > 0 ? ` với ${selectedFiles.length} file đính kèm` : '';
            showToast('success', 'Thành công!', `Email đã được gửi đi${attachmentMsg}`);
            clearComposeForm();
            
            // Invalidate cache and reload emails
            cache.invalidate('emails');
            cache.invalidate('dataStats');
            loadEmails(true);
            
            // Close preview
            const previewSection = document.getElementById('preview-section');
            const composeContainer = document.querySelector('.compose-container');
            previewSection.classList.remove('active');
            composeContainer.classList.remove('with-preview');
            
            if (result.monitor_started) {
                updateMonitorUI(true);
                showToast('info', 'Giám sát tự động', 'Hệ thống giám sát phản hồi đã được kích hoạt');
                addActivityLog('success', 'Auto-Monitor', 'Hệ thống giám sát đã tự động bật sau khi gửi email');
            }
        } else {
            if (result.error_code === 'EMAIL_NOT_CONFIGURED') {
                showToast('warning', 'Chưa cấu hình Email', result.error);
                if (confirm('Bạn cần cấu hình Email gửi trước khi gửi email. Chuyển đến trang Hồ sơ để cấu hình?')) {
                    document.getElementById('preview-section').classList.remove('active');
                    document.querySelector('.compose-container').classList.remove('with-preview');
                    navigateTo('profile');
                }
            } else {
                showToast('error', 'Lỗi', result.error || 'Không thể gửi email');
            }
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        sendBtn.disabled = false;
        sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i> Gửi Email';
    }
}

async function sendEmail() {
    const data = getComposeData();
    
    if (!validateComposeData(data)) return;
    
    const sendBtn = document.getElementById('send-btn');
    sendBtn.disabled = true;
    sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang gửi...';
    
    try {
        let response;
        
        // Check if there are attachments
        if (selectedFiles.length > 0) {
            // Use FormData for file upload
            const formData = new FormData();
            formData.append('sender_name', data.sender_name);
            formData.append('recipient_name', data.recipient_name);
            formData.append('recipient_email', data.recipient_email);
            formData.append('purpose', data.purpose);
            formData.append('tone', data.tone);
            formData.append('language', data.language);
            if (data.additional_context) {
                formData.append('additional_context', data.additional_context);
            }
            if (data.notification_email) {
                formData.append('notification_email', data.notification_email);
            }
            
            // Check if we have preview content
            const previewSubject = document.getElementById('preview-subject-text');
            const previewBody = document.getElementById('preview-body-text');
            if (previewSubject && previewBody && previewSubject.textContent) {
                formData.append('custom_subject', previewSubject.textContent);
                formData.append('custom_body', previewBody.textContent);
            }
            
            // Add files
            for (let file of selectedFiles) {
                formData.append('attachments', file);
            }
            
            const token = localStorage.getItem('auth_token');
            response = await fetch(`${API_BASE}/api/send-email`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                },
                credentials: 'include',
                body: formData
            });
        } else {
            // No attachments, use JSON
            response = await authFetch(`${API_BASE}/api/send-email`, {
                method: 'POST',
                body: JSON.stringify(data)
            });
        }
        
        const result = await response.json();
        
        if (result.success) {
            const attachmentMsg = selectedFiles.length > 0 ? ` với ${selectedFiles.length} file đính kèm` : '';
            showToast('success', 'Thành công!', `Email đã được gửi đi${attachmentMsg}`);
            clearComposeForm();
            
            // Invalidate cache and reload emails
            cache.invalidate('emails');
            cache.invalidate('dataStats');
            loadEmails(true);
            
            // Close preview
            const previewSection = document.getElementById('preview-section');
            const composeContainer = document.querySelector('.compose-container');
            previewSection.classList.remove('active');
            composeContainer.classList.remove('with-preview');
            
            // Check if monitor was auto-started and update UI
            if (result.monitor_started) {
                updateMonitorUI(true);
                showToast('info', 'Giám sát tự động', 'Hệ thống giám sát phản hồi đã được kích hoạt');
                addActivityLog('success', 'Auto-Monitor', 'Hệ thống giám sát đã tự động bật sau khi gửi email');
            }
        } else {
            // Handle specific error codes
            if (result.error_code === 'EMAIL_NOT_CONFIGURED') {
                showToast('warning', 'Chưa cấu hình Email', result.error);
                // Show prompt to configure email
                if (confirm('Bạn cần cấu hình Email gửi trước khi gửi email. Chuyển đến trang Hồ sơ để cấu hình?')) {
                    navigateTo('profile');
                }
            } else {
                showToast('error', 'Lỗi', result.error || 'Không thể gửi email');
            }
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
        language: document.querySelector('input[name="language"]:checked')?.value || 'vi',
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
    
    // Reset language to Vietnamese
    const viRadio = document.querySelector('input[name="language"][value="vi"]');
    if (viRadio) viRadio.checked = true;
    
    // Clear attachments
    selectedFiles = [];
    renderAttachmentList();
    const fileInput = document.getElementById('email-attachments');
    if (fileInput) fileInput.value = '';
}

// ==================== Inbox Page ====================

function initInbox() {
    const searchInput = document.getElementById('search-emails');
    const filterBtns = document.querySelectorAll('.btn-filter');
    
    // Debounced search
    if (searchInput) {
        searchInput.addEventListener('input', debounce(() => {
            renderEmails();
        }, 300));
    }
    
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            filterBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            filterEmails();
        });
    });
    
    // Debounced refresh to prevent spam clicking
    const debouncedLoadEmails = debounce(() => loadEmails(true), 500);
    document.getElementById('refresh-btn').addEventListener('click', debouncedLoadEmails);
}

// Loading state management
let isLoadingEmails = false;

async function loadEmails(forceRefresh = false) {
    // Prevent multiple simultaneous loads
    if (isLoadingEmails) return;
    
    // Check cache first
    if (!forceRefresh) {
        const cachedEmails = cache.get('emails');
        if (cachedEmails) {
            emails = cachedEmails;
            renderEmails();
            updatePendingCount();
            return;
        }
    }
    
    isLoadingEmails = true;
    
    // Show loading state
    const refreshBtn = document.getElementById('refresh-btn');
    const originalContent = refreshBtn ? refreshBtn.innerHTML : '';
    if (refreshBtn) {
        refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        refreshBtn.disabled = true;
    }
    
    try {
        const response = await deduplicatedFetch(`${API_BASE}/api/emails`);
        const result = await response.json();
        
        if (result.success) {
            emails = result.emails;
            cache.set('emails', emails);
            renderEmails();
            updatePendingCount();
        }
    } catch (error) {
        console.error('Failed to load emails:', error);
    } finally {
        isLoadingEmails = false;
        if (refreshBtn) {
            refreshBtn.innerHTML = originalContent || '<i class="fas fa-sync-alt"></i>';
            refreshBtn.disabled = false;
        }
    }
}

function groupEmailsByThread(emailList) {
    // First, deduplicate emails by id (in case of any duplicates)
    const uniqueEmails = [];
    const seenIds = new Set();
    
    emailList.forEach(email => {
        if (!seenIds.has(email.id)) {
            seenIds.add(email.id);
            uniqueEmails.push(email);
        }
    });
    
    // Group emails by thread_id or by parent relationship
    const threads = {};
    const processedIds = new Set();
    
    uniqueEmails.forEach(email => {
        // Skip if already processed
        if (processedIds.has(email.id)) return;
        processedIds.add(email.id);
        
        if (!email.parent_email_id && email.email_type !== 'reply') {
            // This is a root email (original, not a reply)
            const threadId = email.thread_id || email.id;
            if (!threads[threadId]) {
                threads[threadId] = {
                    root: email,
                    replies: []
                };
            } else {
                threads[threadId].root = email;
            }
        } else {
            // This is a reply
            const parentThreadId = email.thread_id || email.parent_email_id || email.id;
            if (!threads[parentThreadId]) {
                threads[parentThreadId] = {
                    root: null,
                    replies: []
                };
            }
            // Check if this reply is already in the list
            const existingReply = threads[parentThreadId].replies.find(r => r.id === email.id);
            if (!existingReply) {
                threads[parentThreadId].replies.push(email);
            }
        }
    });
    
    // Sort replies by sent_at and remove duplicates
    Object.values(threads).forEach(thread => {
        // Remove duplicate replies
        const uniqueReplies = [];
        const replyIds = new Set();
        thread.replies.forEach(reply => {
            if (!replyIds.has(reply.id)) {
                replyIds.add(reply.id);
                uniqueReplies.push(reply);
            }
        });
        thread.replies = uniqueReplies.sort((a, b) => new Date(a.sent_at) - new Date(b.sent_at));
    });
    
    return { threads };
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
    const items = emailList.querySelectorAll('.email-item, .email-thread');
    items.forEach(item => item.remove());
    
    if (filteredEmails.length === 0) {
        emptyState.style.display = 'block';
        return;
    }
    
    emptyState.style.display = 'none';
    
    // Group emails by thread
    const { threads } = groupEmailsByThread(filteredEmails);
    
    // Sort threads by most recent activity
    const sortedThreads = Object.entries(threads).sort((a, b) => {
        const aLatest = a[1].replies.length > 0 
            ? new Date(a[1].replies[a[1].replies.length - 1].sent_at)
            : (a[1].root ? new Date(a[1].root.sent_at) : new Date(0));
        const bLatest = b[1].replies.length > 0 
            ? new Date(b[1].replies[b[1].replies.length - 1].sent_at)
            : (b[1].root ? new Date(b[1].root.sent_at) : new Date(0));
        return bLatest - aLatest;
    });
    
    // Render threads
    sortedThreads.forEach(([threadId, thread]) => {
        if (thread.root) {
            const threadElement = createEmailThread(thread);
            emailList.insertBefore(threadElement, emptyState);
        } else if (thread.replies.length > 0) {
            // Orphan replies (shouldn't happen often)
            thread.replies.forEach(reply => {
                const item = createEmailItem(reply, true);
                emailList.insertBefore(item, emptyState);
            });
        }
    });
}

function createEmailThread(thread) {
    const { root, replies } = thread;
    const hasReplies = replies.length > 0;
    const totalInThread = 1 + replies.length;
    
    // Create thread container
    const threadContainer = document.createElement('div');
    threadContainer.className = 'email-thread';
    
    // Determine thread status
    const allEmails = [root, ...replies];
    const lastEmail = allEmails[allEmails.length - 1];
    const hasAnyResponse = allEmails.some(e => e.response_received);
    const pendingResponse = !lastEmail.response_received;
    
    // Thread header with summary
    let threadStatus = '';
    if (pendingResponse) {
        threadStatus = `<span class="thread-status pending"><i class="fas fa-clock"></i> Chờ phản hồi</span>`;
    } else {
        threadStatus = `<span class="thread-status responded"><i class="fas fa-check-circle"></i> Đã có phản hồi</span>`;
    }
    
    const threadBadge = hasReplies 
        ? `<span class="thread-badge"><i class="fas fa-comments"></i> ${totalInThread} tin nhắn</span>` 
        : '';
    
    // Create root email item
    const rootItem = createEmailItem(root, false, hasReplies);
    rootItem.classList.add('thread-root');
    
    // Add thread indicator if has replies
    if (hasReplies) {
        rootItem.innerHTML = `
            <div class="thread-indicator">
                <div class="thread-line"></div>
            </div>
        ` + rootItem.innerHTML;
    }
    
    threadContainer.appendChild(rootItem);
    
    // Create replies container (collapsible)
    if (hasReplies) {
        const repliesContainer = document.createElement('div');
        repliesContainer.className = 'thread-replies';
        
        replies.forEach((reply, index) => {
            const replyItem = createEmailItem(reply, true, index < replies.length - 1);
            replyItem.classList.add('thread-reply');
            repliesContainer.appendChild(replyItem);
        });
        
        threadContainer.appendChild(repliesContainer);
    }
    
    return threadContainer;
}

function createEmailItem(email, isReply = false, hasMoreReplies = false) {
    const item = document.createElement('div');
    item.className = 'email-item' + (isReply ? ' is-reply' : '');
    
    // Sử dụng touch event để cải thiện trải nghiệm trên mobile
    let touchStartY = 0;
    let touchMoved = false;
    
    item.addEventListener('touchstart', (e) => {
        touchStartY = e.touches[0].clientY;
        touchMoved = false;
    }, { passive: true });
    
    item.addEventListener('touchmove', (e) => {
        const touchCurrentY = e.touches[0].clientY;
        if (Math.abs(touchCurrentY - touchStartY) > 10) {
            touchMoved = true;
        }
    }, { passive: true });
    
    item.addEventListener('touchend', (e) => {
        if (!touchMoved) {
            e.preventDefault();
            showEmailDetail(email);
        }
    });
    
    // Giữ click handler cho desktop
    item.addEventListener('click', (e) => {
        // Chỉ xử lý click trên desktop (không phải touch device)
        if (!('ontouchstart' in window)) {
            showEmailDetail(email);
        }
    });
    
    // Keyboard accessibility
    item.setAttribute('role', 'button');
    item.setAttribute('tabindex', '0');
    item.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            showEmailDetail(email);
        }
    });
    
    const initials = email.recipient_name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
    const date = new Date(email.sent_at).toLocaleDateString('vi-VN', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
    
    // Determine status
    let statusHtml = '';
    let responsePreview = '';
    
    if (email.response_received) {
        const analysis = email.analysis;
        const sentiment = analysis?.sentiment || 'neutral';
        const decision = analysis?.decision || 'responded';
        
        const sentimentIcons = {
            'positive': '<i class="fas fa-smile text-success"></i>',
            'tích cực': '<i class="fas fa-smile text-success"></i>',
            'negative': '<i class="fas fa-frown text-danger"></i>',
            'tiêu cực': '<i class="fas fa-frown text-danger"></i>',
            'neutral': '<i class="fas fa-meh text-warning"></i>',
            'trung tính': '<i class="fas fa-meh text-warning"></i>'
        };
        
        const decisionText = {
            'agreed': 'Đồng ý',
            'đồng ý': 'Đồng ý',
            'disagreed': 'Từ chối',
            'không đồng ý': 'Từ chối',
            'undecided': 'Chưa quyết định',
            'chưa quyết định': 'Chưa quyết định',
            'needs_more_info': 'Cần thêm thông tin',
            'cần thêm thông tin': 'Cần thêm thông tin'
        }[decision?.toLowerCase()] || 'Đã phản hồi';
        
        const sentimentIcon = sentimentIcons[sentiment?.toLowerCase()] || sentimentIcons['neutral'];
        
        statusHtml = `
            <div class="email-response-status has-response">
                <div class="response-indicator">
                    ${sentimentIcon}
                    <span class="response-decision">${decisionText}</span>
                </div>
                <span class="status-badge responded"><i class="fas fa-envelope-open"></i> Đã phản hồi</span>
            </div>
        `;
        
        // Show response preview
        if (email.response_body) {
            const preview = email.response_body.substring(0, 80) + (email.response_body.length > 80 ? '...' : '');
            responsePreview = `
                <div class="response-preview">
                    <i class="fas fa-reply"></i>
                    <span>${preview}</span>
                </div>
            `;
        }
    } else {
        statusHtml = `
            <div class="email-response-status no-response">
                <span class="status-badge pending"><i class="fas fa-clock"></i> Chờ phản hồi</span>
            </div>
        `;
    }
    
    // Email type indicator
    const typeIndicator = isReply 
        ? '<span class="email-type-badge reply"><i class="fas fa-reply"></i> Trả lời</span>'
        : (email.email_type === 'reply' 
            ? '<span class="email-type-badge reply"><i class="fas fa-reply"></i> Trả lời</span>'
            : '<span class="email-type-badge original"><i class="fas fa-paper-plane"></i> Gửi mới</span>');
    
    item.innerHTML = `
        <div class="email-item-left">
            <div class="email-avatar ${email.response_received ? 'has-response' : ''}">${initials}</div>
            ${hasMoreReplies ? '<div class="thread-connector"></div>' : ''}
        </div>
        <div class="email-item-main">
            <div class="email-item-header">
                <div class="email-recipient-info">
                    <span class="email-recipient">${email.recipient_name}</span>
                    <span class="email-recipient-email">${email.recipient_email}</span>
                </div>
                <div class="email-meta">
                    ${typeIndicator}
                    <span class="email-date">${date}</span>
                </div>
            </div>
            <div class="email-subject">${email.subject}</div>
            <div class="email-purpose">${email.purpose}</div>
            ${responsePreview}
            ${statusHtml}
        </div>
    `;
    
    return item;
}

function filterEmails() {
    renderEmails();
}

function updatePendingCount() {
    const pendingCount = emails.filter(e => !e.response_received).length;
    document.getElementById('pending-count').textContent = pendingCount;
    
    // Auto-start checking if there are pending emails and auto-check is not running
    if (pendingCount > 0 && !autoCheckInterval && !autoCheckEnabled) {
        // Auto-enable after first email is sent
        console.log(`📬 ${pendingCount} pending emails detected, starting auto-check...`);
        startAutoCheck();
    } else if (pendingCount === 0 && autoCheckInterval) {
        // Stop auto-check if no more pending emails
        console.log('📭 No more pending emails, stopping auto-check');
        stopAutoCheck();
    }
}

// ==================== Monitor Page ====================

function initMonitor() {
    document.getElementById('start-monitor-btn')?.addEventListener('click', startMonitor);
    document.getElementById('stop-monitor-btn')?.addEventListener('click', stopMonitor);
    document.getElementById('check-once-btn')?.addEventListener('click', checkResponsesOnce);
    document.getElementById('check-imap-btn')?.addEventListener('click', checkImapConnection);
    
    // Add auto-check button handler if exists
    const autoCheckBtn = document.getElementById('auto-check-btn');
    if (autoCheckBtn) {
        autoCheckBtn.addEventListener('click', toggleAutoCheck);
    }
    
    // Initialize auto-check UI
    updateAutoCheckUI(false);
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

// Auto-check responses interval
let autoCheckInterval = null;
let autoCheckEnabled = false;
const AUTO_CHECK_INTERVAL = 30000; // 30 seconds

function startAutoCheck() {
    if (autoCheckInterval) return;
    
    autoCheckEnabled = true;
    updateAutoCheckUI(true);
    
    // Delay first check by 5 seconds to allow database to sync
    setTimeout(() => {
        if (autoCheckEnabled) {
            autoCheckResponses();
        }
    }, 5000);
    
    // Set interval for periodic checks
    autoCheckInterval = setInterval(() => {
        autoCheckResponses();
    }, AUTO_CHECK_INTERVAL);
    
    addActivityLog('success', 'Auto-check bật', `Tự động kiểm tra mỗi ${AUTO_CHECK_INTERVAL/1000} giây`);
    console.log('🔄 Auto-check started');
}

function stopAutoCheck() {
    if (autoCheckInterval) {
        clearInterval(autoCheckInterval);
        autoCheckInterval = null;
    }
    autoCheckEnabled = false;
    updateAutoCheckUI(false);
    addActivityLog('info', 'Auto-check tắt', 'Đã dừng kiểm tra tự động');
    console.log('🔄 Auto-check stopped');
}

function updateAutoCheckUI(enabled) {
    const autoCheckBtn = document.getElementById('auto-check-btn');
    const autoCheckStatus = document.getElementById('auto-check-status');
    
    if (autoCheckBtn) {
        if (enabled) {
            autoCheckBtn.innerHTML = '<i class="fas fa-stop"></i> Dừng Auto-check';
            autoCheckBtn.classList.remove('btn-success');
            autoCheckBtn.classList.add('btn-warning');
        } else {
            autoCheckBtn.innerHTML = '<i class="fas fa-robot"></i> Bật Auto-check';
            autoCheckBtn.classList.remove('btn-warning');
            autoCheckBtn.classList.add('btn-success');
        }
    }
    
    if (autoCheckStatus) {
        if (enabled) {
            autoCheckStatus.innerHTML = `<i class="fas fa-sync-alt fa-spin"></i> Auto-check: Đang chạy (mỗi ${AUTO_CHECK_INTERVAL/1000}s)`;
            autoCheckStatus.className = 'auto-check-status running';
        } else {
            autoCheckStatus.innerHTML = '<i class="fas fa-pause"></i> Auto-check: Tắt';
            autoCheckStatus.className = 'auto-check-status stopped';
        }
    }
}

async function autoCheckResponses() {
    // Only check if there are pending emails
    const pendingCount = emails.filter(e => !e.response_received).length;
    
    if (pendingCount === 0) {
        console.log('📭 No pending emails, skipping auto-check');
        return;
    }
    
    console.log(`📬 Auto-checking responses for ${pendingCount} pending emails...`);
    
    try {
        const token = localStorage.getItem('auth_token');
        const response = await fetch(`${API_BASE}/api/check-responses`, { 
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            credentials: 'include'
        });
        const result = await response.json();
        
        if (result.success) {
            const results = result.results || {};
            const found = results.responses_found || 0;
            const processed = results.responses_processed || 0;
            
            if (found > 0) {
                showToast('success', 'Phản hồi mới!', `Tìm thấy ${found} phản hồi, xử lý ${processed}`);
                addActivityLog('success', 'Auto-check', `Tìm thấy ${found} phản hồi mới`);
            } else {
                console.log('📭 Auto-check: No new responses');
            }
            
            // Reload emails to update UI
            loadEmails();
        }
    } catch (error) {
        console.error('Auto-check error:', error);
    }
}

function toggleAutoCheck() {
    if (autoCheckEnabled) {
        stopAutoCheck();
    } else {
        startAutoCheck();
    }
}

async function checkResponsesOnce() {
    const btn = document.getElementById('check-once-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang kiểm tra...';
    
    try {
        const token = localStorage.getItem('auth_token');
        const response = await fetch(`${API_BASE}/api/check-responses`, { 
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            credentials: 'include'
        });
        const result = await response.json();
        
        if (result.success) {
            const results = result.results || {};
            const pending = results.pending_emails || 0;
            const found = results.responses_found || 0;
            const processed = results.responses_processed || 0;
            
            let message = `Đã kiểm tra ${pending} email chờ phản hồi.`;
            if (found > 0) {
                message += ` Tìm thấy ${found} phản hồi, xử lý ${processed}.`;
                showToast('success', 'Có phản hồi mới!', message);
            } else {
                message += ' Chưa có phản hồi mới.';
                showToast('info', 'Hoàn tất', message);
            }
            
            addActivityLog('info', 'Kiểm tra thủ công', message);
            
            // Show details if any
            if (results.details && results.details.length > 0) {
                results.details.forEach(detail => {
                    if (detail.found > 0) {
                        addActivityLog('success', `Email #${detail.email_id}`, 
                            `${detail.recipient}: ${detail.found} phản hồi, ${detail.processed} đã xử lý`);
                    }
                });
            }
            
            if (results.errors && results.errors.length > 0) {
                results.errors.forEach(error => {
                    addActivityLog('warning', 'Lỗi', error);
                });
            }
            
            loadEmails();
        } else {
            showToast('error', 'Lỗi', result.error);
            addActivityLog('warning', 'Lỗi kiểm tra', result.error);
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
        if (statusDot) statusDot.classList.add('running');
        if (statusText) statusText.textContent = 'Đang chạy';
        if (statusIcon) {
            statusIcon.className = 'status-icon running';
            statusIcon.innerHTML = '<i class="fas fa-play-circle"></i>';
        }
        if (statusTextLarge) statusTextLarge.textContent = 'Đang chạy';
        if (startBtn) startBtn.style.display = 'none';
        if (stopBtn) stopBtn.style.display = 'inline-flex';
    } else {
        if (statusDot) statusDot.classList.remove('running');
        if (statusText) statusText.textContent = 'Đang dừng';
        if (statusIcon) {
            statusIcon.className = 'status-icon stopped';
            statusIcon.innerHTML = '<i class="fas fa-stop-circle"></i>';
        }
        if (statusTextLarge) statusTextLarge.textContent = 'Đã dừng';
        if (startBtn) startBtn.style.display = 'inline-flex';
        if (stopBtn) stopBtn.style.display = 'none';
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
    
    // Reply modal
    const replyModal = document.getElementById('reply-modal');
    if (replyModal) {
        const closeReplyBtns = replyModal.querySelectorAll('.close-reply-modal');
        const replyOverlay = replyModal.querySelector('.modal-overlay');
        
        closeReplyBtns.forEach(btn => {
            btn.addEventListener('click', closeReplyModal);
        });
        replyOverlay.addEventListener('click', closeReplyModal);
        
        // Reply email button in email detail modal
        const replyBtn = document.getElementById('reply-email-btn');
        if (replyBtn) {
            replyBtn.addEventListener('click', openReplyModal);
        }
        
        // Preview reply button
        const previewReplyBtn = document.getElementById('preview-reply-btn');
        if (previewReplyBtn) {
            previewReplyBtn.addEventListener('click', previewReplyEmail);
        }
        
        // Send reply button
        const sendReplyBtn = document.getElementById('send-reply-btn');
        if (sendReplyBtn) {
            sendReplyBtn.addEventListener('click', sendReplyEmail);
        }
    }
}

function showEmailDetail(email) {
    currentEmailId = email.id;
    window.currentEmailData = email; // Store for reply functionality
    const modal = document.getElementById('email-modal');
    const modalBody = document.getElementById('modal-body');
    
    let analysisHtml = '';
    let responseHtml = '';
    
    if (email.response_received && email.response_body) {
        responseHtml = `
            <div class="email-detail-section response-section">
                <h4><i class="fas fa-reply"></i> Phản hồi đã nhận</h4>
                <div class="response-content">
                    <div class="body-content">${email.response_body}</div>
                </div>
            </div>
        `;
    }
    
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
            <h4>Nội dung đã gửi</h4>
            <div class="body-content">${email.body}</div>
        </div>
        <div class="email-detail-section">
            <h4>Trạng thái</h4>
            <p>${email.response_received ? 
                '<span class="status-badge responded"><i class="fas fa-check"></i> Đã nhận phản hồi</span>' : 
                '<span class="status-badge pending"><i class="fas fa-clock"></i> Chờ phản hồi</span>'
            }</p>
        </div>
        ${responseHtml}
        ${analysisHtml}
    `;
    
    // Show/hide buttons based on response status
    const manualBtn = document.getElementById('manual-response-btn');
    const replyBtn = document.getElementById('reply-email-btn');
    
    if (email.response_received) {
        manualBtn.style.display = 'none';
        replyBtn.style.display = 'inline-flex';
    } else {
        manualBtn.style.display = 'inline-flex';
        replyBtn.style.display = 'none';
    }
    
    modal.classList.add('active');
}

// ==================== Reply Email Functions ====================

function openReplyModal() {
    const email = window.currentEmailData;
    if (!email) {
        showToast('error', 'Lỗi', 'Không tìm thấy thông tin email');
        return;
    }
    
    // Close email detail modal
    document.getElementById('email-modal').classList.remove('active');
    
    // Populate reply context
    const replyContext = document.getElementById('reply-context');
    replyContext.innerHTML = `
        <h5><i class="fas fa-envelope"></i> Email gốc đã gửi</h5>
        <div class="original-email">
            <strong>Đến:</strong> ${email.recipient_name} (${email.recipient_email})<br>
            <strong>Tiêu đề:</strong> ${email.subject}<br>
            <strong>Nội dung:</strong><br>
            <div style="margin-top: 8px; padding-left: 12px; border-left: 2px solid #ddd; font-size: 0.9rem;">
                ${email.body ? email.body.substring(0, 300) + (email.body.length > 300 ? '...' : '') : ''}
            </div>
        </div>
        ${email.response_body ? `
            <div class="response-received">
                <h6><i class="fas fa-reply"></i> Phản hồi từ ${email.recipient_name}</h6>
                <div style="padding-left: 12px; border-left: 2px solid #10b981; font-size: 0.9rem;">
                    ${email.response_body.substring(0, 300) + (email.response_body.length > 300 ? '...' : '')}
                </div>
            </div>
        ` : ''}
    `;
    
    // Clear previous values
    document.getElementById('reply-purpose').value = '';
    document.getElementById('reply-additional-context').value = '';
    document.getElementById('reply-preview').style.display = 'none';
    
    // Open reply modal
    document.getElementById('reply-modal').classList.add('active');
}

async function previewReplyEmail() {
    const purpose = document.getElementById('reply-purpose').value.trim();
    const additionalContext = document.getElementById('reply-additional-context').value.trim();
    
    if (!purpose) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập mục đích trả lời');
        return;
    }
    
    const btn = document.getElementById('preview-reply-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang tạo...';
    
    try {
        const response = await authFetch(`${API_BASE}/api/emails/${currentEmailId}/preview-reply`, {
            method: 'POST',
            body: JSON.stringify({
                purpose: purpose,
                additional_context: additionalContext
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            document.getElementById('reply-preview-subject').textContent = result.subject;
            document.getElementById('reply-preview-body').textContent = result.body;
            document.getElementById('reply-preview').style.display = 'block';
            
            // Store preview content for sending
            window.replyPreviewData = {
                subject: result.subject,
                body: result.body
            };
        } else {
            showToast('error', 'Lỗi', result.error || 'Không thể tạo email trả lời');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-eye"></i> Xem trước';
    }
}

async function sendReplyEmail() {
    const purpose = document.getElementById('reply-purpose').value.trim();
    const additionalContext = document.getElementById('reply-additional-context').value.trim();
    
    if (!purpose && !window.replyPreviewData) {
        showToast('error', 'Thiếu thông tin', 'Vui lòng nhập mục đích trả lời hoặc xem trước email');
        return;
    }
    
    const btn = document.getElementById('send-reply-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang gửi...';
    
    try {
        const payload = {
            purpose: purpose,
            additional_context: additionalContext
        };
        
        // If preview was generated, include it
        if (window.replyPreviewData) {
            payload.custom_subject = window.replyPreviewData.subject;
            payload.custom_body = window.replyPreviewData.body;
        }
        
        const response = await authFetch(`${API_BASE}/api/emails/${currentEmailId}/reply`, {
            method: 'POST',
            body: JSON.stringify(payload)
        });
        
        const result = await response.json();
        
        if (result.success) {
            showToast('success', 'Thành công!', 'Đã gửi email trả lời');
            
            // Close modal
            document.getElementById('reply-modal').classList.remove('active');
            
            // Clear preview data
            window.replyPreviewData = null;
            
            // Reload emails
            loadEmails();
            
            addActivityLog('success', 'Trả lời Email', `Đã gửi trả lời đến ${window.currentEmailData?.recipient_name || 'người nhận'}`);
        } else {
            if (result.error_code === 'EMAIL_NOT_CONFIGURED') {
                showToast('warning', 'Chưa cấu hình Email', result.error);
                if (confirm('Bạn cần cấu hình Email gửi. Chuyển đến trang Hồ sơ?')) {
                    document.getElementById('reply-modal').classList.remove('active');
                    navigateTo('profile');
                }
            } else {
                showToast('error', 'Lỗi', result.error || 'Không thể gửi email trả lời');
            }
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane"></i> Gửi trả lời';
    }
}

function closeReplyModal() {
    document.getElementById('reply-modal').classList.remove('active');
    window.replyPreviewData = null;
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
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
            timeout: 10000
        });
        
        socket.on('connect', () => {
            wsConnected = true;
            console.log('🔌 WebSocket connected');
            updateConnectionStatus(true);
            addActivityLog('success', 'Realtime kết nối', 'Kết nối WebSocket thành công');
            // Stop polling if WebSocket is connected
            stopPolling();
        });
        
        socket.on('disconnect', () => {
            wsConnected = false;
            console.log('🔌 WebSocket disconnected');
            updateConnectionStatus(false);
            // Start polling as fallback
            startPolling();
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
            console.log('WebSocket connection error, using polling fallback:', error);
            wsConnected = false;
            updateConnectionStatus(false);
            // Start polling as fallback for Vercel (no WebSocket support)
            startPolling();
        });
        
    } catch (error) {
        console.error('WebSocket initialization failed:', error);
        // Start polling as fallback
        startPolling();
    }
}

function updateConnectionStatus(connected, mode = null) {
    const statusElement = document.getElementById('ws-status');
    if (statusElement) {
        if (connected) {
            statusElement.className = 'ws-status connected';
            statusElement.innerHTML = '<i class="fas fa-wifi"></i> Realtime';
        } else if (mode === 'Polling') {
            statusElement.className = 'ws-status polling';
            statusElement.innerHTML = '<i class="fas fa-sync-alt"></i> Polling';
        } else {
            statusElement.className = 'ws-status disconnected';
            statusElement.innerHTML = '<i class="fas fa-wifi"></i> Offline';
        }
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
    
    // Invalidate cache and reload
    cache.invalidate('cvEvaluations');
    loadCvEvaluations(true);
}

// ==================== Server-Sent Events (Fallback) ====================

// Polling fallback for Vercel (no WebSocket/SSE support)
let pollingInterval = null;
let lastEmailCount = 0;
let lastCvCount = 0;
let pollFailCount = 0;
const MAX_POLL_INTERVAL = 120000; // Max 2 minutes between polls
const MIN_POLL_INTERVAL = 30000;  // Min 30 seconds between polls

function startPolling() {
    if (pollingInterval) return; // Already polling
    
    console.log('📡 Starting polling fallback (WebSocket unavailable)');
    updateConnectionStatus(false, 'Polling');
    pollFailCount = 0;
    
    // Smart polling - increase interval on failures, decrease on success
    scheduleNextPoll(MIN_POLL_INTERVAL);
}

function scheduleNextPoll(interval) {
    if (pollingInterval) {
        clearTimeout(pollingInterval);
    }
    
    pollingInterval = setTimeout(async () => {
        await pollForUpdates();
        
        // Adjust next interval based on success/failure
        const nextInterval = pollFailCount > 0 
            ? Math.min(MIN_POLL_INTERVAL * Math.pow(1.5, pollFailCount), MAX_POLL_INTERVAL)
            : MIN_POLL_INTERVAL;
        
        scheduleNextPoll(nextInterval);
    }, interval);
}

function stopPolling() {
    if (pollingInterval) {
        clearTimeout(pollingInterval);
        pollingInterval = null;
        console.log('📡 Polling stopped (WebSocket connected)');
    }
}

// Throttled poll to prevent too many requests
const throttledPollForUpdates = throttle(async function() {
    try {
        // Check for new emails/responses using cached fetch
        const emailResponse = await deduplicatedFetch(`${API_BASE}/api/emails`);
        const emailResult = await emailResponse.json();
        
        if (emailResult.success) {
            pollFailCount = 0; // Reset fail count on success
            const currentEmailCount = emailResult.emails.length;
            const respondedCount = emailResult.emails.filter(e => e.response_received).length;
            
            // Check if there are new responses
            if (currentEmailCount > 0) {
                const newResponses = emailResult.emails.filter(e => 
                    e.response_received && 
                    e.response_received_at && 
                    isRecentResponse(e.response_received_at)
                );
                
                if (newResponses.length > 0 && emails.length > 0) {
                    // Find truly new responses
                    const oldRespondedIds = emails.filter(e => e.response_received).map(e => e.id);
                    const newlyResponded = newResponses.filter(e => !oldRespondedIds.includes(e.id));
                    
                    newlyResponded.forEach(email => {
                        handleResponseReceived({
                            recipient_name: email.recipient_name,
                            analysis: email.analysis || { decision: 'responded' }
                        });
                    });
                }
            }
            
            emails = emailResult.emails;
            cache.set('emails', emails); // Update cache
            renderEmails();
            updatePendingCount();
        }
    } catch (error) {
        pollFailCount++;
        console.error('Poll failed:', error);
    }
}, 5000);

async function pollForUpdates() {
    await throttledPollForUpdates();
}

function isRecentResponse(timestamp) {
    if (!timestamp) return false;
    const responseTime = new Date(timestamp);
    const now = new Date();
    const diffMinutes = (now - responseTime) / (1000 * 60);
    return diffMinutes < 5; // Consider responses within last 5 minutes as "recent"
}

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
    
    // Invalidate cache and reload
    cache.invalidate('emails');
    loadEmails(true);
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

// Loading state for CV evaluations
let isLoadingCvEvaluations = false;

async function loadCvEvaluations(forceRefresh = false) {
    // Prevent multiple simultaneous loads
    if (isLoadingCvEvaluations) return;
    
    // Check cache first
    if (!forceRefresh) {
        const cachedCvs = cache.get('cvEvaluations');
        if (cachedCvs) {
            cvEvaluations = cachedCvs;
            renderCvEvaluations();
            updateCvStats();
            return;
        }
    }
    
    isLoadingCvEvaluations = true;
    
    try {
        const response = await deduplicatedFetch(`${API_BASE}/api/cv/list`);
        const result = await response.json();
        
        if (result.success) {
            cvEvaluations = result.evaluations;
            cache.set('cvEvaluations', cvEvaluations);
            renderCvEvaluations();
            updateCvStats();
        }
    } catch (error) {
        console.error('Failed to load CV evaluations:', error);
    } finally {
        isLoadingCvEvaluations = false;
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
    
    // Sử dụng touch event để cải thiện trải nghiệm trên mobile
    let touchStartY = 0;
    let touchMoved = false;
    
    item.addEventListener('touchstart', (e) => {
        touchStartY = e.touches[0].clientY;
        touchMoved = false;
    }, { passive: true });
    
    item.addEventListener('touchmove', (e) => {
        const touchCurrentY = e.touches[0].clientY;
        if (Math.abs(touchCurrentY - touchStartY) > 10) {
            touchMoved = true;
        }
    }, { passive: true });
    
    item.addEventListener('touchend', (e) => {
        if (!touchMoved) {
            e.preventDefault();
            showCvDetailModal(cv);
        }
    });
    
    // Giữ click handler cho desktop
    item.addEventListener('click', (e) => {
        if (!('ontouchstart' in window)) {
            showCvDetailModal(cv);
        }
    });
    
    // Keyboard accessibility
    item.setAttribute('role', 'button');
    item.setAttribute('tabindex', '0');
    item.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            showCvDetailModal(cv);
        }
    });
    
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

// ==================== Profile & Settings ====================

function initProfile() {
    // AI Provider toggle
    const providerRadios = document.querySelectorAll('input[name="ai-provider"]');
    providerRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            toggleAiSettings(e.target.value);
        });
    });
    
    // Save profile button
    const saveProfileBtn = document.getElementById('save-profile-btn');
    if (saveProfileBtn) {
        saveProfileBtn.addEventListener('click', saveProfile);
    }
    
    // Save settings button
    const saveSettingsBtn = document.getElementById('save-settings-btn');
    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener('click', saveAllSettings);
    }
    
    // Change password button
    const changePasswordBtn = document.getElementById('change-password-btn');
    if (changePasswordBtn) {
        changePasswordBtn.addEventListener('click', changePassword);
    }
    
    // Delete data buttons
    const deleteAllEmailsBtn = document.getElementById('delete-all-emails-btn');
    if (deleteAllEmailsBtn) {
        deleteAllEmailsBtn.addEventListener('click', deleteAllEmails);
    }
    
    const deleteAllCvsBtn = document.getElementById('delete-all-cvs-btn');
    if (deleteAllCvsBtn) {
        deleteAllCvsBtn.addEventListener('click', deleteAllCvs);
    }
    
    const deleteAllDataBtn = document.getElementById('delete-all-data-btn');
    if (deleteAllDataBtn) {
        deleteAllDataBtn.addEventListener('click', deleteAllData);
    }
    
    // Load data stats when profile page is shown
    loadDataStats();
}

function toggleAiSettings(provider) {
    const azureSettings = document.getElementById('azure-settings');
    const geminiSettings = document.getElementById('gemini-settings');
    
    if (provider === 'azure') {
        azureSettings.style.display = 'block';
        geminiSettings.style.display = 'none';
    } else {
        azureSettings.style.display = 'none';
        geminiSettings.style.display = 'block';
    }
}

function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    const icon = input.nextElementSibling.querySelector('i');
    
    if (input.type === 'password') {
        input.type = 'text';
        icon.className = 'fas fa-eye-slash';
    } else {
        input.type = 'password';
        icon.className = 'fas fa-eye';
    }
}

// Loading state for user settings
let isLoadingUserSettings = false;

async function loadUserSettings(forceRefresh = false) {
    // Prevent multiple simultaneous loads
    if (isLoadingUserSettings) return;
    
    // Check cache first
    if (!forceRefresh) {
        const cachedSettings = cache.get('userSettings');
        if (cachedSettings) {
            applyUserSettings(cachedSettings);
            return;
        }
    }
    
    isLoadingUserSettings = true;
    
    try {
        const response = await deduplicatedFetch(`${API_BASE}/api/user/settings`);
        const data = await response.json();
        
        if (data.success && data.settings) {
            cache.set('userSettings', data.settings);
            applyUserSettings(data.settings);
        }
    } catch (error) {
        console.error('Error loading settings:', error);
    } finally {
        isLoadingUserSettings = false;
    }
}

function applyUserSettings(s) {
    // Check if email is configured - show warning if not
    const emailConfigured = s.sender_email && s.sender_password;
    updateEmailConfigWarning(!emailConfigured);
    
    // Check if Gemini API key is configured - show info
    const hasCustomApiKey = !!s.gemini_api_key;
    updateApiKeyInfo(hasCustomApiKey);
    
    // AI Provider
    const provider = s.ai_provider || 'azure';
    const providerRadio = document.querySelector(`input[name="ai-provider"][value="${provider}"]`);
    if (providerRadio) {
        providerRadio.checked = true;
        toggleAiSettings(provider);
    }
    
    // Azure settings
    if (s.azure_openai_endpoint) {
        document.getElementById('setting-azure-endpoint').value = s.azure_openai_endpoint;
    }
    if (s.azure_openai_api_key) {
        document.getElementById('setting-azure-key').placeholder = s.azure_openai_api_key;
    }
    if (s.azure_openai_deployment_name) {
        document.getElementById('setting-azure-deployment').value = s.azure_openai_deployment_name;
    }
    if (s.azure_openai_api_version) {
        document.getElementById('setting-azure-version').value = s.azure_openai_api_version;
    }
    
    // Gemini settings
    if (s.gemini_api_key) {
        document.getElementById('setting-gemini-key').placeholder = s.gemini_api_key;
    }
    if (s.gemini_model) {
        document.getElementById('setting-gemini-model').value = s.gemini_model;
    }
    
    // Email settings
    if (s.sender_email) {
        document.getElementById('setting-sender-email').value = s.sender_email;
    }
    if (s.email_host) {
        document.getElementById('setting-email-host').value = s.email_host;
    }
    if (s.email_port) {
        document.getElementById('setting-email-port').value = s.email_port;
    }
    if (s.imap_host) {
        document.getElementById('setting-imap-host').value = s.imap_host;
    }
    if (s.imap_port) {
        document.getElementById('setting-imap-port').value = s.imap_port;
    }
}

// Update email config warning banner
function updateEmailConfigWarning(showWarning) {
    let warningBanner = document.getElementById('email-config-warning');
    
    if (showWarning) {
        if (!warningBanner) {
            // Create warning banner
            const composePage = document.getElementById('compose-page');
            if (composePage) {
                warningBanner = document.createElement('div');
                warningBanner.id = 'email-config-warning';
                warningBanner.className = 'config-warning-banner';
                warningBanner.innerHTML = `
                    <i class="fas fa-exclamation-triangle"></i>
                    <span>Bạn chưa cấu hình Email gửi. Chỉ có thể xem trước email, không thể gửi.</span>
                    <button onclick="navigateTo('profile')" class="btn btn-small btn-warning">
                        <i class="fas fa-cog"></i> Cấu hình ngay
                    </button>
                `;
                composePage.insertBefore(warningBanner, composePage.firstChild);
            }
        }
        warningBanner.style.display = 'flex';
        
        // Disable send button
        const sendBtn = document.getElementById('send-btn');
        if (sendBtn) {
            sendBtn.disabled = true;
            sendBtn.title = 'Bạn cần cấu hình Email gửi trước khi gửi email';
        }
    } else {
        if (warningBanner) {
            warningBanner.style.display = 'none';
        }
        // Enable send button
        const sendBtn = document.getElementById('send-btn');
        if (sendBtn) {
            sendBtn.disabled = false;
            sendBtn.title = '';
        }
    }
}

// Update API key info
function updateApiKeyInfo(hasCustomKey) {
    let apiKeyInfo = document.getElementById('api-key-info');
    const composePage = document.getElementById('compose-page');
    
    if (!apiKeyInfo && composePage) {
        apiKeyInfo = document.createElement('div');
        apiKeyInfo.id = 'api-key-info';
        apiKeyInfo.className = 'api-key-info-banner';
        
        // Insert after warning banner if exists, or at the start
        const warningBanner = document.getElementById('email-config-warning');
        if (warningBanner) {
            warningBanner.after(apiKeyInfo);
        } else {
            composePage.insertBefore(apiKeyInfo, composePage.firstChild);
        }
    }
    
    if (apiKeyInfo) {
        if (hasCustomKey) {
            apiKeyInfo.innerHTML = `
                <i class="fas fa-key"></i>
                <span>Bạn đang sử dụng Gemini API Key riêng - Không giới hạn sử dụng</span>
            `;
            apiKeyInfo.className = 'api-key-info-banner custom-key';
        } else {
            apiKeyInfo.innerHTML = `
                <i class="fas fa-info-circle"></i>
                <span>Đang dùng API key hệ thống (giới hạn miễn phí). <a href="#" onclick="navigateTo('profile'); return false;">Thêm API key riêng</a> để sử dụng không giới hạn.</span>
            `;
            apiKeyInfo.className = 'api-key-info-banner system-key';
        }
    }
}

async function saveProfile() {
    const btn = document.getElementById('save-profile-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang lưu...';
    
    try {
        const response = await authFetch(`${API_BASE}/api/auth/profile`, {
            method: 'PUT',
            body: JSON.stringify({
                full_name: document.getElementById('profile-fullname').value,
                email: document.getElementById('profile-email').value
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('success', 'Thành công!', 'Đã cập nhật thông tin cá nhân');
            // Reload user info
            await checkAuth();
        } else {
            showToast('error', 'Lỗi', data.error || 'Không thể cập nhật');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-save"></i> Lưu thông tin';
    }
}

async function saveAllSettings() {
    const btn = document.getElementById('save-settings-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang lưu...';
    
    const settings = {
        ai_provider: document.querySelector('input[name="ai-provider"]:checked').value,
        
        // Azure
        azure_openai_endpoint: document.getElementById('setting-azure-endpoint').value,
        azure_openai_deployment_name: document.getElementById('setting-azure-deployment').value,
        azure_openai_api_version: document.getElementById('setting-azure-version').value,
        
        // Gemini
        gemini_model: document.getElementById('setting-gemini-model').value,
        
        // Email
        sender_email: document.getElementById('setting-sender-email').value,
        email_host: document.getElementById('setting-email-host').value,
        email_port: parseInt(document.getElementById('setting-email-port').value) || 587,
        imap_host: document.getElementById('setting-imap-host').value,
        imap_port: parseInt(document.getElementById('setting-imap-port').value) || 993
    };
    
    // Only include passwords/keys if they were changed (not placeholder)
    const azureKey = document.getElementById('setting-azure-key').value;
    if (azureKey && !azureKey.startsWith('***')) {
        settings.azure_openai_api_key = azureKey;
    }
    
    const geminiKey = document.getElementById('setting-gemini-key').value;
    if (geminiKey && !geminiKey.startsWith('***')) {
        settings.gemini_api_key = geminiKey;
    }
    
    const senderPassword = document.getElementById('setting-sender-password').value;
    if (senderPassword && senderPassword !== '********') {
        settings.sender_password = senderPassword;
    }
    
    try {
        const response = await authFetch(`${API_BASE}/api/user/settings`, {
            method: 'POST',
            body: JSON.stringify(settings)
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('success', 'Thành công!', 'Đã lưu tất cả cài đặt');
            loadUserSettings(); // Reload to show masked values
        } else {
            showToast('error', 'Lỗi', data.error || 'Không thể lưu cài đặt');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-save"></i> Lưu tất cả cài đặt';
    }
}

async function changePassword() {
    const currentPassword = document.getElementById('current-password').value;
    const newPassword = document.getElementById('new-password').value;
    const confirmPassword = document.getElementById('confirm-new-password').value;
    
    if (!currentPassword || !newPassword || !confirmPassword) {
        showToast('error', 'Lỗi', 'Vui lòng điền đầy đủ thông tin');
        return;
    }
    
    if (newPassword !== confirmPassword) {
        showToast('error', 'Lỗi', 'Mật khẩu xác nhận không khớp');
        return;
    }
    
    const btn = document.getElementById('change-password-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang xử lý...';
    
    try {
        const response = await authFetch(`${API_BASE}/api/auth/change-password`, {
            method: 'POST',
            body: JSON.stringify({
                old_password: currentPassword,
                new_password: newPassword
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('success', 'Thành công!', 'Đã đổi mật khẩu. Vui lòng đăng nhập lại.');
            // Clear form
            document.getElementById('current-password').value = '';
            document.getElementById('new-password').value = '';
            document.getElementById('confirm-new-password').value = '';
            
            // Redirect to login after 2 seconds
            setTimeout(() => {
                logout();
            }, 2000);
        } else {
            showToast('error', 'Lỗi', data.error || 'Không thể đổi mật khẩu');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-key"></i> Đổi mật khẩu';
    }
}

// ==================== Data Management ====================

async function loadDataStats(forceRefresh = false) {
    // Check cache first
    if (!forceRefresh) {
        const cachedStats = cache.get('dataStats');
        if (cachedStats) {
            applyDataStats(cachedStats);
            return;
        }
    }
    
    try {
        const response = await deduplicatedFetch(`${API_BASE}/api/data/stats`);
        const data = await response.json();
        
        if (data.success) {
            cache.set('dataStats', data);
            applyDataStats(data);
        }
    } catch (error) {
        console.error('Error loading data stats:', error);
    }
}

function applyDataStats(data) {
    const emailCountEl = document.getElementById('email-count');
    const cvCountEl = document.getElementById('cv-count');
    
    if (emailCountEl) emailCountEl.textContent = data.email_count || 0;
    if (cvCountEl) cvCountEl.textContent = data.cv_count || 0;
}

async function deleteAllEmails() {
    const confirmed = await showConfirmDialog(
        'Xóa tất cả Email?',
        'Bạn có chắc chắn muốn xóa TẤT CẢ email đã gửi? Thao tác này không thể hoàn tác!',
        'danger'
    );
    
    if (!confirmed) return;
    
    const btn = document.getElementById('delete-all-emails-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang xóa...';
    
    try {
        const response = await authFetch(`${API_BASE}/api/emails/delete-all`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('success', 'Thành công!', `Đã xóa ${data.deleted_count} email`);
            // Invalidate cache and reload
            cache.invalidate('emails');
            cache.invalidate('dataStats');
            loadDataStats(true);
            loadEmails(true);
        } else {
            showToast('error', 'Lỗi', data.error || 'Không thể xóa email');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-trash-alt"></i> Xóa tất cả Email';
    }
}

async function deleteAllCvs() {
    const confirmed = await showConfirmDialog(
        'Xóa tất cả CV?',
        'Bạn có chắc chắn muốn xóa TẤT CẢ CV đã đánh giá? Thao tác này không thể hoàn tác!',
        'danger'
    );
    
    if (!confirmed) return;
    
    const btn = document.getElementById('delete-all-cvs-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang xóa...';
    
    try {
        const response = await authFetch(`${API_BASE}/api/cv/delete-all`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('success', 'Thành công!', `Đã xóa ${data.deleted_count} CV`);
            // Invalidate cache and reload
            cache.invalidate('cvEvaluations');
            cache.invalidate('dataStats');
            loadDataStats(true);
            loadCvEvaluations(true);
        } else {
            showToast('error', 'Lỗi', data.error || 'Không thể xóa CV');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-trash-alt"></i> Xóa tất cả CV';
    }
}

async function deleteAllData() {
    const confirmed = await showConfirmDialog(
        'Xóa TOÀN BỘ dữ liệu?',
        'Bạn có chắc chắn muốn xóa TẤT CẢ email VÀ CV? Thao tác này KHÔNG THỂ hoàn tác!',
        'danger'
    );
    
    if (!confirmed) return;
    
    // Double confirm for this dangerous action
    const doubleConfirmed = await showConfirmDialog(
        'XÁC NHẬN LẦN NỮA',
        'Đây là thao tác nguy hiểm! Tất cả dữ liệu sẽ bị xóa vĩnh viễn. Bạn thực sự muốn tiếp tục?',
        'danger'
    );
    
    if (!doubleConfirmed) return;
    
    const btn = document.getElementById('delete-all-data-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang xóa...';
    
    try {
        const response = await authFetch(`${API_BASE}/api/data/delete-all`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('success', 'Thành công!', `Đã xóa ${data.deleted_emails} email và ${data.deleted_cvs} CV`);
            loadDataStats();
            loadEmails();
            loadCvEvaluations();
        } else {
            showToast('error', 'Lỗi', data.error || 'Không thể xóa dữ liệu');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-exclamation-triangle"></i> Xóa toàn bộ dữ liệu';
    }
}

async function deleteEmail(emailId) {
    const confirmed = await showConfirmDialog(
        'Xóa email này?',
        'Bạn có chắc chắn muốn xóa email này? Thao tác không thể hoàn tác.',
        'warning'
    );
    
    if (!confirmed) return;
    
    try {
        const response = await authFetch(`${API_BASE}/api/emails/${emailId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('success', 'Đã xóa', 'Email đã được xóa');
            loadEmails();
            loadDataStats();
        } else {
            showToast('error', 'Lỗi', data.error || 'Không thể xóa email');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    }
}

async function deleteCv(cvId) {
    const confirmed = await showConfirmDialog(
        'Xóa CV này?',
        'Bạn có chắc chắn muốn xóa CV này? Thao tác không thể hoàn tác.',
        'warning'
    );
    
    if (!confirmed) return;
    
    try {
        const response = await authFetch(`${API_BASE}/api/cv/${cvId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast('success', 'Đã xóa', 'CV đã được xóa');
            loadCvEvaluations();
            loadDataStats();
        } else {
            showToast('error', 'Lỗi', data.error || 'Không thể xóa CV');
        }
    } catch (error) {
        showToast('error', 'Lỗi kết nối', 'Không thể kết nối đến server');
    }
}

function showConfirmDialog(title, message, type = 'warning') {
    return new Promise((resolve) => {
        // Create modal
        const modal = document.createElement('div');
        modal.className = 'modal confirm-modal active';
        modal.innerHTML = `
            <div class="modal-overlay"></div>
            <div class="modal-content confirm-dialog ${type}">
                <div class="modal-header">
                    <h2><i class="fas fa-${type === 'danger' ? 'exclamation-triangle' : 'question-circle'}"></i> ${title}</h2>
                </div>
                <div class="modal-body">
                    <p>${message}</p>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" id="confirm-cancel">
                        <i class="fas fa-times"></i> Hủy
                    </button>
                    <button class="btn btn-${type === 'danger' ? 'danger' : 'primary'}" id="confirm-ok">
                        <i class="fas fa-check"></i> Xác nhận
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // Handle clicks
        modal.querySelector('#confirm-cancel').addEventListener('click', () => {
            modal.remove();
            resolve(false);
        });
        
        modal.querySelector('#confirm-ok').addEventListener('click', () => {
            modal.remove();
            resolve(true);
        });
        
        modal.querySelector('.modal-overlay').addEventListener('click', () => {
            modal.remove();
            resolve(false);
        });
    });
}

// Make functions globally available
window.previewCvEmail = previewCvEmail;
window.allowResendEmail = allowResendEmail;
window.togglePassword = togglePassword;
window.logout = logout;
window.deleteEmail = deleteEmail;
window.deleteCv = deleteCv;
window.removeAttachment = removeAttachment;

