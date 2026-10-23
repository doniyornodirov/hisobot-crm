const message = document.querySelector("#message");
const authStatus = document.querySelector("#auth-status");
const addForm = document.querySelector("#add-form");
const adminControls = addForm.querySelectorAll("input, button");
const reportEmployeeFilter = document.querySelector("#report-employee-filter");
let reportRows = [];
let employeeNames = new Map();

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function digitsOnly(value) {
  return value.replace(/\D/g, "");
}

function groupDigits(digits) {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function formatTimestamp(value) {
  return new Intl.DateTimeFormat("uz-UZ", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "Asia/Tashkent"
  }).format(new Date(value));
}

function submissionTotal(report) {
  return report.paynet + report.card_total + report.levy + report.daily
    - report.terminal - report.giving_total - report.discount - report.expense
    + report.debt_payment;
}

function reportFields(report, employeeName) {
  const fields = node("div", undefined, "report-fields");
  const lines = [
    `👤 Xodim: ${employeeName}`,
    `📅 Sana: ${report.work_date}`,
    `💳 Paynet: ${Number(report.paynet).toLocaleString()} so'm`,
    `💳 Card (+3%): ${Number(report.card_total).toLocaleString()} so'm`,
    `🏷️ Levy: ${Number(report.levy).toLocaleString()} so'm`,
    `📱 SIMcard: ${report.simcard} dona`,
    `💸 Qarz uchun: ${Number(report.debt_payment).toLocaleString()} so'm`,
    `✅ Berildi (tasdiqlangan): ${Number(report.giving_total).toLocaleString()} so'm`,
    `🏧 Terminal: ${Number(report.terminal).toLocaleString()} so'm`,
    `☀️ Kunlik: ${Number(report.daily).toLocaleString()} so'm`,
    `🏷️ Skidka: ${Number(report.discount).toLocaleString()} so'm`,
    `🧾 Xarajat: ${Number(report.expense).toLocaleString()} so'm`,
    `📦 Jami topshirilishi kerak: ${submissionTotal(report).toLocaleString()} so'm`
  ];
  if (report.comment) lines.push(`📝 Izoh: ${report.comment}`);
  for (const line of lines) {
    fields.append(node("div", line, line.startsWith("📦") ? "report-line report-total" : "report-line"));
  }
  return fields;
}

function formatAmountInput(input, maxDigits) {
  input.addEventListener("input", () => {
    const cursor = input.selectionStart ?? input.value.length;
    const digitsBeforeCursor = digitsOnly(input.value.slice(0, cursor)).length;
    const digits = digitsOnly(input.value).slice(0, maxDigits);
    input.value = groupDigits(digits);
    let nextCursor = 0;
    let countedDigits = 0;
    while (nextCursor < input.value.length && countedDigits < digitsBeforeCursor) {
      if (/\d/.test(input.value[nextCursor])) countedDigits += 1;
      nextCursor += 1;
    }
    input.setSelectionRange(nextCursor, nextCursor);
    input.setCustomValidity("");
  });
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.method ? { "X-Requested-With": "XMLHttpRequest" } : {}),
      ...options.headers
    }
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || "So'rov bajarilmadi.");
  return result;
}

function renderList(target, rows, renderRow, emptyText) {
  target.replaceChildren();
  if (!rows.length) {
    target.append(node("p", emptyText, "muted"));
    return;
  }
  rows.forEach((item) => target.append(renderRow(item)));
}

function decisionButtons(type, item, decisions = [true, false], reasonRequired = true) {
  const actions = node("div", undefined, "entry-actions");
  for (const approved of decisions) {
    const button = node(
      "button",
      approved ? "Tasdiqlash" : "Rad etish",
      approved ? "approve" : "danger"
    );
    button.addEventListener("click", async () => {
      let reason = "";
      if (!approved) {
        if (reasonRequired) {
          reason = prompt("Rad etish sababini kiriting:");
          if (reason === null) return;
          if (!reason.trim()) {
            message.textContent = "Rad etish sababi majburiy.";
            message.className = "error";
            return;
          }
        }
      }
      try {
        await api(`/admin/api/${type}/${item.id}/decision`, {
          method: "POST",
          body: JSON.stringify({ approved, reason })
        });
        message.textContent = "Qaror saqlandi.";
        message.className = "";
        await loadDashboard();
      } catch (error) {
        message.textContent = error.message;
        message.className = "error";
      }
    });
    actions.append(button);
  }
  return actions;
}

function historyText(item) {
  const labels = {
    pending: ["⏳ Kutilmoqda", "status-pending"],
    approved: ["✅ Tasdiqlandi", "status-approved"],
    rejected: ["❌ Rad etildi", "status-rejected"]
  };
  const [label, statusClass] = labels[item.status] || [item.status, "status-pending"];
  const history = node("div", undefined, "history-meta");
  history.append(
    node("p", `Kiritilgan: ${formatTimestamp(item.created_at)}`, "history-time"),
    node("span", label, `status-line ${statusClass}`)
  );
  return history;
}

function renderEmployees(employees) {
  renderList(document.querySelector("#employees"), employees, (employee) => {
    const row = node("div", undefined, "entry employee-entry");
    const heading = node("div", undefined, "employee-heading");
    heading.append(
      node("strong", employee.bot_name, "employee-name"),
      node("span", `ID ${employee.telegram_id}`, "employee-id")
    );
    row.append(heading);
    const debtForm = node("form", undefined, "form-row");
    debtForm.innerHTML = '<input name="amount" type="text" inputmode="numeric" pattern="[0-9]{1,3}( [0-9]{3})*" maxlength="13" placeholder="Qarz summasi" required><input name="description" maxlength="500" placeholder="Qarz sababi" required><button type="submit">Qarz belgilash</button>';
    const debtAmount = debtForm.elements.amount;
    formatAmountInput(debtAmount, 10);
    debtForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const amountDigits = digitsOnly(debtAmount.value);
      const amount = Number(amountDigits);
      if (!amountDigits || amount <= 0 || amount > 1_000_000_000) {
        debtAmount.setCustomValidity("Qarz summasini 1 dan 1 000 000 000 gacha kiriting.");
        debtForm.reportValidity();
        return;
      }
      const data = new FormData(debtForm);
      try {
        await api(`/admin/api/employees/${employee.telegram_id}/debt`, {
          method: "POST",
          body: JSON.stringify({ amount, description: data.get("description") })
        });
        message.textContent = "Qarzdorlik qayd etildi.";
        message.className = "";
        await loadDashboard();
      } catch (error) {
        message.textContent = error.message;
        message.className = "error";
      }
    });
    const dismiss = node("button", "Ishdan bo'shatish", "danger");
    dismiss.addEventListener("click", async () => {
      if (!confirm(`${employee.bot_name} ishdan bo'shatilsinmi?`)) return;
      try {
        await api(`/admin/api/employees/${employee.telegram_id}/dismiss`, { method: "POST" });
        message.textContent = "Xodimning web-ilovaga kirishi bloklandi.";
        await loadDashboard();
      } catch (error) {
        message.textContent = error.message;
        message.className = "error";
      }
    });
    const employeeActions = node("div", undefined, "employee-actions");
    employeeActions.append(debtForm, dismiss);
    row.append(employeeActions);
    return row;
  }, "Faol xodimlar yo'q.");
}

function renderGivings(givings, names) {
  renderList(document.querySelector("#givings"), givings, (item) => {
    const row = node("div", undefined, "entry");
    row.append(
      node("div", `${names.get(item.employee_id) || item.employee_id} · ${item.amount.toLocaleString()} so'm · ${item.work_date}`),
      node("div", item.note || "Izohsiz"),
      historyText(item)
    );
    if (item.status === "pending") {
      row.append(decisionButtons("givings", item, [true, false], false));
    } else {
      row.append(decisionButtons("givings", item, [item.status === "rejected"], false));
    }
    return row;
  }, "Berilgan summa so'rovlari yo'q.");
}

function renderReports(reports, names) {
  const selectedEmployee = reportEmployeeFilter.value;
  const filteredReports = selectedEmployee
    ? reports.filter((item) => String(item.employee_id) === selectedEmployee)
    : reports;
  renderList(document.querySelector("#reports"), filteredReports, (item) => {
    const row = node("div", undefined, "entry");
    row.append(
      reportFields(item, names.get(item.employee_id) || String(item.employee_id)),
      historyText(item)
    );
    if (item.status === "pending") {
      row.append(decisionButtons("reports", item));
    } else {
      row.append(decisionButtons("reports", item, [item.status === "rejected"]));
    }
    return row;
  }, selectedEmployee ? "Tanlangan xodimda hisobotlar yo'q." : "Hisobotlar yo'q.");
}

function renderReportEmployeeFilter(employees) {
  const selectedEmployee = reportEmployeeFilter.value;
  reportEmployeeFilter.replaceChildren(node("option", "Barcha xodimlar"));
  reportEmployeeFilter.firstElementChild.value = "";
  employees.forEach((employee) => {
    const option = node("option", employee.bot_name);
    option.value = String(employee.telegram_id);
    reportEmployeeFilter.append(option);
  });
  if ([...reportEmployeeFilter.options].some((option) => option.value === selectedEmployee)) {
    reportEmployeeFilter.value = selectedEmployee;
  }
}

reportEmployeeFilter.addEventListener("change", () => {
  renderReports(reportRows, employeeNames);
});

function renderDebts(debts, balances, names) {
  const target = document.querySelector("#debts");
  target.replaceChildren();
  if (!balances.length) target.append(node("p", "Hali qarzdorlik belgilanmagan.", "muted"));
  for (const item of balances) {
    target.append(node("div", `${names.get(item.employee_id) || item.employee_id} · Qoldiq: ${Number(item.balance).toLocaleString()} so'm`, "entry"));
  }
  if (debts.length) {
    target.append(node("h3", "Qarz o'zgarishlari tarixi"));
    const history = node("div", undefined, "history-scroll");
    debts.forEach((item) => {
      const isAdded = item.amount_delta > 0;
      const row = node("div", undefined, `debt-history-row ${isAdded ? "debt-added" : "debt-paid"}`);
      const amount = `${isAdded ? "+" : "−"}${Math.abs(item.amount_delta).toLocaleString()} so'm`;
      const details = node("div", undefined, "debt-history-details");
      details.append(
        node("strong", `${names.get(item.employee_id) || item.employee_id} · ${amount}`),
        node("span", item.description, "debt-history-description"),
        node("time", formatTimestamp(item.created_at), "debt-history-time")
      );
      row.append(node("span", isAdded ? "＋" : "✓", "debt-history-icon"), details);
      history.append(row);
    });
    target.append(history);
    fitHistoryList(history);
  }
}

function renderRating(target, rows) {
  target.replaceChildren();
  const topRows = rows.filter((item) => item.rank <= 3);
  if (!topRows.length) {
    target.append(node("p", "Reyting uchun xodimlar yo'q.", "muted"));
    return;
  }
  for (const item of topRows) {
    const row = node("div", undefined, `ranking-row ranking-place-${item.rank}`);
    const medal = ["🥇", "🥈", "🥉"][item.rank - 1] || "";
    row.append(
      node("span", `${medal} #${item.rank} · ${item.bot_name}`, "ranking-name"),
      node("span", `${Number(item.score).toFixed(2)} ball`, "ranking-score"),
      node(
        "span",
        `Karta (+3%): ${Number(item.card_total_with_fee).toLocaleString()} so'm · Berildi: ${Number(item.approved_giving_total).toLocaleString()} so'm · Hisobot: ${Number(item.report_submission_total).toLocaleString()} so'm · Qarz: ${Number(item.debt_balance).toLocaleString()} so'm`,
        "ranking-details"
      )
    );
    target.append(row);
  }
}

function fitHistoryList(history) {
  const entries = [...history.children];
  if (entries.length <= 3) {
    history.style.maxHeight = "";
    return;
  }
  history.style.maxHeight = "none";
  const visibleHeight = entries.slice(0, 3).reduce((height, entry) => {
    const style = getComputedStyle(entry);
    return height + entry.getBoundingClientRect().height + Number.parseFloat(style.marginTop) + Number.parseFloat(style.marginBottom);
  }, 0);
  history.style.maxHeight = `${Math.ceil(visibleHeight)}px`;
}

window.addEventListener("resize", () => {
  document.querySelectorAll(".history-scroll").forEach(fitHistoryList);
});

async function loadDashboard() {
  const data = await api("/admin/api/workflows");
  renderEmployees(data.employees);
  renderReportEmployeeFilter(data.employees);
  employeeNames = new Map(data.employees.map((employee) => [employee.telegram_id, employee.bot_name]));
  renderGivings(data.givings, employeeNames);
  reportRows = data.reports;
  renderReports(reportRows, employeeNames);
  renderDebts(data.debts, data.debt_balances, employeeNames);
  renderRating(document.querySelector("#monthly-ranking"), data.ratings.monthly);
  renderRating(document.querySelector("#overall-ranking"), data.ratings.overall);
}

addForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(addForm);
  try {
    await api("/admin/api/employees", {
      method: "POST",
      body: JSON.stringify({ telegram_id: Number(data.get("telegram_id")), bot_name: data.get("bot_name") })
    });
    message.textContent = "Xodim qo'shildi.";
    message.className = "";
    addForm.reset();
    await loadDashboard();
  } catch (error) {
    message.textContent = error.message;
    message.className = "error";
  }
});

async function signInAdmin() {
  const telegram = window.Telegram?.WebApp;
  if (!telegram?.initData) {
    authStatus.textContent = "Admin panelni Telegram botdagi pastki Admin panel tugmasidan oching.";
    return;
  }
  telegram.ready();
  telegram.expand();
  const result = await api("/auth/telegram", {
    method: "POST",
    body: JSON.stringify({ init_data: telegram.initData })
  });
  if (result.role !== "admin") throw new Error("Superadmin akkaunti bilan Telegram botdan oching.");
  adminControls.forEach((control) => { control.disabled = false; });
  authStatus.textContent = "Superadmin sifatida tasdiqlandingiz.";
  await loadDashboard();
}

signInAdmin().catch((error) => {
  authStatus.textContent = error.message || "Kirish vaqtida xatolik yuz berdi.";
});
