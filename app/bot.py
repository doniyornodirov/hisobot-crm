import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonDefault,
    MenuButtonWebApp,
    Message,
    WebAppInfo,
)

from app.config import get_settings
from app.employees import get_active_employee, initialize_database
from app.workflows import (
    card_request,
    initialize_workflows,
    set_card_request_decision,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def card_notification_text(request: dict[str, object]) -> str:
    statuses = {
        "pending": "⏳ Kutilmoqda",
        "approved": "✅ Tasdiqlandi",
        "rejected": "❌ Rad etildi",
    }
    employee_name = request.get("bot_name") or request["employee_id"]
    amount = f"{int(request['amount']):,}".replace(",", " ")
    same_day_count = int(request.get("same_day_count", 1))
    repeat_card_warning = (
        "\n⚠️ DIQQAT: Bugun bu kartaga to'lov qilindi. ❌❌❌"
        if same_day_count > 1
        else ""
    )
    return (
        "💳 Yangi karta to'ldirish so'rovi\n"
        f"👤 Xodim: {employee_name}\n"
        f"💳 Karta: {request['card_number']}\n"
        f"🪪 Ega: {request['cardholder']}\n"
        f"💰 Summa: {amount} so'm\n"
        f"📌 Status: {statuses[str(request['status'])]}"
        f"{repeat_card_warning}"
    )


def report_notification_text(report: dict[str, object]) -> str:
    def amount(field: str) -> str:
        return f"{int(report[field]):,}".replace(",", " ")

    total = (
        int(report["paynet"])
        + int(report["card_total"])
        + int(report["levy"])
        + int(report["daily"])
        - int(report["terminal"])
        - int(report["giving_total"])
        - int(report["discount"])
        - int(report["expense"])
        + int(report["debt_payment"])
    )
    employee_name = report.get("bot_name") or report["employee_id"]
    lines = [
        "📋 Yangi kunlik hisobot",
        f"👤 Xodim: {employee_name}",
        f"📅 Sana: {report['work_date']}",
        f"💳 Paynet: {amount('paynet')} so'm",
        f"💳 Card (+3%): {amount('card_total')} so'm",
        f"🏷️ Levy: {amount('levy')} so'm",
        f"📱 SIMcard: {report['simcard']} dona",
        f"💸 Qarz uchun: {amount('debt_payment')} so'm",
        f"✅ Berildi (tasdiqlangan): {amount('giving_total')} so'm",
        f"🏧 Terminal: {amount('terminal')} so'm",
        f"☀️ Kunlik: {amount('daily')} so'm",
        f"🏷️ Skidka: {amount('discount')} so'm",
        f"🧾 Xarajat: {amount('expense')} so'm",
        f"📦 Jami topshirilishi kerak: {total:,}".replace(",", " ") + " so'm",
    ]
    comment = str(report["comment"]).strip()
    if comment:
        lines.append(f"📝 Izoh: {comment}")
    return "\n".join(lines)


def card_decision_keyboard(
    request_id: int,
    decision: str,
) -> InlineKeyboardMarkup:
    if decision == "approved":
        buttons = [
            InlineKeyboardButton(
                text="❌ Rad etish",
                callback_data=f"card:{request_id}:reject",
            )
        ]
    elif decision == "rejected":
        buttons = [
            InlineKeyboardButton(
                text="✅ Tasdiqlash",
                callback_data=f"card:{request_id}:approve",
            )
        ]
    else:
        buttons = [
            InlineKeyboardButton(
                text="✅ Tasdiqlash",
                callback_data=f"card:{request_id}:approve",
            ),
            InlineKeyboardButton(
                text="❌ Rad etish",
                callback_data=f"card:{request_id}:reject",
            ),
        ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


async def card_request_decision(callback: CallbackQuery, bot: Bot) -> None:
    settings = get_settings()
    message = callback.message
    if (
        message is None
        or not callable(getattr(message, "edit_text", None))
        or message.chat.id != settings.admin_group_id
        or not callback.data
        or callback.from_user is None
    ):
        await callback.answer("Bu so'rovni bu guruhda bajarib bo'lmaydi.", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) != 3 or parts[0] != "card" or parts[2] not in {"approve", "reject"}:
        await callback.answer("So'rov tugmasi yaroqsiz.", show_alert=True)
        return
    try:
        request_id = int(parts[1])
    except ValueError:
        await callback.answer("So'rov tugmasi yaroqsiz.", show_alert=True)
        return

    try:
        member = await bot.get_chat_member(
            chat_id=settings.admin_group_id,
            user_id=callback.from_user.id,
        )
    except TelegramAPIError:
        logger.exception(
            "Guruhdagi %s foydalanuvchining admin huquqini tekshirib bo'lmadi",
            callback.from_user.id,
        )
        await callback.answer(
            "Admin huquqini tekshirib bo'lmadi. Botni guruhga admin qiling.",
            show_alert=True,
        )
        return
    if member.status not in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}:
        await callback.answer("Qarorni faqat guruh adminlari o'zgartira oladi.", show_alert=True)
        return

    request = card_request(settings.employee_db_path, request_id)
    if request is None:
        await callback.answer("Karta so'rovi topilmadi.", show_alert=True)
        return
    approved = parts[2] == "approve"
    target_status = "approved" if approved else "rejected"
    if request["status"] == target_status:
        await callback.answer(
            f"So'rov allaqachon {'tasdiqlangan' if approved else 'rad etilgan'}.",
            show_alert=True,
        )
        return

    try:
        set_card_request_decision(
            settings.employee_db_path,
            request_id,
            approved,
            callback.from_user.id,
        )
        updated_request = card_request(settings.employee_db_path, request_id)
        if updated_request is None:
            raise LookupError("Karta so'rovi topilmadi")
        await message.edit_text(
            card_notification_text(updated_request),
            reply_markup=card_decision_keyboard(request_id, target_status),
        )
    except (LookupError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    except TelegramAPIError:
        logger.exception(
            "Karta so'rovi #%s qarori saqlandi, ammo guruh xabari yangilanmadi",
            request_id,
        )
        await callback.answer(
            "Qaror saqlandi, ammo xabarni yangilab bo'lmadi.",
            show_alert=True,
        )
        return

    await callback.answer("Qaror saqlandi.")


async def start_command(message: Message) -> None:
    user = message.from_user
    if user is None or message.chat.type != "private":
        return

    settings = get_settings()
    if user.id == settings.superadmin_id:
        if settings.web_app_url:
            admin_panel_url = settings.web_app_url.removesuffix("/employee") + "/"
            menu_button = MenuButtonWebApp(
                text="Admin panel",
                web_app=WebAppInfo(url=admin_panel_url),
            )
        else:
            menu_button = MenuButtonDefault()
        await message.bot.set_chat_menu_button(
            chat_id=user.id,
            menu_button=menu_button,
        )
        await message.answer(
            "Assalomu alaykum, superadmin. Admin panelni chat pastidagi "
            "\"Admin panel\" tugmasidan oching."
        )
        return

    employee = get_active_employee(settings.employee_db_path, user.id)
    if employee is None:
        await message.bot.set_chat_menu_button(
            chat_id=user.id,
            menu_button=MenuButtonDefault(),
        )
        await message.answer(
            "Ro'yxatdan o'tish uchun Telegram ID raqamingizni superadminga yuboring:\n"
            f"{user.id}\n\n"
            "Superadmin sizni web-panelda ro'yxatdan o'tkazgach, qayta /start yuboring."
        )
        return

    if settings.web_app_url:
        menu_button = MenuButtonWebApp(
            text="Hisobot",
            web_app=WebAppInfo(url=settings.web_app_url),
        )
    else:
        menu_button = MenuButtonDefault()
    await message.bot.set_chat_menu_button(
        chat_id=user.id,
        menu_button=menu_button,
    )

    await message.answer(
        f"Assalomu alaykum, {employee.bot_name}! Siz ro'yxatdan o'tgansiz.\n"
        "Hisobot va boshqa ishlar chat pastidagi \"Hisobot\" tugmasida."
    )


async def main() -> None:
    settings = get_settings()
    initialize_database(settings.employee_db_path)
    initialize_workflows(settings.employee_db_path)
    dispatcher = Dispatcher()
    dispatcher.message.register(start_command, CommandStart())
    dispatcher.callback_query.register(card_request_decision, F.data.startswith("card:"))

    async with Bot(token=settings.bot_token.get_secret_value()) as bot:
        logger.info("Starting Telegram bot polling (superadmin ID: %s)", settings.superadmin_id)
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )


if __name__ == "__main__":
    asyncio.run(main())
