import tempfile
import unittest
from http.cookies import SimpleCookie
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import Response
from starlette.requests import Request

from app.employees import initialize_database, register_employee, get_active_employee
from app.main import (
    EmployeePinUpdate,
    WebLoginRequest,
    crm_dashboard_data,
    crm_employees_list,
    crm_get_current_user,
    crm_logout,
    crm_static_page,
    crm_update_employee_pin,
    crm_web_login,
)
from app.workflows import initialize_workflows, create_card_request, create_money_giving


class CRMWebsiteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "employees.sqlite3"
        initialize_database(self.database_path)
        initialize_workflows(self.database_path)
        self.bot_token = "test-bot-token"
        self.secret_key = "a-test-secret-key-that-is-long-enough-32-chars"
        self.settings = SimpleNamespace(
            bot_token=SimpleNamespace(get_secret_value=lambda: self.bot_token),
            superadmin_id=99999,
            admin_username="admin",
            admin_password="admin123",
            secret_key=SimpleNamespace(get_secret_value=lambda: self.secret_key),
            employee_db_path=self.database_path,
            report_group_id=-5578176162,
            admin_group_id=-1001234567,
            app_env="test",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_crm_static_page_serves_crm_html(self) -> None:
        response = await crm_static_page()
        self.assertTrue(Path(response.path).is_file())
        content = Path(response.path).read_text(encoding="utf-8")
        self.assertIn("HISOBOT CRM", content)
        self.assertIn("/static/crm.css", content)
        self.assertIn("/static/crm.js", content)
        self.assertIn("id=\"auth-screen\"", content)
        self.assertIn("id=\"app-container\"", content)

    async def test_crm_employees_list_endpoint(self) -> None:
        register_employee(self.database_path, 101, "Ali Valiyev", pin="1111")
        register_employee(self.database_path, 102, "Vali Aliyev", pin="2222")

        with patch("app.main.get_settings", return_value=self.settings):
            employees = await crm_employees_list()

        self.assertEqual(len(employees), 2)
        names = [e["bot_name"] for e in employees]
        self.assertIn("Ali Valiyev", names)
        self.assertIn("Vali Aliyev", names)

    async def test_crm_admin_login_success_and_failure(self) -> None:
        with patch("app.main.get_settings", return_value=self.settings):
            # Success
            response = Response()
            res = await crm_web_login(
                WebLoginRequest(role="admin", username="admin", password="admin123"),
                response,
            )
            self.assertEqual(res["status"], "authenticated")
            self.assertEqual(res["role"], "admin")
            self.assertIn("set-cookie", response.headers)
            self.assertIn("admin_session", response.headers["set-cookie"])

            # Failure
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx:
                await crm_web_login(
                    WebLoginRequest(role="admin", username="admin", password="wrongpassword"),
                    Response(),
                )
            self.assertEqual(ctx.exception.status_code, 401)

    async def test_crm_employee_login_success_and_failure(self) -> None:
        register_employee(self.database_path, 201, "Bobur", pin="4321")

        with patch("app.main.get_settings", return_value=self.settings):
            # Success with correct PIN
            response = Response()
            res = await crm_web_login(
                WebLoginRequest(role="employee", employee_id=201, pin="4321"),
                response,
            )
            self.assertEqual(res["status"], "authenticated")
            self.assertEqual(res["role"], "employee")
            self.assertEqual(res["user"]["name"], "Bobur")
            self.assertIn("set-cookie", response.headers)
            self.assertIn("employee_session", response.headers["set-cookie"])

            # Failure with wrong PIN
            from fastapi import HTTPException
            with self.assertRaises(HTTPException) as ctx:
                await crm_web_login(
                    WebLoginRequest(role="employee", employee_id=201, pin="9999"),
                    Response(),
                )
            self.assertEqual(ctx.exception.status_code, 401)

    async def test_crm_me_and_logout(self) -> None:
        register_employee(self.database_path, 301, "Jasur", pin="1234")

        with patch("app.main.get_settings", return_value=self.settings):
            # Unauthenticated check
            empty_req = Request({"type": "http", "method": "GET", "path": "/crm/api/me", "headers": []})
            me = await crm_get_current_user(empty_req)
            self.assertFalse(me["authenticated"])
            self.assertEqual(me["role"], "guest")

            # Login as employee
            login_resp = Response()
            await crm_web_login(
                WebLoginRequest(role="employee", employee_id=301, pin="1234"),
                login_resp,
            )
            cookie = SimpleCookie()
            cookie.load(login_resp.headers["set-cookie"])
            session = cookie["employee_session"].value

            # Authenticated check
            auth_req = Request({
                "type": "http",
                "method": "GET",
                "path": "/crm/api/me",
                "headers": [(b"cookie", f"employee_session={session}".encode())],
            })
            me_auth = await crm_get_current_user(auth_req)
            self.assertTrue(me_auth["authenticated"])
            self.assertEqual(me_auth["role"], "employee")
            self.assertEqual(me_auth["user"]["id"], 301)

            # Logout
            logout_resp = Response()
            logout_res = await crm_logout(logout_resp)
            self.assertEqual(logout_res["status"], "logged_out")

    async def test_crm_dashboard_data_for_admin_and_employee(self) -> None:
        register_employee(self.database_path, 401, "Sardor", pin="1234")
        create_card_request(self.database_path, 401, "8600123456789012", "Sardor Aliyev", 100_000)
        create_money_giving(self.database_path, 401, 50_000, note="Kassa")

        with patch("app.main.get_settings", return_value=self.settings):
            # Admin Login
            login_resp = Response()
            await crm_web_login(WebLoginRequest(role="admin", username="admin", password="admin123"), login_resp)
            cookie = SimpleCookie()
            cookie.load(login_resp.headers["set-cookie"])
            admin_session = cookie["admin_session"].value

            admin_req = Request({
                "type": "http",
                "method": "GET",
                "path": "/crm/api/dashboard",
                "headers": [(b"cookie", f"admin_session={admin_session}".encode())],
            })
            admin_dash = await crm_dashboard_data(admin_req)
            self.assertEqual(admin_dash["role"], "admin")
            self.assertIn("stats", admin_dash["data"])
            self.assertIn("cards", admin_dash["data"])
            self.assertIn("givings", admin_dash["data"])
            self.assertIn("reports", admin_dash["data"])
            self.assertIn("debt_balances", admin_dash["data"])
            self.assertEqual(len(admin_dash["data"]["cards"]), 1)

            # Employee Login
            emp_resp = Response()
            await crm_web_login(WebLoginRequest(role="employee", employee_id=401, pin="1234"), emp_resp)
            cookie_emp = SimpleCookie()
            cookie_emp.load(emp_resp.headers["set-cookie"])
            emp_session = cookie_emp["employee_session"].value

            emp_req = Request({
                "type": "http",
                "method": "GET",
                "path": "/crm/api/dashboard",
                "headers": [(b"cookie", f"employee_session={emp_session}".encode())],
            })
            emp_dash = await crm_dashboard_data(emp_req)
            self.assertEqual(emp_dash["role"], "employee")
            self.assertIn("cards", emp_dash["data"])
            self.assertIn("debt_balance", emp_dash["data"])

    async def test_crm_update_employee_pin(self) -> None:
        register_employee(self.database_path, 501, "Dilshod", pin="1234")

        with patch("app.main.get_settings", return_value=self.settings):
            res = await crm_update_employee_pin(501, EmployeePinUpdate(pin="9876"))
            self.assertEqual(res["status"], "pin_updated")

            emp = get_active_employee(self.database_path, 501)
            self.assertIsNotNone(emp)
            self.assertEqual(emp.pin, "9876")
