# Xodimlar hisobot va reyting tizimi — loyiha rejasi

## Maqsad

Web-ilova orqali xodimlar, kunlik hisobotlar, karta to'ldirish so'rovlari, pul operatsiyalari va qarzdorlikni boshqarish. Telegram bot faqat boshlang'ich ro'yxatdan o'tishda ID ko'rsatadi va bildirishnomalar yuboradi. Tizim lokal muhitda sinov ma'lumotlari bilan, serverda esa alohida production ma'lumotlar bazasi bilan ishlaydi.

## Kelishilgan talablar

- Xodimlar barcha ish jarayonlarini web-ilovada bajaradi. Telegram bot xodimga Telegram ID sini ko'rsatadi va bildirishnomalar yuboradi; karta so'rovi uchun admin guruhida faqat Telegram adminlari qaror tugmalaridan foydalanishi mumkin.
- Xodim botda `/start` yuborib o'z Telegram ID sini oladi va superadminga beradi. Superadmin web-panelda xodimni ro'yxatdan o'tkazadi; web-ilovaga kirishda profil Telegram ID bilan xavfsiz tasdiqlanadi.
- Admin rollari: barcha huquqli superadmin va cheklangan huquqli adminlar.
- Superadmin xodimlarni ishga oladi, bot taniydigan nomini belgilaydi, ishdan bo'shatadi va qarzdorlik belgilaydi.
- Ishdan bo'shatilgan xodimning kirishi darhol bloklanadi. Xodimga tegishli ish ma'lumotlari va tarixi 1 oydan so'ng o'chiriladi.
- Hisobot shabloni tasdiqlanishi yoki rad etilishi mumkin; qaror va sabablar tarixda ko'rinadi.
- Reyting joriy oy va umumiy davr uchun alohida hisoblanadi. Har 100 000 so'm tasdiqlangan karta summasi (3% ustama bilan), tasdiqlangan berilgan summa va tasdiqlangan hisobotdagi "Jami topshirilishi kerak" qiymati uchun +1 ball; har 100 000 so'm joriy qarz qoldig'i uchun -1 ball. Ball ikki kasr xonasigacha yaxlitlanadi, teng ball olganlar bir xil o'rinni egallaydi.
- Lokal muhit sinov uchun alohida ma'lumotlardan, server esa production ma'lumotlaridan foydalanadi.

## Hisobot shakli

Xodim har ish kuni uchun bitta hisobot yuboradi. Quyidagi maydon nomlari yuborilgan shablondan olindi.

| Bo'lim | Maydon | Kiritish va hisoblash qoidasi |
|---|---|---|
| Hisobot | Paynet | Xodim kiritadi |
| Hisobot | Card (+3%) | Tasdiqlangan karta to'ldirish so'rovlari summasidan tizim avtomatik hisoblaydi: summa + 3% |
| Hisobot | Levy | Xodim kiritadi |
| Hisobot | SIMcard (dona) | Xodim dona sonini kiritadi |
| Hisobot | Qarzdorlik | Superadmin belgilaydi; tasdiqlangan qarz to'lovidan keyin qoldiq avtomatik kamayadi |
| Hisobot | Qarz uchun | Xodim qarzni yopish uchun bergan summani kiritadi; qarz faqat hisobot tasdiqlangach kamayadi |
| Minus | Terminal | Xodim kiritadi |
| Minus | Berildi (Tasdiqlangan) | Xodim bergan va admin tasdiqlagan summalarning shu kundagi jami avtomatik ko'rsatiladi |
| Minus | Kunlik | Xodim kiritadi |
| Minus | Skidka | Xodim kiritadi |
| Minus | Xarajat | Xodim kiritadi |
| Minus | Comment | Xodim uchun ixtiyoriy izoh |

Pul summalari butun so'mda saqlanadi. 3% ustama qo'shilgandan keyingi karta jami keyingi 1 000 so'mlik qiymatga yuqoriga yaxlitlanadi (masalan, 10 000 so'm → 11 000 so'm; 100 000 so'm → 103 000 so'm).

Hisobot web-ilovadan yuborilgach admin web-ilovada ko'rib chiqadi va tasdiqlaydi yoki rad etish sababini yozadi. Tasdiqlanmagan hisobot qarzdorlik qoldig'ini o'zgartirmaydi. Har bir xodim va hisobot sanasi uchun faqat bitta joriy hisobot saqlanadi va hisobot alohida Telegram guruhiga yuboriladi. Xodim shu sana uchun qayta yuborsa, oldingi guruh xabari o'chirilib yangisi yuboriladi, hisobot qayta ko'rib chiqish uchun kutilmoqda holatiga tushadi. Oldingi hisobot tasdiqlangan bo'lsa, yangi hisobotdagi qarz tekshiruvidan oldin avvalgi qarz to'lovi ledgerda qaytariladi. Xodim va admin hisobotlarning holati va tarixini web-ilovada ko'ra oladi.

## Asosiy ish jarayonlari

### Xodimlar

1. Xodim botda `/start` yuborib o'zining raqamli Telegram ID sini oladi.
2. Xodim ID sini superadminga beradi; admin xodim profili va bot taniydigan nomini web-panelda kiritadi.
3. Xodim Telegram ichidagi Mini App tugmasi orqali web-ilovani ochadi. Server Telegram imzosini tekshiradi, faol profilning Telegram ID si mos bo'lsa, HttpOnly sessiya beradi.
4. Ishdan bo'shatilganda web-ilovadagi akkaunt darhol bloklanadi, xodimga tegishli ma'lumotlar 1 oylik saqlash muddati tugagach o'chiriladi.
5. Admin web-panelda faol xodimlar ro'yxatini, qarzdorlikni, hisobot va operatsiyalar tarixini ko'radi.

### Karta to'ldirish

1. Xodim web-ilovada 16 xonali karta raqami, karta egasining ismi-familiyasi va so'mdagi summani kiritib so'rov yuboradi.
2. Web-ilova admin Telegram guruhiga to'liq karta raqami va emoji bilan so'rov yuboradi; xabarda tasdiqlash va rad etish tugmalari bo'ladi.
3. Guruhda tugmani bosganda bot foydalanuvchining guruh admini ekanini tekshiradi; oddiy a'zoning qarori qabul qilinmaydi. Guruh admini so'rovni tasdiqlaydi yoki rad etadi, xabar holati yashil belgi/qizil x bilan yangilanadi.
4. Qaror qabul qilingandan so'ng tugma qarama-qarshi amalni ko'rsatadi; guruh admini qarorni qayta o'zgartira oladi. Har bir o'zgarish admin ID si va vaqti bilan audit qilinadi.
5. Xodim web-ilovada faqat o'z so'rovlari va tarixini ko'radi; boshqa xodimlarning karta ma'lumoti ochilmaydi.
6. Tarixda sana-vaqt, karta raqami, karta egasi, asl summa, holat va tasdiqlangan so'rov uchun 3% qo'shilgan yakuniy summa aks etadi.
7. Faqat tasdiqlangan so'rov uchun 3% hisoblanadi; shu kun hisobotining `Card (+3%)` maydoniga 3% qo'shilgan summa kiritiladi. Qaror o'zgarsa, hisobot summasi ham qayta hisoblanadi.
8. Xodim o'z so'rovlari va qarorlar tarixini, admin esa barcha so'rovlar tarixini ko'radi.

### Berilgan/olingan pul summalari

1. Xodim ish jarayonida bergan summasini yuboradi.
2. Admin web-ilovada tasdiqlaydi yoki rad etadi.
3. Faqat shu kun uchun tasdiqlangan summalar kunlik hisobotdagi `Berildi (Tasdiqlangan)` maydonida jamlanadi.
4. Xodim o'z operatsiyalarining holati va tarixini ko'radi.

### Qarzdorlik

- Superadmin xodimning qarzdorligini belgilaydi va o'zgarishlar qayd etiladi.
- Xodim kunlik hisobotda `Qarz uchun` qiymatini kiritadi.
- Hisobot tasdiqlangandagina shu summa qarzdorlik qoldig'idan ayriladi; rad etilgan hisobot qarzni o'zgartirmaydi.
- Admin qarzdorliklar ro'yxati, qoldiq va tarixni ko'radi.

### Kunlik hisobot xabari

- Har bir hisobot yuborilganda to'liq kunlik ko'rsatkichlar `REPORT_GROUP_ID` bilan belgilangan Telegram guruhiga bitta xabar qilib yuboriladi.
- Bir xodim bir hisobot sanasi uchun qayta yuborsa, oldingi Telegram xabari o'chirilib, yangilangan hisobot yangi xabar bilan yuboriladi; bazada bitta joriy yozuv saqlanadi.
- Oldingi hisobot tasdiqlangan bo'lsa, yangi versiya kutishga o'tishidan oldin undagi qarz to'lovi ledgerda teskari yozuv bilan bekor qilinadi.

### Reyting

- Reyting joriy kalendar oy va umumiy davr bo'yicha alohida ko'rsatiladi; davr hisobot/so'rovlarning O'zbekiston ish sanasi bo'yicha aniqlanadi.
- Faqat hozirda tasdiqlangan karta so'rovlari hisoblanadi; har bir karta summasiga 3% qo'shilgach, yakuniy qiymat keyingi 1 000 so'mga yuqoriga yaxlitlanadi.
- Faqat tasdiqlangan berilgan summalar va tasdiqlangan hisobotlar hisoblanadi. Hisobot hissasi ilovadagi `Jami topshirilishi kerak` formulasidir.
- Karta (+3%), berilgan summa va hisobot hissasining har 100 000 so'mi +1 ball; joriy qarz qoldig'ining har 100 000 so'mi -1 ball. Qarzdorlik jarimasi oylik va umumiy reytingda aynan hozirgi qoldiqdan olinadi.
- Faol xodimlar admin va xodim web-ilovasida ball, o'rin va tarkibiy summalar bilan ko'rsatiladi. Teng ball olganlar bir xil o'rinni bo'lishadi.

## Texnik yechim taklifi

- **Backend:** Python va FastAPI — bot hamda web-panel foydalanadigan umumiy API.
- **Telegram:** aiogram; lokalda polling, serverda webhook.
- **Ma'lumotlar bazasi:** PostgreSQL. Lokal va production alohida baza/konfiguratsiya bilan ishlaydi.
- **Web-panel:** Telegram Mini App initData orqali superadminni tasdiqlash va ruxsatga asoslangan boshqaruv interfeysi.
- **Ishga tushirish:** Docker Compose orqali lokal muhit; serverda HTTPS. Maxfiy sozlamalar kodga yozilmaydi, muhit o'zgaruvchilaridan olinadi.

Bu texnik tanlovlar dastur tuzilmasini tekshirgandan so'ng mavjud loyiha talablariga moslab tasdiqlanadi.

## Ruxsatlar va xavfsizlik

- Xodimning Telegram Mini App initData imzosi va yangiligi kirishda serverda tekshiriladi; Telegram ID si hamda faol profil holati web-ilovaning har bir tegishli so'rovida tekshiriladi.
- Ishdan bo'shatish xodimga web-ilovaga kirishni darhol to'xtatadi; mavjud sessiya/tokenlar ham bekor qilinadi.
- Superadmin web-panelga Telegram Mini App imzosi bilan kiradi; panelda alohida login/parol yo'q. Cheklangan admin rollari uchun aniq ruxsatlar keyin kelishiladi.
- Web-ilovada xodim faqat o'z ma'lumotlariga kira oladi; boshqa xodimlarning karta raqamlari va so'rovlari xodimlarga ko'rinmaydi. To'liq karta raqami so'rov egasiga web-ilovada va admin guruhida ko'rinadi. Guruh callback'i har amal paytida foydalanuvchining ayni guruhdagi admin/creator maqomini tekshiradi; oddiy a'zolar rad qilinadi. Bu tekshiruv ishonchli bo'lishi uchun bot admin bo'lishi kerak.
- Har bir admin amali, jumladan ishga olish/bo'shatish, qarz o'zgartirish, tasdiqlash va rad etish, kim va qachon bajargani bilan audit qilinadi.
- Telegram bot tokeni, ma'lumotlar bazasi manzili/paroli, admin guruh ID si, maxfiy kalitlar va boshqa maxfiy qiymatlar kodga yozilmaydi. Dastur ularni muhit o'zgaruvchilaridan (environment variables) oladi.
- Haqiqiy qiymatlar saqlanadigan `.env` fayllari `.gitignore` orqali Git'dan chiqariladi. GitHub'ga faqat haqiqiy maxfiy qiymatlari bo'lmagan `.env.example` shabloni yuklanadi; unda `BOT_TOKEN=your_bot_token_here` kabi o'rinbosar qiymatlar bo'ladi.
- Lokal muhitda ishlab chiquvchi o'zining `.env` faylidan, serverda esa serverning maxfiy konfiguratsiyasidan foydalaniladi. `.env.example` dagi o'rinbosarlar ishga tushirishdan oldin haqiqiy maxfiy qiymatlar bilan almashtiriladi, ammo haqiqiy qiymatlar hech qachon repozitoriyga qo'shilmaydi.
- Zaxira nusxalar va ilova qilingan fayllar uchun ham 1 oylik saqlash/o'chirish talabi bajariladigan tartib ishlab chiqiladi.

## Amalga oshirish bosqichlari

1. Repozitoriy va mavjud muhitni tekshirish; lokal/server konfiguratsiyasini belgilash.
2. Ma'lumotlar modeli, migratsiyalar, rollar va audit izini yaratish.
3. Admin autentifikatsiyasi, xodimni Telegram ID orqali web-panelda bog'lash va darhol bloklashni amalga oshirish.
4. Xodim va admin uchun barcha ish amallarini web-ilovada yaratish; botni ID ko'rsatish va bildirishnomalar bilan cheklash.
5. Karta so'rovlari, pul summalari va qarzdorlik jarayonlarini hamda qaror tarixlarini qo'shish.
6. Rasmga mos kunlik hisobot formasini, avtomatik maydonlarni va tasdiqlash/rad etishni yaratish.
7. Web-panelda xodimlar, qarzdorlik, navbatdagi so'rovlar, hisobotlar va tarixlarni ko'rsatish.
8. Reytingni joriy oy va umumiy davr bo'yicha hisoblash va ko'rsatish.
9. Lokal sinovlar, ruxsat va o'chirish muddatlarini tekshirish; so'ng production serverga HTTPS va alohida baza bilan joylash.

## Qabul mezonlari

- Xodim faqat Telegram Mini App orqali, Telegram imzosi tekshirilib, Telegram ID si faol profilga mos bo'lganda web-ilovaga kira oladi.
- Ishdan bo'shatilgan xodim yangi amal bajara olmaydi; 1 oydan so'ng uning belgilangan shaxsiy/ish ma'lumotlari o'chadi.
- Xodim web-ilovada karta to'ldirish so'rovi, pul summasi va kunlik hisobot yubora oladi; o'z qarorlari tarixini ko'ra oladi.
- Adminlar web-ilovada ruxsatlari doirasida xodimlar, qarzdorliklar va hisobotlarni boshqaradi; karta so'rovini web-ilovada yoki admin guruhidagi tasdiqlangan tugmalar orqali ko'rib chiqadi.
- `Card (+3%)` tasdiqlangan karta to'ldirishlardan 3% ustama bilan hisoblanadi.
- `Berildi (Tasdiqlangan)` faqat shu kun uchun tasdiqlangan xodim summalarini jamlaydi.
- `Qarz uchun` qarzdorlikni faqat tegishli hisobot tasdiqlanganda kamaytiradi.
- Reyting faqat tasdiqlangan kartalar, berilgan summalar va hisobotlardan ball to'playdi; joriy qarz qoldig'i oylik va umumiy reytingdan ayriladi.
- Kunlik hisobot alohida Telegram guruhiga yuboriladi; shu sana uchun takror yuborilganda eski guruh xabari o'chirilib yangisi yuboriladi.
- Lokal va production muhitlari bir-birining ma'lumotlar bazasiga ulanmaydi.

## Keyin aniqlanadigan qarorlar

- Cheklangan admin rollarining aniq huquqlari.
- O'tkazib yuborilgan kunlar uchun hisobot topshirish muddati va cheklovlari.
- 1 oylik o'chirishda qaysi audit metama'lumotlari saqlanishi va zaxiralardan o'chirishning texnik muddati.
- Hisobotdagi pul maydonlari uchun manfiy qiymat, maksimal qiymat va tuzatish talablar.
