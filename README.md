# Hisobot Bot

Telegram bot va web-ilova loyihasi. Xodim va superadminning ish jarayonlari Telegram Mini App ichidagi web-ilovada bajariladi. Bot xodimga o'z Telegram ID sini ko'rsatadi, Mini App tugmasini beradi va karta so'rovlari haqida admin guruhiga xabar yuboradi. Ilova hozircha SQLite'dan foydalanadi; lokal/server muhitlarining ma'lumotlar bazasini alohida sozlang.

## Lokal ishga tushirish (Docker)

1. `.env.example` faylidan `.env` nusxa yarating.
2. BotFather'da chatga yuborilgan tokenni bekor qilib, yangisini yarating. Yangi tokenni faqat `.env` ichidagi `BOT_TOKEN` qiymatiga joylang; tokenni kodga yoki GitHub'ga kiritmang.
3. `.env` ichida `SUPERADMIN_ID`, karta so'rovlari uchun `ADMIN_GROUP_ID` va kunlik hisobotlar uchun `REPORT_GROUP_ID` ni sozlang; maxfiy kalit va baza parolini kiriting. `SECRET_KEY` kamida 32 belgidan iborat tasodifiy qiymat bo'lsin.
4. Loyiha ildizida ishga tushiring:

   ```powershell
   docker compose up --build
   ```

5. API holatini `http://localhost:8000/health` manzilida tekshiring. Xodim botda `/start` yuborib o'z Telegram ID sini oladi; admin amallari web-panelda bajariladi.
6. Superadmin Telegram botda `/start` yuboradi. Chatning pastki menyusida paydo bo'ladigan `Admin panel` tugmasini bosing. Admin panel xabar ko'rinishida kelmaydi; login/parol so'ralmaydi.
7. Xodim Mini App tugmasini olish uchun `.env` ichidagi `WEB_APP_URL` ga HTTPS manzilini qo'ying, masalan vaqtinchalik HTTPS tunnel yoki deployed domenning `https://.../employee` manzili. Telegram Mini App oddiy `http://localhost` manzilidan ochilmaydi. Cloudflare Tunnel o'rnatilgan bo'lsa, alohida terminalda `cloudflared tunnel --url http://localhost:8000` buyrug'ini ishga tushiring, bergan `https://...trycloudflare.com` manzilining oxiriga `/employee` qo'shib `WEB_APP_URL` ga yozing va botni qayta ishga tushiring.

`SECRET_KEY` yaratish uchun:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Docker o'rnatilmagan bo'lsa, Python 3.12+ muhitida kutubxonalarni `pip install -r requirements.txt` orqali o'rnating. API `uvicorn app.main:app --reload` bilan, Telegram bot esa alohida terminalda `python -m app.bot` bilan ishga tushadi. Web-panel `http://localhost:8000` da, xodimlar esa `data/employees.sqlite3` faylida bo'ladi.

## Maxfiy ma'lumotlar

- Haqiqiy qiymatlarni `.env` yoki serverning maxfiy sozlamalar omborida saqlang; `.env` Git va Docker build kontekstidan chiqarilgan.
- Admin panel login/parol ishlatmaydi. Superadmin faqat bot chatining pastki menyusidagi `Admin panel` Web App tugmasi orqali kiradi; server Telegram Mini App imzosini tekshiradi va superadmin Telegram ID siga mos bo'lgandagina ruxsat beradi. Panelni oddiy brauzerda ochganda Telegram tasdiqlovi bo'lmagani uchun boshqaruv ishlamaydi.
- GitHub'ga faqat o'rinbosar qiymatlari bor `.env.example` yuboriladi.
- Production uchun alohida baza va alohida kuchli sirlar ishlating; lokal `.env` faylini serverga yoki repozitoriyga ko'chirmang.
- `docker-compose.yml` faqat lokal ishlab chiqish uchun. Production'da `POSTGRES_PASSWORD` va boshqa maxfiy sozlamalarni platformaning secret/environment sozlamalaridan bering, servislarni HTTPS reverse proxy ortida joylashtiring va ma'lumotlar bazasi portini internetga ochmang.
- Xodim botda `/start` yuboradi va ko'rsatilgan Telegram ID sini superadminga yuboradi. Superadmin xodimni web-panelda ro'yxatdan o'tkazadi.
- Telegram Mini App login Telegram imzosini tekshiradi, xodim ID si faol profil bilan mosligini tasdiqlaydi va 12 soatlik HttpOnly sessiya beradi. Xodim ishdan bo'shatilsa, keyingi so'rovda profil tekshiruvidan o'tmaydi.
- Superadmin panelda xodim qo'shadi/bo'shatadi, qarz belgilaydi, berilgan summalar va hisobotlarni ko'rib tasdiqlaydi yoki sabab bilan rad etadi. Karta so'rovlari tarix/qaror bo'limi panelda ko'rsatilmaydi; ularning tasdig'i faqat Telegram guruhidagi admin tugmalari orqali boshqariladi.
- Har bir kunlik hisobot alohida `REPORT_GROUP_ID` guruhiga bitta xabar sifatida yuboriladi. Xodim shu hisobot sanasi uchun qayta yuborsa, oldingi guruh xabari o'chirilib yangisi yuboriladi va hisobot admin tasdig'iga qaytadi. Oldingi hisobot tasdiqlangan bo'lsa, uning qarzga ta'siri qaytariladi. Bot hisobot guruhiga qo'shilgan bo'lishi kerak.
- Karta so'rovi admin guruhiga emoji va tasdiqlash/rad etish tugmalari bilan yuboriladi. Bir xil karta raqamiga O'zbekiston vaqti bilan shu kalendar kuni ikkinchi yoki undan keyingi so'rov tushsa, guruh xabarida bugun bu kartaga to'lov qilingani haqida ogohlantirish ko'rsatiladi. Tugmani bosganda bot guruhdagi bosuvchining admin/creator maqomini tekshiradi; oddiy a'zolar qarorni o'zgartira olmaydi. Guruhdagi qaror o'zgarganda xabar holati va qarama-qarshi tugma yangilanadi. Bu tekshiruv ishlashi uchun botni guruhga admin qilib qo'shing va `.env` dagi `ADMIN_GROUP_ID` ni o'sha guruh ID siga moslang.
- Xodim Mini App'da karta to'ldirish so'rovi uchun aynan 16 raqamli karta raqami (har to'rt raqamda bo'shliq ko'rinishida), faqat harfli karta egasi va faqat raqamli, uchlik guruhlarga ajratilgan summa kiritadi. Karta so'rovi summasi kamida 10 000 so'm bo'lishi kerak; 3% qo'shilgandan so'ng jami keyingi 1 000 so'mga yuqoriga yaxlitlanadi. Uchala maydon majburiy. Berilgan summa va kunlik hisobot ham yuborib, o'z tarixini ko'ra oladi. Karta va tasdiqlangan pul summalari hisobotda avtomatik jamlanadi; qarz hisobot tasdiqlangandagina kamayadi.
- Frontend fayllari `app/static/` ichida: `index.html`, `employee.html`, `app.css`, `admin.js`, `employee.js`. FastAPI ularni `/` va `/employee` sahifalarida hamda `/static/` yo'lida taqdim etadi.
- Reyting oylik va umumiy kesimlarda ko'rsatiladi: har 100 000 so'm tasdiqlangan karta summasi (+3% ustama bilan), tasdiqlangan berilgan summa va tasdiqlangan hisobotdagi "Jami topshirilishi kerak" qiymati +1 ball; har 100 000 so'm joriy qarz qoldig'i -1 ball. Ball ikki kasr xonasigacha hisoblanadi va xodim hamda admin web-ilovasida ko'rinadi. Cheklangan admin rollari va PostgreSQL/production joylashuvi hali alohida yakunlanishi kerak. Hozirgi kodning ishlashini quyidagicha tekshiring: `python -m unittest discover -s tests`.
