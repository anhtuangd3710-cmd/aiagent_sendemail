# Email AI Agent 🤖📧

Một AI Agent hoàn chỉnh sử dụng Azure OpenAI để tự động soạn email và phân tích phản hồi.

## ✨ Tính năng

- ✅ **Giao diện Web hiện đại** - UI đẹp, dễ sử dụng, responsive
- ✅ **Tự động soạn email** - AI tạo email chuyên nghiệp dựa trên mục đích của bạn
- ✅ **Gửi email tự động** - Gửi email đến người nhận bất kỳ
- ✅ **Giám sát phản hồi** - Tự động kiểm tra và nhận phản hồi từ người nhận
- ✅ **Phân tích thông minh** - AI phân tích nội dung phản hồi, xác định:
  - Cảm xúc (tích cực/tiêu cực/trung tính)
  - Quyết định (đồng ý/không đồng ý/chưa quyết định)
  - Các điểm chính trong phản hồi
  - Các hành động cần thực hiện
- ✅ **Thông báo tự động** - Gửi email thông báo kết quả phân tích đến người gửi ban đầu

## 🚀 Cài đặt

### 1. Clone dự án
```bash
cd agentsendemail
```

### 2. Tạo môi trường ảo (khuyến nghị)
```bash
python -m venv venv
venv\Scripts\activate  # Windows
# hoặc
source venv/bin/activate  # Linux/Mac
```

### 3. Cài đặt dependencies
```bash
pip install -r requirements.txt
```

### 4. Cấu hình môi trường
```bash
# Copy file cấu hình mẫu
copy .env.example .env  # Windows
# hoặc
cp .env.example .env  # Linux/Mac
```

Chỉnh sửa file `.env` với thông tin của bạn:

```env
# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=https://your-resource-name.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4

# Email Configuration
SENDER_EMAIL=your-email@gmail.com
SENDER_PASSWORD=your-app-password
```

### Cấu hình Gmail
1. Bật xác thực 2 yếu tố (2FA) cho tài khoản Gmail
2. Tạo App Password tại: https://myaccount.google.com/apppasswords
3. Sử dụng App Password trong file `.env`

## 🖥️ Sử dụng

### Giao diện Web (Khuyến nghị)
```bash
python app.py
```
Mở trình duyệt và truy cập: **http://localhost:5000**

### Chế độ Command Line

#### Interactive Mode
```bash
python main.py interactive
```

#### Gửi email mới
```bash
python main.py send \
    --sender-name "Nguyễn Văn A" \
    --recipient-name "Trần Văn B" \
    --recipient-email "b@example.com" \
    --purpose "Mời họp về dự án mới vào thứ 6 tuần này" \
    --tone professional
```

#### Bắt đầu giám sát phản hồi
```bash
python main.py monitor
```

#### Kiểm tra phản hồi một lần
```bash
python main.py check
```

#### Xem danh sách email đã gửi
```bash
python main.py list
```

## 📁 Cấu trúc dự án

```
agentsendemail/
├── config/
│   ├── __init__.py
│   └── settings.py              # Cấu hình hệ thống
├── services/
│   ├── __init__.py
│   ├── ai_agent.py              # AI Agent sử dụng Azure OpenAI
│   ├── database.py              # Quản lý database SQLite
│   ├── email_service.py         # Dịch vụ gửi/nhận email
│   └── email_monitor.py         # Giám sát phản hồi email
├── static/
│   ├── css/
│   │   └── style.css            # Styles cho UI
│   └── js/
│       └── app.js               # Frontend JavaScript
├── templates/
│   └── index.html               # Giao diện Web
├── app.py                       # Flask Web Server
├── main.py                      # CLI Application
├── requirements.txt             # Dependencies
├── .env.example                 # File cấu hình mẫu
└── README.md                    # Tài liệu này
```

## Luồng hoạt động

```
┌─────────────────────────────────────────────────────────────┐
│                    NGƯỜI DÙNG A                              │
│  1. Nhập yêu cầu: "Mời B họp về dự án X"                   │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    AI AGENT                                  │
│  2. Azure OpenAI tạo email chuyên nghiệp                    │
│     - Subject: "Lời mời họp về dự án X"                     │
│     - Body: Nội dung email hoàn chỉnh                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                 EMAIL SERVICE                                │
│  3. Gửi email đến người B                                   │
│  4. Lưu thông tin vào database để theo dõi                  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                 EMAIL MONITOR                                │
│  5. Giám sát hộp thư đến, chờ phản hồi từ B                │
└──────────────────────┬──────────────────────────────────────┘
                       │ (Khi B phản hồi)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    AI AGENT                                  │
│  6. Phân tích phản hồi:                                     │
│     - Sentiment: Tích cực/Tiêu cực                          │
│     - Decision: Đồng ý/Không đồng ý                         │
│     - Key points: Các điểm quan trọng                       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    THÔNG BÁO                                 │
│  7. Gửi email thông báo kết quả phân tích đến A            │
│     - Tóm tắt phản hồi của B                                │
│     - Quyết định: B đồng ý/không đồng ý                     │
│     - Các bước tiếp theo cần thực hiện                      │
└─────────────────────────────────────────────────────────────┘
```

## API Usage (Sử dụng như thư viện)

```python
from services import EmailService, AIAgent, DatabaseService, EmailMonitor

# Khởi tạo services
email_service = EmailService()
ai_agent = AIAgent()
database = DatabaseService()

# Tạo email bằng AI
email = ai_agent.generate_email(
    sender_name="Nguyễn Văn A",
    recipient_name="Trần Văn B",
    recipient_email="b@example.com",
    purpose="Mời họp thảo luận dự án mới",
    tone="professional"
)

# Gửi email
email_service.send_email(
    recipient_email="b@example.com",
    subject=email['subject'],
    body=email['body']
)

# Phân tích phản hồi
analysis = ai_agent.analyze_response(
    original_email_subject=email['subject'],
    original_email_body=email['body'],
    original_purpose="Mời họp",
    response_body="Cảm ơn anh, tôi sẽ tham gia...",
    response_subject="Re: Lời mời họp"
)

print(f"Quyết định: {analysis['decision']}")
print(f"Tóm tắt: {analysis['summary']}")
```

## Lưu ý bảo mật

- ⚠️ Không commit file `.env` vào git
- ⚠️ Sử dụng App Password thay vì mật khẩu chính
- ⚠️ Bảo mật API key của Azure OpenAI

## License

MIT License
