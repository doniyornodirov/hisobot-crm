import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from app.employees import initialize_database, register_employee
from app.workflows import (
    add_debt,
    admin_dashboard,
    create_card_request,
    create_money_giving,
    create_report,
    employee_dashboard,
    initialize_workflows,
    review_card_request,
    review_money_giving,
    review_report,
    rating_boards,
    set_card_request_decision,
    _work_date,
)


class WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "app.sqlite3"
        initialize_database(self.database_path)
        initialize_workflows(self.database_path)
        register_employee(self.database_path, 12345, "Ali")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_card_request_rejects_amount_below_minimum(self) -> None:
        with self.assertRaisesRegex(ValueError, "10 000"):
            create_card_request(self.database_path, 12345, "1234567812345678", "Ali Valiyev", 9_999)
        for amount, expected_total in ((10_000, 11_000), (10_001, 11_000), (100_000, 103_000), (100_001, 104_000)):
            request_id = create_card_request(
                self.database_path, 12345, "1234567812345678", "Ali Valiyev", amount
            )
            set_card_request_decision(self.database_path, request_id, True, 999)
        dashboard = employee_dashboard(self.database_path, 12345)
        self.assertEqual(
            [card["total_with_fee"] for card in dashboard["cards"]],
            [104_000, 103_000, 11_000, 11_000],
        )
        self.assertEqual(dashboard["card_total_with_fee"], 229_000)
        self.assertEqual(dashboard["rating"]["monthly"]["card_total_with_fee"], 229_000)

    def test_initialization_recalculates_existing_report_card_totals(self) -> None:
        card_id = create_card_request(
            self.database_path, 12345, "1234567812345678", "Ali Valiyev", 10_000
        )
        set_card_request_decision(self.database_path, card_id, True, 999)
        report_id = create_report(
            self.database_path,
            12345,
            {
                "work_date": _work_date().isoformat(),
                "paynet": 0,
                "levy": 0,
                "simcard": 0,
                "debt_payment": 0,
                "terminal": 0,
                "daily": 0,
                "discount": 0,
                "expense": 0,
            },
        )
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute("UPDATE reports SET card_total = ? WHERE id = ?", (10_300, report_id))
            connection.commit()
        finally:
            connection.close()

        initialize_workflows(self.database_path)

        report = employee_dashboard(self.database_path, 12345)["reports"][0]
        self.assertEqual(report["card_total"], 11_000)

    def test_approved_operations_appear_in_report_and_debt_is_paid_only_on_approval(self) -> None:
        card_id = create_card_request(self.database_path, 12345, "1234567812345678", "Ali Valiyev", 100_000)
        giving_id = create_money_giving(self.database_path, 12345, 50_000, "Kun yakuni")
        review_card_request(self.database_path, card_id, 12345, True, "", 999)
        review_money_giving(self.database_path, giving_id, 12345, True, "", 999)
        add_debt(self.database_path, 12345, 200_000, "Tovar qarzi", 999)

        report_id = create_report(
            self.database_path,
            12345,
            {
                "work_date": _work_date().isoformat(),
                "paynet": 300_000,
                "levy": 0,
                "simcard": 2,
                "debt_payment": 75_000,
                "terminal": 0,
                "daily": 0,
                "discount": 0,
                "expense": 0,
                "comment": "Kunlik hisobot",
            },
        )
        pending = employee_dashboard(self.database_path, 12345)
        self.assertEqual(pending["debt_balance"], 200_000)
        self.assertEqual(pending["card_total_with_fee"], 103_000)
        self.assertEqual(pending["approved_giving_total"], 50_000)
        self.assertEqual(pending["reports"][0]["card_total"], 103_000)
        self.assertEqual(pending["reports"][0]["giving_total"], 50_000)

        review_report(self.database_path, report_id, True, "", 999)

        final = employee_dashboard(self.database_path, 12345)
        self.assertEqual(final["debt_balance"], 125_000)
        self.assertEqual(final["reports"][0]["status"], "approved")

    def test_rejected_report_does_not_reduce_debt_and_requires_reason(self) -> None:
        add_debt(self.database_path, 12345, 100_000, "Qarz", 999)
        report_id = create_report(
            self.database_path,
            12345,
            {
                "work_date": _work_date().isoformat(),
                "paynet": 0,
                "levy": 0,
                "simcard": 0,
                "debt_payment": 20_000,
                "terminal": 0,
                "daily": 0,
                "discount": 0,
                "expense": 0,
            },
        )

        with self.assertRaisesRegex(ValueError, "sababi"):
            review_report(self.database_path, report_id, False, "", 999)
        review_report(self.database_path, report_id, False, "Summa noto'g'ri", 999)

        dashboard = employee_dashboard(self.database_path, 12345)
        self.assertEqual(dashboard["debt_balance"], 100_000)
        self.assertEqual(dashboard["reports"][0]["decision_reason"], "Summa noto'g'ri")

    def test_report_decision_can_be_reversed_without_double_charging_debt(self) -> None:
        add_debt(self.database_path, 12345, 100_000, "Qarz", 999)
        report_id = create_report(
            self.database_path,
            12345,
            {
                "work_date": _work_date().isoformat(),
                "paynet": 0,
                "levy": 0,
                "simcard": 0,
                "debt_payment": 20_000,
                "terminal": 0,
                "daily": 0,
                "discount": 0,
                "expense": 0,
            },
        )

        review_report(self.database_path, report_id, True, "", 999)
        self.assertEqual(employee_dashboard(self.database_path, 12345)["debt_balance"], 80_000)
        review_report(self.database_path, report_id, False, "Xato", 999)
        self.assertEqual(employee_dashboard(self.database_path, 12345)["debt_balance"], 100_000)
        review_report(self.database_path, report_id, False, "Xato", 999)
        self.assertEqual(employee_dashboard(self.database_path, 12345)["debt_balance"], 100_000)
        review_report(self.database_path, report_id, True, "", 999)
        self.assertEqual(employee_dashboard(self.database_path, 12345)["debt_balance"], 80_000)
        self.assertEqual(
            employee_dashboard(self.database_path, 12345)["reports"][0]["status"],
            "approved",
        )

    def test_rejected_report_can_be_resubmitted_for_same_date(self) -> None:
        original = {
            "work_date": _work_date().isoformat(),
            "paynet": 10_000,
            "levy": 0,
            "simcard": 0,
            "debt_payment": 0,
            "terminal": 0,
            "daily": 0,
            "discount": 0,
            "expense": 0,
            "comment": "Birinchi nusxa",
        }
        report_id = create_report(self.database_path, 12345, original)
        review_report(self.database_path, report_id, False, "Qayta tekshiring", 999)

        corrected = {**original, "paynet": 25_000, "comment": "Tuzatilgan"}
        resubmitted_id = create_report(self.database_path, 12345, corrected)

        self.assertEqual(resubmitted_id, report_id)
        report = employee_dashboard(self.database_path, 12345)["reports"][0]
        self.assertEqual(report["status"], "pending")
        self.assertEqual(report["paynet"], 25_000)
        self.assertEqual(report["comment"], "Tuzatilgan")
        self.assertIsNone(report["decision_reason"])
        final_id = create_report(
            self.database_path,
            12345,
            {**corrected, "paynet": 30_000},
        )
        self.assertEqual(final_id, report_id)
        self.assertEqual(
            employee_dashboard(self.database_path, 12345)["reports"][0]["paynet"],
            30_000,
        )

    def test_one_report_per_employee_and_date_and_debt_cannot_be_overpaid(self) -> None:
        add_debt(self.database_path, 12345, 10_000, "Qarz", 999)
        report_data = {
            "work_date": _work_date().isoformat(),
            "paynet": 0,
            "levy": 0,
            "simcard": 0,
            "debt_payment": 11_000,
            "terminal": 0,
            "daily": 0,
            "discount": 0,
            "expense": 0,
        }
        with self.assertRaisesRegex(ValueError, "qarzdorlikdan"):
            create_report(self.database_path, 12345, report_data)

        report_data["debt_payment"] = 0
        report_id = create_report(self.database_path, 12345, report_data)
        updated_report_id = create_report(
            self.database_path,
            12345,
            {**report_data, "paynet": 25_000},
        )
        self.assertEqual(updated_report_id, report_id)
        self.assertEqual(
            employee_dashboard(self.database_path, 12345)["reports"][0]["paynet"],
            25_000,
        )

    def test_replacing_approved_report_reverses_its_debt_payment(self) -> None:
        add_debt(self.database_path, 12345, 100_000, "Qarz", 999)
        report_values = {
            "work_date": _work_date().isoformat(),
            "paynet": 0,
            "levy": 0,
            "simcard": 0,
            "debt_payment": 60_000,
            "terminal": 0,
            "daily": 0,
            "discount": 0,
            "expense": 0,
        }
        report_id = create_report(self.database_path, 12345, report_values)
        review_report(self.database_path, report_id, True, "", 999)
        self.assertEqual(employee_dashboard(self.database_path, 12345)["debt_balance"], 40_000)

        replacement_id = create_report(
            self.database_path,
            12345,
            {**report_values, "debt_payment": 70_000},
        )

        dashboard = employee_dashboard(self.database_path, 12345)
        self.assertEqual(replacement_id, report_id)
        self.assertEqual(dashboard["debt_balance"], 100_000)
        self.assertEqual(dashboard["reports"][0]["debt_payment"], 70_000)
        self.assertEqual(dashboard["reports"][0]["status"], "pending")
        self.assertIn("almashtirildi", dashboard["debts"][0]["description"])

    def test_admin_dashboard_contains_review_history_and_debt_balance(self) -> None:
        giving_id = create_money_giving(self.database_path, 12345, 20_000)
        review_money_giving(self.database_path, giving_id, 12345, False, "Tekshirib chiqing", 999)
        add_debt(self.database_path, 12345, 30_000, "Qarz", 999)

        dashboard = admin_dashboard(self.database_path)

        self.assertEqual(dashboard["givings"][0]["decision_reason"], "Tekshirib chiqing")
        self.assertEqual(dashboard["debt_balances"][0]["balance"], 30_000)
        self.assertTrue(dashboard["audit"])

    def test_giving_decision_can_be_reversed_and_recalculates_report_total(self) -> None:
        giving_id = create_money_giving(
            self.database_path, 12345, 50_000, "Kun yakuni"
        )
        report_id = create_report(
            self.database_path,
            12345,
            {
                "work_date": _work_date().isoformat(),
                "paynet": 100_000,
                "levy": 0,
                "simcard": 0,
                "debt_payment": 0,
                "terminal": 0,
                "daily": 0,
                "discount": 0,
                "expense": 0,
            },
        )

        review_money_giving(
            self.database_path, giving_id, 12345, True, "", 999
        )
        approved = employee_dashboard(self.database_path, 12345)["reports"][0]
        self.assertEqual(approved["id"], report_id)
        self.assertEqual(approved["giving_total"], 50_000)

        review_money_giving(
            self.database_path, giving_id, 12345, False, "", 999
        )
        rejected = employee_dashboard(self.database_path, 12345)["reports"][0]
        self.assertEqual(rejected["giving_total"], 0)
        self.assertEqual(rejected["status"], "pending")
        self.assertEqual(
            employee_dashboard(self.database_path, 12345)["givings"][0]["status"],
            "rejected",
        )
        self.assertIsNone(
            employee_dashboard(self.database_path, 12345)["givings"][0]["decision_reason"]
        )

        review_money_giving(
            self.database_path, giving_id, 12345, True, "", 999
        )
        restored = employee_dashboard(self.database_path, 12345)["reports"][0]
        self.assertEqual(restored["giving_total"], 50_000)
        self.assertEqual(
            employee_dashboard(self.database_path, 12345)["givings"][0]["status"],
            "approved",
        )

    def test_card_decision_can_be_reversed_and_recalculates_submitted_report(self) -> None:
        card_id = create_card_request(
            self.database_path, 12345, "1234567812345678", "Ali Valiyev", 100_000
        )
        report_id = create_report(
            self.database_path,
            12345,
            {
                "work_date": _work_date().isoformat(),
                "paynet": 0,
                "levy": 0,
                "simcard": 0,
                "debt_payment": 0,
                "terminal": 0,
                "daily": 0,
                "discount": 0,
                "expense": 0,
            },
        )

        set_card_request_decision(self.database_path, card_id, True, 9001)
        approved_report = employee_dashboard(self.database_path, 12345)["reports"][0]
        self.assertEqual(approved_report["id"], report_id)
        self.assertEqual(approved_report["card_total"], 103_000)

        set_card_request_decision(self.database_path, card_id, False, 9002)
        rejected_report = employee_dashboard(self.database_path, 12345)["reports"][0]
        self.assertEqual(rejected_report["card_total"], 0)
        self.assertEqual(rejected_report["status"], "pending")
        self.assertEqual(
            employee_dashboard(self.database_path, 12345)["cards"][0]["status"],
            "rejected",
        )

    def test_ratings_use_approved_revenue_and_current_debt(self) -> None:
        register_employee(self.database_path, 67890, "Zarina")
        monthly_card_id = create_card_request(
            self.database_path, 12345, "1234567812345678", "Ali Valiyev", 100_000
        )
        set_card_request_decision(self.database_path, monthly_card_id, True, 999)

        previous_month = (_work_date().replace(day=1) - timedelta(days=1)).isoformat()
        historical_card_id = create_card_request(
            self.database_path, 12345, "8765432187654321", "Ali Valiyev", 100_000
        )
        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute(
                "UPDATE card_requests SET work_date = ? WHERE id = ?",
                (previous_month, historical_card_id),
            )
            connection.commit()
        finally:
            connection.close()
        set_card_request_decision(self.database_path, historical_card_id, True, 999)

        create_money_giving(self.database_path, 12345, 900_000, "Kutilmoqda")
        giving_id = create_money_giving(
            self.database_path, 12345, 100_000, "Berilgan summa"
        )
        review_money_giving(
            self.database_path, giving_id, 12345, True, "", 999
        )
        add_debt(self.database_path, 12345, 50_000, "Qarz", 999)
        report_id = create_report(
            self.database_path,
            12345,
            {
                "work_date": _work_date().isoformat(),
                "paynet": 200_000,
                "levy": 0,
                "simcard": 0,
                "debt_payment": 0,
                "terminal": 0,
                "daily": 0,
                "discount": 0,
                "expense": 0,
            },
        )
        review_report(self.database_path, report_id, True, "", 999)
        create_report(
            self.database_path,
            12345,
            {
                "work_date": previous_month,
                "paynet": 900_000,
                "levy": 0,
                "simcard": 0,
                "debt_payment": 0,
                "terminal": 0,
                "daily": 0,
                "discount": 0,
                "expense": 0,
            },
        )

        boards = rating_boards(self.database_path)
        monthly = {row["employee_id"]: row for row in boards["monthly"]}
        overall = {row["employee_id"]: row for row in boards["overall"]}

        self.assertEqual(monthly[12345]["card_total_with_fee"], 103_000)
        self.assertEqual(monthly[12345]["approved_giving_total"], 100_000)
        self.assertEqual(monthly[12345]["report_submission_total"], 203_000)
        self.assertEqual(monthly[12345]["debt_balance"], 50_000)
        self.assertEqual(monthly[12345]["score"], 3.56)
        self.assertEqual(overall[12345]["card_total_with_fee"], 206_000)
        self.assertEqual(overall[12345]["score"], 4.59)
        self.assertEqual(monthly[67890]["score"], 0)
        self.assertEqual(monthly[67890]["rank"], 2)
        employee_rating = employee_dashboard(self.database_path, 12345)["rating"]
        self.assertEqual(employee_rating["monthly"]["score"], 3.56)
        self.assertEqual(len(employee_rating["monthly_top"]), 2)
        self.assertEqual(len(employee_rating["overall_top"]), 2)

    def test_admin_dashboard_limits_each_rating_to_top_three_positions(self) -> None:
        employee_ids = [12345, 67890, 67891, 67892]
        amounts = [100_000, 200_000, 300_000, 400_000]
        for employee_id, amount in zip(employee_ids[1:], amounts[1:]):
            register_employee(self.database_path, employee_id, f"Employee {employee_id}")
            card_id = create_card_request(
                self.database_path,
                employee_id,
                f"{employee_id:016d}",
                "Card Holder",
                amount,
            )
            set_card_request_decision(self.database_path, card_id, True, 999)

        dashboard = admin_dashboard(self.database_path)

        self.assertEqual(len(dashboard["ratings"]["monthly"]), 3)
        self.assertEqual(len(dashboard["ratings"]["overall"]), 3)
        self.assertEqual(
            [row["employee_id"] for row in dashboard["ratings"]["monthly"]],
            [67892, 67891, 67890],
        )


if __name__ == "__main__":
    unittest.main()
