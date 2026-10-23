from contextlib import asynccontextmanager
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field, field_validator

from app.config import get_settings
from app.bot import (
    card_decision_keyboard,
    card_notification_text,
    report_notification_text,
)
from app.employees import (
    Employee,
    dismiss_employee,
    get_active_employee,
    initialize_database,
    list_active_employees,
    register_employee,
)
from app.telegram_auth import (
    create_employee_session,
    validate_employee_session,
    validate_telegram_init_data,
)
from app.workflows import (
    add_debt,
    admin_dashboard,
    create_card_request,
    create_money_giving,
    create_report,
    daily_report,
    employee_dashboard,
    initialize_workflows,
    card_request,
    save_card_notification,
    save_report_notification,
    set_card_request_decision,
    review_money_giving,
    review_report,
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    initialize_database(settings.employee_db_path)
    initialize_workflows(settings.employee_db_path)
    yield


app = FastAPI(title="Hisobot Bot", version="0.1.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=500)
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def cache_versioned_static_assets(request: Request, call_next):
    response = await call_next(request)
    if request.method == "GET" and request.url.path.startswith("/static/") and request.query_params.get("v"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


class EmployeeCreate(BaseModel):
    telegram_id: int = Field(gt=0)
    bot_name: str = Field(min_length=1, max_length=100)

    @field_validator("bot_name")
    @classmethod
    def strip_bot_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Employee name cannot be blank")
        return cleaned


class TelegramLogin(BaseModel):
    init_data: str = Field(min_length=1, max_length=10_000)


class CardRequestCreate(BaseModel):
    card_number: str = Field(pattern=r"^[0-9]{16}$")
    cardholder: str = Field(min_length=1, max_length=120)
    amount: int = Field(ge=10_000, le=1_000_000_000)

    @field_validator("card_number", mode="before")
    @classmethod
    def normalize_card_number(cls, value: object) -> object:
        if isinstance(value, str):
            return value.replace(" ", "")
        return value

    @field_validator("cardholder")
    @classmethod
    def strip_cardholder(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned or any(not (character.isalpha() or character == " ") for character in cleaned):
            raise ValueError("Karta egasining ismi faqat harflardan iborat bo'lishi kerak")
        return cleaned

    @field_validator("amount", mode="before")
    @classmethod
    def normalize_amount(cls, value: object) -> object:
        if isinstance(value, str):
            digits = value.replace(" ", "")
            if not digits.isascii() or not digits.isdigit():
                raise ValueError("Summa faqat raqamlardan iborat bo'lishi kerak")
            return int(digits)
        return value


class MoneyGivingCreate(BaseModel):
    amount: int = Field(gt=0, le=1_000_000_000)
    note: str = Field(default="", max_length=500)


class DailyReportCreate(BaseModel):
    work_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    paynet: int = Field(ge=0, le=1_000_000_000)
    levy: int = Field(ge=0, le=1_000_000_000)
    simcard: int = Field(ge=0, le=1_000_000)
    debt_payment: int = Field(ge=0, le=1_000_000_000)
    terminal: int = Field(ge=0, le=1_000_000_000)
    daily: int = Field(ge=0, le=1_000_000_000)
    discount: int = Field(ge=0, le=1_000_000_000)
    expense: int = Field(ge=0, le=1_000_000_000)
    comment: str = Field(default="", max_length=1000)


class DebtCreate(BaseModel):
    amount: int = Field(gt=0, le=1_000_000_000)
    description: str = Field(min_length=1, max_length=500)

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Qarz sababi kiritilishi kerak")
        return cleaned


class WorkflowDecision(BaseModel):
    approved: bool
    reason: str = Field(default="", max_length=1000)


def get_current_employee(request: Request) -> Employee:
    settings = get_settings()
    token = request.cookies.get("employee_session")
    if token is None:
        raise HTTPException(status_code=401, detail="Telegram orqali qayta kiring")
    telegram_id = validate_employee_session(
        token,
        settings.secret_key.get_secret_value(),
    )
    if telegram_id is None:
        raise HTTPException(status_code=401, detail="Sessiya yaroqsiz yoki muddati tugagan")
    employee = get_active_employee(settings.employee_db_path, telegram_id)
    if employee is None:
        raise HTTPException(status_code=403, detail="Xodim profili faol emas")
    return employee


def require_admin(request: Request) -> None:
    settings = get_settings()
    token = request.cookies.get("admin_session")
    if token is None:
        raise HTTPException(status_code=401, detail="Admin Telegram sessiyasi kerak")
    telegram_id = validate_employee_session(
        token,
        settings.secret_key.get_secret_value(),
    )
    if telegram_id != settings.superadmin_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin ruxsati talab qilinadi",
        )
    if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get(
        "x-requested-with"
    ) != "XMLHttpRequest":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="So'rov web-ilova orqali yuborilishi kerak",
        )


async def admin_panel() -> str:
    return """<!doctype html>
<html lang="uz">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <title>Hisobot Bot — Admin</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, Segoe UI, sans-serif; }
    body { margin: 0; background: #101827; color: #e5edf7; }
    main { width: min(900px, calc(100% - 32px)); margin: 42px auto; }
    h1 { margin-bottom: 8px; } .muted { color: #9aa9bd; }
    section { margin-top: 24px; padding: 24px; border: 1px solid #2b394d;
      border-radius: 14px; background: #182335; }
    form { display: grid; grid-template-columns: 1fr 2fr auto; gap: 12px; }
    input, button { box-sizing: border-box; border-radius: 8px; padding: 12px;
      font: inherit; }
    input { min-width: 0; color: #e5edf7; background: #101827; border: 1px solid #35445b; }
    button { cursor: pointer; color: white; border: 0; background: #1687ed; }
    button.danger { background: #b93845; padding: 8px 12px; }
    .employee { display: flex; align-items: center; justify-content: space-between;
      gap: 16px; padding: 14px 0; border-bottom: 1px solid #2b394d; }
    .employee:last-child { border-bottom: 0; }
    #message { min-height: 1.4em; color: #8ddba7; }
    @media (max-width: 640px) { form { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<main>
  <h1>Hisobot Bot</h1>
  <div id="auth-status" class="muted">Telegram akkauntingiz tekshirilmoqda...</div>
  <section>
    <h2>Xodim qo'shish</h2>
    <form id="add-form">
      <input name="telegram_id" type="number" min="1" placeholder="Telegram ID" required disabled>
      <input name="bot_name" maxlength="100" placeholder="Bot taniydigan ism" required disabled>
      <button type="submit" disabled>Xodimni qo'shish</button>
    </form>
    <p id="message" role="status"></p>
  </section>
  <section>
    <h2>Faol xodimlar</h2>
    <div id="employees" class="muted">Telegram tasdiqlovi kutilmoqda...</div>
  </section>
</main>
<script>
const message = document.querySelector("#message");
const list = document.querySelector("#employees");
const authStatus = document.querySelector("#auth-status");
const adminControls = document.querySelectorAll("#add-form input, #add-form button");

async function loadEmployees() {
  const response = await fetch("/admin/api/employees");
  if (!response.ok) throw new Error("Xodimlar ro'yxatini yuklab bo'lmadi.");
  const employees = await response.json();
  list.replaceChildren();
  if (employees.length === 0) {
    list.textContent = "Hozircha faol xodimlar yo'q.";
    return;
  }
  for (const employee of employees) {
    const row = document.createElement("div");
    row.className = "employee";
    const info = document.createElement("span");
    info.textContent = `${employee.bot_name} · Telegram ID: ${employee.telegram_id}`;
    const dismiss = document.createElement("button");
    dismiss.className = "danger";
    dismiss.textContent = "Ishdan bo'shatish";
    dismiss.addEventListener("click", async () => {
      if (!confirm(`${employee.bot_name} ishdan bo'shatilsinmi?`)) return;
      const result = await fetch(`/admin/api/employees/${employee.telegram_id}/dismiss`, {
        method: "POST",
        headers: { "X-Requested-With": "XMLHttpRequest" }
      });
      if (!result.ok) {
        message.textContent = "Xodimni ishdan bo'shatib bo'lmadi.";
        return;
      }
      message.textContent = "Xodimning botga kirishi bloklandi.";
      await loadEmployees();
    });
    row.append(info, dismiss);
    list.append(row);
  }
}

document.querySelector("#add-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const response = await fetch("/admin/api/employees", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "XMLHttpRequest"
    },
    body: JSON.stringify({
      telegram_id: Number(form.get("telegram_id")),
      bot_name: form.get("bot_name")
    })
  });
  if (!response.ok) {
    const error = await response.json();
    message.textContent = error.detail || "Xodimni qo'shib bo'lmadi.";
    return;
  }
  message.textContent = "Xodim qo'shildi.";
  event.currentTarget.reset();
  await loadEmployees();
});

async function signInAdmin() {
  const telegram = window.Telegram?.WebApp;
  if (!telegram || !telegram.initData) {
    authStatus.textContent = "Admin panelga kirish uchun uni Telegram bot tugmasidan oching.";
    list.textContent = "Telegram Mini App orqali ochilmagan.";
    return;
  }
  telegram.ready();
  telegram.expand();
  const response = await fetch("/auth/telegram", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ init_data: telegram.initData })
  });
  const result = await response.json();
  if (!response.ok || result.role !== "admin") {
    authStatus.textContent = result.detail || "Bu Telegram akkauntida admin huquqi yo'q.";
    list.textContent = "Superadmin akkaunti bilan Telegram botdan oching.";
    return;
  }
  for (const control of adminControls) control.disabled = false;
  authStatus.textContent = "Superadmin sifatida Telegram orqali tasdiqlandingiz.";
  await loadEmployees();
}

signInAdmin().catch(() => {
  authStatus.textContent = "Kirish vaqtida xatolik yuz berdi.";
  list.textContent = "Internetni tekshirib, web-ilovani qayta oching.";
});
</script>
</body>
</html>"""


@app.get("/admin/api/employees", dependencies=[Depends(require_admin)])
async def admin_employees() -> list[dict[str, int | str]]:
    settings = get_settings()
    return [
        {"telegram_id": employee.telegram_id, "bot_name": employee.bot_name}
        for employee in list_active_employees(settings.employee_db_path)
    ]


@app.post("/admin/api/employees", dependencies=[Depends(require_admin)])
async def admin_add_employee(employee: EmployeeCreate) -> dict[str, str]:
    settings = get_settings()
    if employee.telegram_id == settings.superadmin_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Superadmin ID xodim ID si sifatida ishlatilmaydi",
        )
    result = register_employee(
        settings.employee_db_path,
        employee.telegram_id,
        employee.bot_name,
        settings.superadmin_id,
    )
    return {"status": result}


@app.post(
    "/admin/api/employees/{telegram_id}/dismiss",
    dependencies=[Depends(require_admin)],
)
async def admin_dismiss_employee(telegram_id: int) -> dict[str, str]:
    settings = get_settings()
    if not dismiss_employee(
        settings.employee_db_path,
        telegram_id,
        get_settings().superadmin_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Faol xodim topilmadi",
        )
    return {"status": "dismissed"}


def _workflow_error(error: ValueError) -> HTTPException:
    return HTTPException(status_code=409, detail=str(error))


def _admin_workflow_row(collection: str, record_id: int) -> dict[str, object]:
    records = admin_dashboard(get_settings().employee_db_path)[collection]
    for record in records:
        if record.get("id") == record_id:
            return record
    raise HTTPException(status_code=404, detail="Yozuv topilmadi")


@app.get("/employee/api/dashboard")
async def employee_workflow_dashboard(
    work_date: str | None = None,
    employee: Employee = Depends(get_current_employee),
) -> dict[str, object]:
    settings = get_settings()
    try:
        return employee_dashboard(settings.employee_db_path, employee.telegram_id, work_date)
    except ValueError as error:
        raise _workflow_error(error) from error


@app.post("/employee/api/cards")
async def employee_create_card_request(
    payload: CardRequestCreate,
    employee: Employee = Depends(get_current_employee),
) -> dict[str, object]:
    settings = get_settings()
    try:
        request_id = create_card_request(
            settings.employee_db_path,
            employee.telegram_id,
            payload.card_number,
            payload.cardholder,
            payload.amount,
        )
    except ValueError as error:
        raise _workflow_error(error) from error

    warning = None
    saved_request = card_request(settings.employee_db_path, request_id)
    if saved_request is None:
        raise HTTPException(status_code=500, detail="Saqlangan karta so'rovi topilmadi")
    try:
        async with Bot(token=settings.bot_token.get_secret_value()) as bot:
            sent_message = await bot.send_message(
                chat_id=settings.admin_group_id,
                text=card_notification_text(saved_request),
                reply_markup=card_decision_keyboard(request_id, "pending"),
            )
    except (TelegramAPIError, OSError, TimeoutError):
        logger.exception("Karta so'rovi #%s saqlandi, ammo Telegram xabari yuborilmadi", request_id)
        warning = "So'rov saqlandi, lekin admin guruhiga xabar yuborilmadi."
    else:
        save_card_notification(
            settings.employee_db_path,
            request_id,
            settings.admin_group_id,
            sent_message.message_id,
        )
    result: dict[str, object] = {"id": request_id, "status": "pending"}
    if warning is not None:
        result["notification_warning"] = warning
    return result


@app.post("/employee/api/givings")
async def employee_create_money_giving(
    payload: MoneyGivingCreate,
    employee: Employee = Depends(get_current_employee),
) -> dict[str, object]:
    settings = get_settings()
    try:
        giving_id = create_money_giving(
            settings.employee_db_path, employee.telegram_id, payload.amount, payload.note
        )
    except ValueError as error:
        raise _workflow_error(error) from error
    return {"id": giving_id, "status": "pending"}


@app.post("/employee/api/reports")
async def employee_create_daily_report(
    payload: DailyReportCreate,
    employee: Employee = Depends(get_current_employee),
) -> dict[str, object]:
    settings = get_settings()
    previous_report = daily_report(
        settings.employee_db_path,
        employee.telegram_id,
        payload.work_date,
    )
    try:
        report_id = create_report(
            settings.employee_db_path,
            employee.telegram_id,
            payload.model_dump(),
        )
    except ValueError as error:
        raise _workflow_error(error) from error
    saved_report = daily_report(
        settings.employee_db_path,
        employee.telegram_id,
        payload.work_date,
    )
    if saved_report is None:
        raise HTTPException(status_code=500, detail="Saqlangan hisobot topilmadi")

    warnings: list[str] = []
    async with Bot(token=settings.bot_token.get_secret_value()) as bot:
        if (
            previous_report is not None
            and previous_report["notification_chat_id"] is not None
            and previous_report["notification_message_id"] is not None
        ):
            try:
                await bot.delete_message(
                    chat_id=int(previous_report["notification_chat_id"]),
                    message_id=int(previous_report["notification_message_id"]),
                )
            except (TelegramAPIError, OSError, TimeoutError):
                logger.exception(
                    "Hisobot #%s yangilandi, ammo guruhdagi eski xabar o'chirilmadi",
                    previous_report["id"],
                )
                warnings.append("Guruhdagi eski hisobot xabari o'chirilmadi.")

        try:
            sent_message = await bot.send_message(
                chat_id=settings.report_group_id,
                text=report_notification_text(saved_report),
            )
        except (TelegramAPIError, OSError, TimeoutError):
            logger.exception(
                "Hisobot #%s saqlandi, ammo hisobot guruhiga xabar yuborilmadi",
                report_id,
            )
            warnings.append("Hisobot saqlandi, lekin hisobot guruhiga xabar yuborilmadi.")
        else:
            save_report_notification(
                settings.employee_db_path,
                report_id,
                settings.report_group_id,
                sent_message.message_id,
            )

    result: dict[str, object] = {"id": report_id, "status": "pending"}
    if warnings:
        result["notification_warning"] = " ".join(warnings)
    return result


@app.get("/admin/api/workflows", dependencies=[Depends(require_admin)])
async def admin_workflow_dashboard() -> dict[str, object]:
    settings = get_settings()
    result = admin_dashboard(settings.employee_db_path)
    result.pop("cards", None)
    result.pop("audit", None)
    result["employees"] = [
        {"telegram_id": employee.telegram_id, "bot_name": employee.bot_name}
        for employee in list_active_employees(settings.employee_db_path)
    ]
    return result


@app.post(
    "/admin/api/employees/{telegram_id}/debt",
    dependencies=[Depends(require_admin)],
)
async def admin_add_employee_debt(telegram_id: int, payload: DebtCreate) -> dict[str, object]:
    settings = get_settings()
    employee = get_active_employee(settings.employee_db_path, telegram_id)
    if employee is None:
        raise HTTPException(status_code=404, detail="Faol xodim topilmadi")
    try:
        debt_id = add_debt(
            settings.employee_db_path,
            telegram_id,
            payload.amount,
            payload.description,
            settings.superadmin_id,
        )
    except ValueError as error:
        raise _workflow_error(error) from error
    return {"id": debt_id, "status": "recorded"}


@app.post(
    "/admin/api/cards/{record_id}/decision",
    dependencies=[Depends(require_admin)],
)
async def admin_decide_card(record_id: int, payload: WorkflowDecision) -> dict[str, str]:
    settings = get_settings()
    record = card_request(settings.employee_db_path, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Karta so'rovi topilmadi")
    if not payload.approved and not payload.reason.strip():
        raise HTTPException(status_code=422, detail="Rad etish sababi kiritilishi shart")
    try:
        decision = set_card_request_decision(
            settings.employee_db_path,
            record_id,
            payload.approved,
            settings.superadmin_id,
            payload.reason,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise _workflow_error(error) from error
    updated_record = card_request(settings.employee_db_path, record_id)
    result: dict[str, str] = {"status": decision}
    if updated_record is not None and updated_record["notification_message_id"] is not None:
        try:
            async with Bot(token=settings.bot_token.get_secret_value()) as bot:
                await bot.edit_message_text(
                    chat_id=int(updated_record["notification_chat_id"]),
                    message_id=int(updated_record["notification_message_id"]),
                    text=card_notification_text(updated_record),
                    reply_markup=card_decision_keyboard(record_id, decision),
                )
        except (TelegramAPIError, OSError, TimeoutError):
            logger.exception("Karta so'rovi #%s qarori saqlandi, ammo guruh xabari yangilanmadi", record_id)
            result["notification_warning"] = "Qaror saqlandi, lekin guruh xabari yangilanmadi."
    return result


@app.post(
    "/admin/api/givings/{record_id}/decision",
    dependencies=[Depends(require_admin)],
)
async def admin_decide_giving(record_id: int, payload: WorkflowDecision) -> dict[str, str]:
    settings = get_settings()
    record = _admin_workflow_row("givings", record_id)
    try:
        review_money_giving(
            settings.employee_db_path,
            record_id,
            int(record["employee_id"]),
            payload.approved,
            payload.reason,
            settings.superadmin_id,
        )
    except ValueError as error:
        raise _workflow_error(error) from error
    return {"status": "approved" if payload.approved else "rejected"}


@app.post(
    "/admin/api/reports/{record_id}/decision",
    dependencies=[Depends(require_admin)],
)
async def admin_decide_report(record_id: int, payload: WorkflowDecision) -> dict[str, str]:
    settings = get_settings()
    try:
        review_report(
            settings.employee_db_path,
            record_id,
            payload.approved,
            payload.reason,
            settings.superadmin_id,
        )
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise _workflow_error(error) from error
    return {"status": "approved" if payload.approved else "rejected"}


async def employee_app() -> str:
    return """<!doctype html>
<html lang="uz">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <title>Hisobot Bot — Xodim</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, Segoe UI, sans-serif; }
    body { margin: 0; background: #101827; color: #e5edf7; }
    main { width: min(640px, calc(100% - 32px)); margin: 32px auto; }
    section { margin-top: 20px; padding: 24px; border: 1px solid #2b394d;
      border-radius: 14px; background: #182335; }
    .muted { color: #9aa9bd; } #status { min-height: 1.5em; }
  </style>
</head>
<body>
<main>
  <h1>Hisobot Bot</h1>
  <p class="muted">Xodimlar web-ilovasi</p>
  <section>
    <h2 id="greeting">Tekshirilmoqda...</h2>
    <p id="status" class="muted">Telegram akkauntingiz tasdiqlanmoqda.</p>
  </section>
</main>
<script>
const greeting = document.querySelector("#greeting");
const status = document.querySelector("#status");
const telegram = window.Telegram?.WebApp;

async function signIn() {
  if (!telegram || !telegram.initData) {
    greeting.textContent = "Telegram orqali oching";
    status.textContent = "Botdagi Web-ilovani ochish tugmasidan foydalaning.";
    return;
  }
  telegram.ready();
  telegram.expand();
  const response = await fetch("/auth/telegram", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ init_data: telegram.initData })
  });
  const result = await response.json();
  if (!response.ok) {
    greeting.textContent = "Kirish amalga oshmadi";
    status.textContent = result.detail || "Admin bilan bog'laning.";
    return;
  }
  const profile = await fetch("/employee/api/me", { credentials: "same-origin" });
  if (!profile.ok) {
    greeting.textContent = "Sessiyani tasdiqlab bo'lmadi";
    status.textContent = "Ilovani qayta oching yoki admin bilan bog'laning.";
    return;
  }
  const employee = await profile.json();
  greeting.textContent = `Assalomu alaykum, ${employee.bot_name}!`;
  status.textContent = "Akkauntingiz tasdiqlandi. Hisobot va so'rovlar web-ilovada bajariladi.";
}

signIn().catch(() => {
  greeting.textContent = "Ulanishda xatolik";
  status.textContent = "Internetni tekshirib, ilovani qayta oching.";
});
</script>
</body>
</html>"""


@app.get("/", include_in_schema=False)
async def admin_static_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/employee", include_in_schema=False)
async def employee_static_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "employee.html")


@app.post("/auth/telegram")
async def telegram_employee_login(
    login: TelegramLogin,
    response: Response,
) -> dict[str, str]:
    settings = get_settings()
    try:
        telegram_user = validate_telegram_init_data(
            login.init_data,
            settings.bot_token.get_secret_value(),
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Telegram tasdiqlovi yaroqsiz yoki muddati o'tgan",
        ) from error

    telegram_id = telegram_user["id"]
    if telegram_id == settings.superadmin_id:
        cookie_name = "admin_session"
        role = "admin"
    else:
        employee = get_active_employee(settings.employee_db_path, telegram_id)
        if employee is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Profil faol xodim sifatida ro'yxatdan o'tmagan",
            )
        cookie_name = "employee_session"
        role = "employee"

    response.set_cookie(
        key=cookie_name,
        value=create_employee_session(
            telegram_id,
            settings.secret_key.get_secret_value(),
        ),
        max_age=43_200,
        httponly=True,
        secure=settings.app_env == "production",
        samesite="strict",
        path="/",
    )
    return {"status": "authenticated", "role": role}


@app.get("/employee/api/me")
async def employee_profile(
    employee: Employee = Depends(get_current_employee),
) -> dict[str, int | str]:
    return {"telegram_id": employee.telegram_id, "bot_name": employee.bot_name}


@app.post("/auth/logout")
async def employee_logout(
    response: Response,
    _: Employee = Depends(get_current_employee),
) -> dict[str, str]:
    response.delete_cookie(
        key="employee_session",
        httponly=True,
        secure=get_settings().app_env == "production",
        samesite="strict",
        path="/",
    )
    return {"status": "logged_out"}


@app.get("/health", tags=["operations"])
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
