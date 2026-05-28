# 🤖 LD Secretary Bot

AI เลขาส่วนตัว สำหรับ OWNDAYS L&D Thailand
LINE Bot + Claude API

---

## 📋 สิ่งที่ต้องเตรียม

1. **LINE Developers Account** → https://developers.line.biz/
2. **Anthropic API Key** → https://console.anthropic.com/
3. **Railway Account** → https://railway.app/ (หรือ host อื่น)
4. **GitHub Account** → สำหรับ deploy

---

## 🚀 วิธี Deploy บน Railway

### 1. Push code ขึ้น GitHub

```bash
git init
git add .
git commit -m "Initial: LD Secretary Bot"
git remote add origin https://github.com/YOUR_USERNAME/ld-secretary-bot.git
git push -u origin main
```

### 2. สร้าง Project บน Railway

1. ไปที่ https://railway.app/ → Login ด้วย GitHub
2. กด **New Project** → **Deploy from GitHub repo**
3. เลือก repo `ld-secretary-bot`
4. Railway จะ detect Python + Procfile อัตโนมัติ

### 3. ตั้ง Environment Variables

ใน Railway → Settings → Variables → เพิ่ม:

| Variable | ค่า |
|---|---|
| `LINE_CHANNEL_SECRET` | จาก LINE Developers Console |
| `LINE_CHANNEL_ACCESS_TOKEN` | จาก LINE Developers Console |
| `ANTHROPIC_API_KEY` | จาก Anthropic Console |

### 4. ตั้ง Webhook ใน LINE

1. ไปที่ LINE Developers Console → Channel ของคุณ → Messaging API
2. Webhook URL: `https://YOUR-APP.railway.app/webhook`
3. กด **Verify** → ต้องขึ้น Success
4. เปิด **Use webhook** → ON
5. ปิด **Auto-reply messages** → OFF (สำคัญ!)

### 5. ทดสอบ

Scan QR Code ของ bot → ส่งข้อความ → ควรได้คำตอบจาก AI

---

## 📁 โครงสร้างไฟล์

```
ld-secretary-bot/
├── app.py              # Main application
├── requirements.txt    # Python dependencies
├── Procfile           # Railway/Heroku deploy config
├── .env.example       # Environment variables template
└── README.md          # This file
```

---

## 🔮 Roadmap

- [x] Step 1: LINE Bot + Claude API (Basic chat)
- [ ] Step 2: เชื่อม Google Sheets API (ดึงข้อมูล L&D)
- [ ] Step 3: Daily Brief อัตโนมัติทุกเช้า
- [ ] Step 4: Memory + Task tracking
- [ ] Step 5: Agent-to-Agent handoff
