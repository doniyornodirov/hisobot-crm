const greeting = document.querySelector("#greeting");
const statusText = document.querySelector("#status");
const workspace = document.querySelector("#workspace");
const telegram = window.Telegram?.WebApp;

function el(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function money(value) {
  return `${Number(value).toLocaleString()} so'm`;
}

function submissionTotal(report) {
  return report.paynet + report.card_total + report.levy + report.daily
    - report.terminal - report.giving_total - report.discount - report.expense
    + report.debt_payment;
}

function reportFields(report) {
  const fields = el("div", undefined, "report-fields");
  const lines = [
    `📅 Sana: ${report.work_date}`,
    `💳 Paynet: ${money(report.paynet)}`,
    `💳 Card (+3%): ${money(report.card_total)}`,
    `🏷️ Levy: ${money(report.levy)}`,
    `📱 SIMcard: ${report.simcard} dona`,
    `💸 Qarz uchun: ${money(report.debt_payment)}`,
    `✅ Berildi (tasdiqlangan): ${money(report.giving_total)}`,
    `🏧 Terminal: ${money(report.terminal)}`,
    `☀️ Kunlik: ${money(report.daily)}`,
    `🏷️ Skidka: ${money(report.discount)}`,
    `🧾 Xarajat: ${money(report.expense)}`,
    `📦 Jami topshirilishi kerak: ${money(submissionTotal(report))}`
  ];
  if (report.comment) lines.push(`📝 Izoh: ${report.comment}`);
  lines.push(`🕒 Yuborilgan: ${formatTimestamp(report.created_at)}`);
  for (const line of lines) {
    fields.append(el("div", line, line.startsWith("📦") ? "report-line report-total" : "report-line"));
  }
  return fields;
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

function formatRequestTime(value) {
  return new Intl.DateTimeFormat("uz-UZ", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "Asia/Tashkent"
  }).format(new Date(value));
}

function renderDebtHistoryRow(item) {
  const isAdded = item.amount_delta > 0;
  const row = el("div", undefined, `debt-history-row ${isAdded ? "debt-added" : "debt-paid"}`);
  const amount = `${isAdded ? "+" : "−"}${money(Math.abs(item.amount_delta))}`;
  const details = el("div", undefined, "debt-history-details");
  details.append(
    el("strong", amount),
    el("span", item.description, "debt-history-description"),
    el("time", formatTimestamp(item.created_at), "debt-history-time")
  );
  row.append(el("span", isAdded ? "＋" : "✓", "debt-history-icon"), details);
  return row;
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

function showRows(target, rows, render, emptyText) {
  target.replaceChildren();
  if (!rows.length) target.append(el("p", emptyText, "muted"));
  rows.forEach((item) => target.append(render(item)));
}

function fitHistoryList(history) {
  const entries = [...history.children].filter((entry) => entry.classList.contains("entry") || entry.classList.contains("debt-history-row"));
  const visibleCount = Number(history.dataset.visibleCount) || 3;
  if (entries.length <= visibleCount) {
    history.style.maxHeight = "";
    return;
  }
  history.style.maxHeight = "none";
  const visibleHeight = entries.slice(0, visibleCount).reduce((height, entry) => {
    const style = getComputedStyle(entry);
    return height + entry.getBoundingClientRect().height + Number.parseFloat(style.marginTop) + Number.parseFloat(style.marginBottom);
  }, 0);
  history.style.maxHeight = `${Math.ceil(visibleHeight)}px`;
}

function fitHistoryLists() {
  document.querySelectorAll(".history-scroll").forEach(fitHistoryList);
}

window.addEventListener("resize", fitHistoryLists);

function renderStatus(item) {
  const labels = {
    pending: ["⏳ Kutilmoqda", "status-pending"],
    approved: ["✅ Tasdiqlandi", "status-approved"],
    rejected: ["❌ Rad etildi", "status-rejected"]
  };
  const [label, statusClass] = labels[item.status] || [item.status, "status-pending"];
  return el("span", label, `status-line ${statusClass}`);
}

function digitsOnly(value) {
  return value.replace(/\D/g, "");
}

function groupDigits(digits) {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function numberToUzbekWords(value) {
  const ones = ["", "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz"];
  const tens = ["", "o'n", "yigirma", "o'ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to'qson"];
  const scales = ["", "ming", "million", "milliard"];

  function underThousand(number) {
    const words = [];
    const hundreds = Math.floor(number / 100);
    const remainder = number % 100;
    if (hundreds) words.push(`${ones[hundreds]} yuz`);
    if (remainder >= 10) words.push(tens[Math.floor(remainder / 10)]);
    if (remainder % 10) words.push(ones[remainder % 10]);
    return words.join(" ");
  }

  if (value === 0) return "nol";
  const parts = [];
  let remaining = value;
  let scaleIndex = 0;
  while (remaining > 0) {
    const group = remaining % 1000;
    if (group) {
      const groupWords = underThousand(group);
      parts.unshift([groupWords, scales[scaleIndex]].filter(Boolean).join(" "));
    }
    remaining = Math.floor(remaining / 1000);
    scaleIndex += 1;
  }
  return parts.join(" ");
}

function formatNumericInput(input, maxDigits, formatter) {
  input.addEventListener("input", () => {
    const cursor = input.selectionStart ?? input.value.length;
    const digitsBeforeCursor = digitsOnly(input.value.slice(0, cursor)).length;
    const digits = digitsOnly(input.value).slice(0, maxDigits);
    input.value = formatter(digits);
    let nextCursor = 0;
    let countedDigits = 0;
    while (nextCursor < input.value.length && countedDigits < digitsBeforeCursor) {
      if (/\d/.test(input.value[nextCursor])) countedDigits += 1;
      nextCursor += 1;
    }
    input.setSelectionRange(nextCursor, nextCursor);
  });
}

const cardForm = document.querySelector("#card-form");
const givingForm = document.querySelector("#giving-form");
const cardNumberInput = cardForm.elements.card_number;
const cardholderInput = cardForm.elements.cardholder;
const cardAmountInput = cardForm.elements.amount;
const cardAmountPreview = document.querySelector("#card-amount-preview");
const givingAmountInput = givingForm.elements.amount;

formatNumericInput(cardNumberInput, 16, (digits) =>
  digits.match(/.{1,4}/g)?.join(" ") ?? "",
);
formatNumericInput(cardAmountInput, 10, groupDigits);
formatNumericInput(givingAmountInput, 10, groupDigits);
cardAmountInput.addEventListener("input", () => {
  const digits = digitsOnly(cardAmountInput.value);
  const amount = Number(digits);
  cardAmountInput.setCustomValidity("");
  cardAmountPreview.replaceChildren();
  if (!digits) return;
  if (amount < 10_000) {
    cardAmountPreview.append(el("div", "Eng kam summa: 10 000 so'm."));
    return;
  }
  const totalWithFee = Math.ceil((amount * 103) / 100_000) * 1_000;
  const totalLine = el("div");
  const surprise = amount >= 100_000_000
    ? "😱"
    : amount >= 10_000_000
      ? "🤯"
      : amount >= 1_000_000
        ? "😲"
        : amount >= 100_000
          ? "😮"
          : "🙂";
  totalLine.append(
    document.createTextNode("3% bilan jami: "),
    el("strong", `${groupDigits(String(totalWithFee))} so'm`)
  );
  cardAmountPreview.append(
    el("div", `O'qilishi: ${numberToUzbekWords(amount)} so'm`),
    totalLine,
    el("div", surprise, "card-amount-surprise")
  );
});
givingAmountInput.addEventListener("input", () => givingAmountInput.setCustomValidity(""));
givingForm.addEventListener("submit", (event) => {
  const digits = digitsOnly(givingAmountInput.value);
  if (!digits || Number(digits) <= 0 || Number(digits) > 1_000_000_000) {
    event.preventDefault();
    givingAmountInput.setCustomValidity("Summani 1 dan 1 000 000 000 gacha kiriting.");
    givingAmountInput.reportValidity();
    return;
  }
  givingAmountInput.setCustomValidity("");
});
const reportForm = document.querySelector("#report-form");
const reportNumericFields = [
  ["paynet", 1_000_000_000],
  ["levy", 1_000_000_000],
  ["simcard", 1_000_000],
  ["debt_payment", 1_000_000_000],
  ["terminal", 1_000_000_000],
  ["daily", 1_000_000_000],
  ["discount", 1_000_000_000],
  ["expense", 1_000_000_000]
];
for (const [name] of reportNumericFields) {
  const input = reportForm.elements[name];
  formatNumericInput(input, name === "simcard" ? 7 : 10, groupDigits);
  input.addEventListener("input", () => input.setCustomValidity(""));
}
cardNumberInput.addEventListener("input", () => cardNumberInput.setCustomValidity(""));
cardAmountInput.addEventListener("input", () => cardAmountInput.setCustomValidity(""));
cardholderInput.addEventListener("input", () => {
  const cursor = cardholderInput.selectionStart ?? cardholderInput.value.length;
  const beforeCursor = cardholderInput.value.slice(0, cursor);
  const sanitize = (value) => value.replace(/[^\p{L} ]/gu, "").replace(/\s{2,}/g, " ");
  cardholderInput.value = sanitize(cardholderInput.value);
  const newCursor = sanitize(beforeCursor).length;
  cardholderInput.setSelectionRange(newCursor, newCursor);
  cardholderInput.setCustomValidity("");
});

cardForm.addEventListener("submit", (event) => {
  const cardDigits = digitsOnly(cardNumberInput.value);
  if (cardDigits.length !== 16) {
    event.preventDefault();
    cardNumberInput.setCustomValidity("Karta raqami aynan 16 ta raqam bo'lishi kerak.");
    cardNumberInput.reportValidity();
    return;
  }
  cardNumberInput.setCustomValidity("");
  if (!cardholderInput.value.trim() || !/^[\p{L} ]+$/u.test(cardholderInput.value)) {
    event.preventDefault();
    cardholderInput.setCustomValidity("Karta egasini faqat harflar bilan kiriting.");
    cardholderInput.reportValidity();
    return;
  }
  cardholderInput.setCustomValidity("");
  const amountDigits = digitsOnly(cardAmountInput.value);
  if (amountDigits.length === 0 || Number(amountDigits) <= 0 || Number(amountDigits) > 1_000_000_000) {
    event.preventDefault();
    cardAmountInput.setCustomValidity("Summani 1 dan 1 000 000 000 gacha kiriting.");
    cardAmountInput.reportValidity();
    return;
  }
  cardAmountInput.setCustomValidity("");
});

reportForm.addEventListener("submit", (event) => {
  for (const [name, maximum] of reportNumericFields) {
    const input = reportForm.elements[name];
    const digits = digitsOnly(input.value);
    if (!digits || Number(digits) > maximum) {
      event.preventDefault();
      input.setCustomValidity(`Qiymat 0 dan ${maximum.toLocaleString("en-US").replace(/,/g, " ")} gacha bo'lishi kerak.`);
      input.reportValidity();
      return;
    }
    input.setCustomValidity("");
  }
});

async function loadDashboard() {
  const selectedDate = document.querySelector('#report-form [name="work_date"]').value;
  const query = selectedDate ? `?work_date=${encodeURIComponent(selectedDate)}` : "";
  const data = await api(`/employee/api/dashboard${query}`);
  const totals = document.querySelector("#totals");
  totals.dataset.workDate = data.work_date;
  totals.replaceChildren(
    el("div", `Qarzdorlik: ${money(data.debt_balance)}`, "stat"),
    el("div", `Tanlangan sana karta (+3%): ${money(data.card_total_with_fee)}`, "stat"),
    el("div", `Tasdiqlangan berildi: ${money(data.approved_giving_total)}`, "stat")
  );
  renderRating("monthly-ranking", "monthly-rating", data.rating.monthly_top, data.rating.monthly);
  renderRating("overall-ranking", "overall-rating", data.rating.overall_top, data.rating.overall);
  document.querySelector("#card-total").value = money(data.card_total_with_fee);
  document.querySelector("#giving-total").value = money(data.approved_giving_total);
  document.querySelector("#debt-total").value = money(data.debt_balance);
  document.querySelector('#report-form [name="work_date"]').value = data.work_date;
  showRows(document.querySelector("#cards"), data.cards, (item) => {
    const row = el("div", undefined, "entry");
    const total = item.status === "approved" ? item.total_with_fee : item.amount;
    row.append(
      el("div", `${money(total)} · ${item.work_date} · ${formatRequestTime(item.created_at)}`, "card-history-heading"),
      el("div", `👤 ${item.cardholder}`, "card-history-detail"),
      el("div", `💳 ${item.card_number}`, "card-history-detail"),
      renderStatus(item)
    );
    return row;
  }, "Karta so'rovlari yo'q.");
  document.querySelector("#cards").classList.add("history-scroll");
  fitHistoryLists();
  showRows(document.querySelector("#givings"), data.givings, (item) => {
    const row = el("div", undefined, "entry");
    row.append(
      el("strong", `${money(item.amount)} · ${item.work_date}`),
      el("div", item.note || "Izohsiz"),
      el("p", `Yuborilgan: ${formatTimestamp(item.created_at)}`, "history-time"),
      renderStatus(item)
    );
    return row;
  }, "Yuborilgan summa yo'q.");
  const reportHistory = document.querySelector("#reports");
  reportHistory.classList.add("history-scroll");
  reportHistory.dataset.visibleCount = "1";
  showRows(reportHistory, data.reports, (item) => {
    const row = el("div", undefined, "entry");
    row.append(
      reportFields(item),
      renderStatus(item)
    );
    return row;
  }, "Hisobotlar yo'q.");
  fitHistoryLists();
  const debtHistory = document.querySelector("#debts");
  debtHistory.classList.add("history-scroll");
  showRows(debtHistory, data.debts, renderDebtHistoryRow, "Qarzdorlik tarixi yo'q.");
  fitHistoryLists();
}

function renderRating(listId, ownId, topRows, ownRating) {
  const list = document.querySelector(`#${listId}`);
  list.replaceChildren();
  for (const item of topRows) {
    const row = el("div", undefined, `ranking-row ranking-place-${item.rank}`);
    const medal = ["🥇", "🥈", "🥉"][item.rank - 1] || "";
    row.append(
      el("span", `${medal} #${item.rank} · ${item.bot_name}`, "ranking-name"),
      el("span", `${Number(item.score).toFixed(2)} ball`, "ranking-score")
    );
    list.append(row);
  }
  if (!topRows.length) list.append(el("p", "Reyting uchun xodimlar yo'q.", "muted"));

  const own = document.querySelector(`#${ownId}`);
  own.replaceChildren();
  own.append(
    el("strong", `Sizning o'rningiz: #${ownRating.rank} · ${Number(ownRating.score).toFixed(2)} ball`),
    el(
      "p",
      `Karta ${money(ownRating.card_total_with_fee)} · Berildi ${money(ownRating.approved_giving_total)} · Hisobot ${money(ownRating.report_submission_total)} · Qarz ${money(ownRating.debt_balance)}`
    )
  );
}

function bindForm(formId, endpoint, makeBody, successText, validate) {
  document.querySelector(formId).addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    if (validate) {
      const validationMessage = validate(data);
      form.elements.amount.setCustomValidity(validationMessage);
      if (validationMessage) {
        form.elements.amount.reportValidity();
        return;
      }
    }
    statusText.className = "muted";
    try {
      const result = await api(endpoint, {
        method: "POST",
        body: JSON.stringify(makeBody(data))
      });
      statusText.textContent = result.notification_warning || successText;
      statusText.className = result.notification_warning ? "error" : "muted";
      form.reset();
      await loadDashboard();
    } catch (error) {
      statusText.textContent = error.message;
      statusText.className = "error";
    }
  });
}

bindForm("#card-form", "/employee/api/cards", (data) => ({
  card_number: digitsOnly(data.get("card_number")),
  cardholder: data.get("cardholder"),
  amount: Number(digitsOnly(data.get("amount")))
}), "Karta so'rovi yuborildi.", (data) => {
  const amountDigits = digitsOnly(data.get("amount"));
  return amountDigits && Number(amountDigits) < 10_000
    ? "Karta so'rovi uchun eng kam summa 10 000 so'm."
    : "";
});
bindForm("#giving-form", "/employee/api/givings", (data) => ({
  amount: Number(digitsOnly(data.get("amount"))),
  note: data.get("note")
}), "Summa tasdiqlashga yuborildi.");
bindForm("#report-form", "/employee/api/reports", (data) => ({
  work_date: data.get("work_date"),
  paynet: Number(digitsOnly(data.get("paynet"))),
  levy: Number(digitsOnly(data.get("levy"))),
  simcard: Number(digitsOnly(data.get("simcard"))),
  debt_payment: Number(digitsOnly(data.get("debt_payment"))),
  terminal: Number(digitsOnly(data.get("terminal"))),
  daily: Number(digitsOnly(data.get("daily"))),
  discount: Number(digitsOnly(data.get("discount"))),
  expense: Number(digitsOnly(data.get("expense"))),
  comment: data.get("comment")
}), "Hisobot admin ko'rib chiqishi uchun yuborildi.");

document.querySelector('#report-form [name="work_date"]').addEventListener("change", () => {
  loadDashboard().catch((error) => {
    statusText.textContent = error.message;
    statusText.className = "error";
  });
});

async function signIn() {
  if (!telegram?.initData) {
    greeting.textContent = "Telegram orqali oching";
    statusText.textContent = "Botdagi pastki Hisobot tugmasidan foydalaning.";
    return;
  }
  telegram.ready();
  telegram.expand();
  const login = await api("/auth/telegram", {
    method: "POST",
    body: JSON.stringify({ init_data: telegram.initData })
  });
  if (login.role !== "employee") throw new Error("Xodim akkaunti orqali oching.");
  const profile = await api("/employee/api/me");
  greeting.textContent = `Assalomu alaykum, ${profile.bot_name}!`;
  statusText.textContent = "Xodim akkauntingiz tasdiqlandi.";
  workspace.hidden = false;
  await loadDashboard();
}

signIn().catch((error) => {
  greeting.textContent = "Kirish amalga oshmadi";
  statusText.textContent = error.message || "Internetni tekshirib, ilovani qayta oching.";
  statusText.className = "error";
});
