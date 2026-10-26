# 🎴 Mimi Helper Bot

Bot Discord giúp ping role khi **bot Mimi** (`<@1476927725775356037>`) drop card.

## ✨ Tính năng

- 🔔 **Tự động ping role** khi phát hiện Mimi drop card
- ⚙️ **Slash commands** (`/setup`) dễ sử dụng
- 🏠 **Cấu hình per-server** — mỗi server thiết lập riêng
- 📌 **Chọn kênh ping** — ping ở cùng kênh hoặc kênh riêng
- 🔄 **Bật/tắt** linh hoạt
- 🧹 **Tự xóa ping** sau 30 giây để tránh spam

## 🚀 Cài đặt

### 1. Tạo Bot trên Discord Developer Portal

1. Truy cập https://discord.com/developers/applications
2. Tạo Application mới → vào tab **Bot**
3. Copy **Bot Token**
4. Bật các **Privileged Gateway Intents**:
   - ✅ Message Content Intent
   - ✅ Server Members Intent
5. Tạo invite link (tab **OAuth2 → URL Generator**):
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Send Messages`, `Read Messages/View Channels`, `Manage Messages`

### 2. Cài đặt

```bash
# Clone hoặc tải project
cd quick-franklin

# Cài dependencies
pip install -r requirements.txt

# Tạo file .env từ template
copy .env.example .env

# Sửa file .env và dán Bot Token vào
```

### 3. Chạy bot

```bash
python bot.py
```

## 📖 Hướng dẫn sử dụng

### Slash Commands (Khuyến nghị)

| Lệnh | Mô tả |
|-------|--------|
| `/setup role @Role` | Chọn role sẽ được ping |
| `/setup channel #channel` | Chọn kênh gửi thông báo (tùy chọn) |
| `/setup toggle True/False` | Bật/tắt bot |
| `/setup status` | Xem cấu hình hiện tại |

### Prefix Commands (Backup)

| Lệnh | Mô tả |
|-------|--------|
| `!setrole @Role` | Thiết lập role ping |
| `!removerole` | Xóa role ping |
| `!botstatus` | Xem trạng thái |

> **Lưu ý:** Các lệnh setup yêu cầu quyền **Manage Server**.

## 🔄 Cách hoạt động

1. Bot lắng nghe tất cả tin nhắn trong server
2. Khi phát hiện tin nhắn từ **bot Mimi** (ID: `1476927725775356037`)
3. Kiểm tra nội dung có chứa pattern drop card (`dropped X cards!`)
4. Nếu đúng → ping role đã thiết lập
5. Tin nhắn ping tự xóa sau 30 giây

## 📁 Cấu trúc project

```
quick-franklin/
├── bot.py              # Code chính của bot
├── requirements.txt    # Dependencies
├── .env.example        # Template file cấu hình
├── .env                # File cấu hình (tự tạo)
├── .gitignore
├── README.md
└── data/
    └── config.json     # Cấu hình per-server (tự tạo)
```
