// Hisobot CRM Client Application Logic

const state = {
  user: null,
  dashboard: null,
  employees: [],
  activeView: 'dashboard',
  cardFilter: 'all',
  givingFilter: 'all',
  reportFilter: 'all',
  reportEmployeeFilter: '',
  rankingPeriod: 'monthly',
  pendingRejectAction: null,
  pendingPinAction: null
};

// Utilities
function formatMoney(amount) {
  if (amount === null || amount === undefined || isNaN(amount)) return '0 so\'m';
  return Number(amount).toLocaleString('ru-RU').replace(/,/g, ' ') + ' so\'m';
}

function cleanDigits(val) {
  return String(val || '').replace(/\D/g, '');
}

function calculateCardFee(amount) {
  const num = Number(amount) || 0;
  if (num < 10000) return 0;
  return Math.floor((num * 103 + 99999) / 100000) * 1000;
}

function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : '⚠️';
  toast.innerHTML = `<span class="toast-icon">${icon}</span><span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(40px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Live Clock in Tashkent time (UTC+5)
function startLiveClock() {
  const el = document.getElementById('live-clock');
  function update() {
    const now = new Date();
    // Format to Tashkent timezone
    const timeStr = now.toLocaleTimeString('uz-UZ', {
      timeZone: 'Asia/Tashkent',
      hour12: false
    });
    el.textContent = `${timeStr} (UZT)`;
  }
  update();
  setInterval(update, 1000);
}

// Check initial authentication
async function checkAuth() {
  try {
    const res = await fetch('/crm/api/me', { credentials: 'same-origin' });
    const data = await res.json();
    if (data.authenticated) {
      state.user = data;
      showAppScreen();
      await loadDashboard();
    } else {
      showAuthScreen();
      await loadEmployeeSelectList();
    }
  } catch (err) {
    console.error('Auth tekshirishda xatolik:', err);
    showAuthScreen();
  }
}

function showAuthScreen() {
  document.getElementById('auth-screen').style.display = 'flex';
  document.getElementById('app-container').style.display = 'none';
}

function showAppScreen() {
  document.getElementById('auth-screen').style.display = 'none';
  document.getElementById('app-container').style.display = 'flex';
  
  // Set user profile info
  const name = state.user.user.name || 'Foydalanuvchi';
  const role = state.user.role;
  document.getElementById('user-display-name').textContent = name;
  document.getElementById('user-role-label').textContent = role === 'admin' ? 'Superadmin' : 'Xodim';
  document.getElementById('user-avatar').textContent = name.substring(0, 2).toUpperCase();
  document.getElementById('sidebar-role-tag').textContent = role === 'admin' ? 'BOSHQARUV PANELI' : 'XODIM KABINETI';

  // Role based visibility
  const isAdm = role === 'admin';
  document.getElementById('nav-item-employees').style.display = isAdm ? 'flex' : 'none';
  document.getElementById('admin-debt-form-container').style.display = isAdm ? 'block' : 'none';
  
  // Forms for employee
  document.getElementById('employee-card-form-container').style.display = isAdm ? 'none' : 'block';
  document.getElementById('employee-giving-form-container').style.display = isAdm ? 'none' : 'block';
  document.getElementById('employee-report-form-container').style.display = isAdm ? 'none' : 'block';

  // Hero greeting & actions
  document.getElementById('hero-greeting').textContent = `Assalomu alaykum, ${name}!`;
  renderHeroActions();
}

function renderHeroActions() {
  const container = document.getElementById('hero-actions-container');
  container.innerHTML = '';
  if (state.user.role === 'admin') {
    container.innerHTML = `
      <button class="btn-hero primary" onclick="switchView('employees')">+ Yangi xodim</button>
      <button class="btn-hero secondary" onclick="switchView('debts')">+ Qarz belgilash</button>
    `;
  } else {
    container.innerHTML = `
      <button class="btn-hero primary" onclick="switchView('cards')">+ Karta to'ldirish</button>
      <button class="btn-hero secondary" onclick="switchView('reports')">+ Kunlik hisobot</button>
    `;
  }
}

// Load Employee Select List for Login and Forms
async function loadEmployeeSelectList() {
  try {
    const res = await fetch('/crm/api/employees-list');
    if (!res.ok) return;
    const employees = await res.json();
    state.employees = employees;

    // Populate login dropdown
    const selectLogin = document.getElementById('employee-select-list');
    selectLogin.innerHTML = '<option value="">Ro\'yxatdan xodimni tanlang...</option>';
    employees.forEach(emp => {
      const opt = document.createElement('option');
      opt.value = emp.telegram_id;
      opt.textContent = `${emp.bot_name} (ID: ${emp.telegram_id})`;
      selectLogin.appendChild(opt);
    });

    // Populate debt employee select
    const selectDebt = document.getElementById('debt-employee-select');
    if (selectDebt) {
      selectDebt.innerHTML = '<option value="">Xodimni tanlang...</option>';
      employees.forEach(emp => {
        const opt = document.createElement('option');
        opt.value = emp.telegram_id;
        opt.textContent = `${emp.bot_name} (ID: ${emp.telegram_id})`;
        selectDebt.appendChild(opt);
      });
    }

    // Populate report filter select
    const selectReportFilter = document.getElementById('report-filter-employee');
    if (selectReportFilter) {
      selectReportFilter.innerHTML = '<option value="">Barcha xodimlar</option>';
      employees.forEach(emp => {
        const opt = document.createElement('option');
        opt.value = emp.telegram_id;
        opt.textContent = emp.bot_name;
        selectReportFilter.appendChild(opt);
      });
    }
  } catch (err) {
    console.error('Xodimlarni yuklashda xatolik:', err);
  }
}

// Load Dashboard Data
async function loadDashboard() {
  try {
    const res = await fetch('/crm/api/dashboard', { credentials: 'same-origin' });
    if (!res.ok) throw new Error('Dashboard ma\'lumotlarini yuklab bo\'lmadi');
    const result = await res.json();
    state.dashboard = result.data;

    await loadEmployeeSelectList();
    renderKPIs();
    renderCardsTable();
    renderGivingsTable();
    renderReportsTable();
    renderDebtsSection();
    if (state.user.role === 'admin') {
      renderEmployeesTable();
    }
    renderRankings();
    renderDashboardPendingOverview();
  } catch (err) {
    console.error('Dashboard xatolik:', err);
    showToast('Ma\'lumotlarni yuklashda xatolik yuz berdi', 'error');
  }
}

// Render KPI Cards
function renderKPIs() {
  const d = state.dashboard;
  if (!d) return;

  if (state.user.role === 'admin') {
    const stats = d.stats || {};
    document.getElementById('kpi-card-total').textContent = formatMoney(stats.today_approved_cards_total || 0);
    document.getElementById('kpi-card-sub').textContent = `Kutilmoqda: ${stats.pending_cards_count || 0} ta so'rov`;

    document.getElementById('kpi-giving-total').textContent = formatMoney(stats.today_approved_givings_total || 0);
    document.getElementById('kpi-giving-sub').textContent = `Kutilmoqda: ${stats.pending_givings_count || 0} ta so'rov`;

    document.getElementById('kpi-reports-count').textContent = `${stats.total_reports_count || 0} ta hisobot`;
    document.getElementById('kpi-reports-sub').textContent = `Kutilmoqda: ${stats.pending_reports_count || 0} ta`;

    document.getElementById('kpi-debt-balance').textContent = formatMoney(stats.total_debt_balance || 0);
    document.getElementById('kpi-debt-sub').textContent = `Faol xodimlar: ${stats.active_employees_count || 0} nafar`;

    // Badges on sidebar
    updateBadge('badge-pending-cards', stats.pending_cards_count);
    updateBadge('badge-pending-givings', stats.pending_givings_count);
    updateBadge('badge-pending-reports', stats.pending_reports_count);
  } else {
    // Employee perspective
    document.getElementById('kpi-card-total').textContent = formatMoney(d.card_total_with_fee || 0);
    document.getElementById('kpi-card-sub').textContent = 'Bugungi tasdiqlangan kartalar';

    document.getElementById('kpi-giving-total').textContent = formatMoney(d.approved_giving_total || 0);
    document.getElementById('kpi-giving-sub').textContent = 'Bugungi tasdiqlangan topshirish';

    const myReports = d.reports || [];
    document.getElementById('kpi-reports-count').textContent = `${myReports.length} ta hisobot`;
    const pendingMy = myReports.filter(r => r.status === 'pending').length;
    document.getElementById('kpi-reports-sub').textContent = pendingMy ? `${pendingMy} ta kutilmoqda` : 'Barchasi ko\'rib chiqilgan';

    document.getElementById('kpi-debt-balance').textContent = formatMoney(d.debt_balance || 0);
    document.getElementById('kpi-debt-sub').textContent = 'Sizning joriy qarzingiz';

    // Auto-populate report fields for employee
    const inputCardAuto = document.getElementById('input-report-card-auto');
    if (inputCardAuto) inputCardAuto.value = formatMoney(d.card_total_with_fee || 0);
    const inputGivingAuto = document.getElementById('input-report-giving-auto');
    if (inputGivingAuto) inputGivingAuto.value = formatMoney(d.approved_giving_total || 0);
    const inputDebtAuto = document.getElementById('input-report-debt-balance-auto');
    if (inputDebtAuto) inputDebtAuto.value = formatMoney(d.debt_balance || 0);

    const pendingCards = (d.cards || []).filter(c => c.status === 'pending').length;
    const pendingGivings = (d.givings || []).filter(g => g.status === 'pending').length;
    updateBadge('badge-pending-cards', pendingCards);
    updateBadge('badge-pending-givings', pendingGivings);
    updateBadge('badge-pending-reports', pendingMy);
  }
}

function updateBadge(elementId, count) {
  const el = document.getElementById(elementId);
  if (!el) return;
  if (count && count > 0) {
    el.textContent = count;
    el.style.display = 'inline-block';
  } else {
    el.style.display = 'none';
  }
}

// Render Dashboard Pending Overview Table
function renderDashboardPendingOverview() {
  const tbody = document.getElementById('dashboard-pending-tbody');
  tbody.innerHTML = '';
  const d = state.dashboard;
  if (!d) return;

  const pendingItems = [];

  (d.cards || []).forEach(c => {
    if (c.status === 'pending') {
      pendingItems.push({
        type: 'Karta so\'rovi',
        icon: '💳',
        id: c.id,
        employee: c.bot_name || c.employee_id,
        details: `${c.card_number} (${c.cardholder})`,
        amount: calculateCardFee(c.amount),
        raw: c,
        category: 'card'
      });
    }
  });

  (d.givings || []).forEach(g => {
    if (g.status === 'pending') {
      pendingItems.push({
        type: 'Pul topshirish',
        icon: '💵',
        id: g.id,
        employee: g.bot_name || g.employee_id,
        details: g.note || 'Izohsiz',
        amount: g.amount,
        raw: g,
        category: 'giving'
      });
    }
  });

  (d.reports || []).forEach(r => {
    if (r.status === 'pending') {
      const total = (
        Number(r.paynet) + Number(r.card_total) + Number(r.levy) + Number(r.daily)
        - Number(r.terminal) - Number(r.giving_total) - Number(r.discount) - Number(r.expense) + Number(r.debt_payment)
      );
      pendingItems.push({
        type: 'Kunlik hisobot',
        icon: '📋',
        id: r.id,
        employee: r.bot_name || r.employee_id,
        details: `Sana: ${r.work_date}`,
        amount: total,
        raw: r,
        category: 'report'
      });
    }
  });

  if (pendingItems.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-dim); padding: 24px;">Hozircha kutilayotgan so\'rovlar yo\'q. Barcha amallar bajarilgan!</td></tr>';
    return;
  }

  pendingItems.slice(0, 10).forEach(item => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${item.icon} ${item.type}</strong></td>
      <td>${item.employee}</td>
      <td>${item.details}</td>
      <td><strong>${formatMoney(item.amount)}</strong></td>
      <td><span class="badge badge-pending">⏳ Kutilmoqda</span></td>
      <td>
        ${state.user.role === 'admin' ? `
          <div class="btn-action-group">
            <button class="btn-sm approve" onclick="decideItem('${item.category}', ${item.id}, true)">Tasdiqlash</button>
            <button class="btn-sm reject" onclick="openRejectModal('${item.category}', ${item.id})">Rad etish</button>
          </div>
        ` : '<span style="color: var(--text-dim);">Admin tekshiruvi kutilmoqda</span>'}
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// Render Cards Table
function renderCardsTable() {
  const tbody = document.getElementById('cards-tbody');
  tbody.innerHTML = '';
  const d = state.dashboard;
  if (!d) return;

  let cards = d.cards || [];
  if (state.cardFilter !== 'all') {
    cards = cards.filter(c => c.status === state.cardFilter);
  }

  if (cards.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: var(--text-dim); padding: 24px;">Karta to\'ldirish so\'rovlari topilmadi.</td></tr>';
    return;
  }

  cards.forEach(card => {
    const tr = document.createElement('tr');
    const feeTotal = calculateCardFee(card.amount);
    const dateFormatted = (card.created_at || '').substring(0, 16).replace('T', ' ');
    const isPending = card.status === 'pending';
    
    let statusBadge = '<span class="badge badge-pending">⏳ Kutilmoqda</span>';
    if (card.status === 'approved') statusBadge = '<span class="badge badge-approved">✅ Tasdiqlandi</span>';
    if (card.status === 'rejected') statusBadge = `<span class="badge badge-rejected" title="${card.decision_reason || ''}">❌ Rad etildi</span>`;

    let actions = '-';
    if (state.user.role === 'admin') {
      if (isPending) {
        actions = `
          <div class="btn-action-group">
            <button class="btn-sm approve" onclick="decideItem('card', ${card.id}, true)">Tasdiqlash</button>
            <button class="btn-sm reject" onclick="openRejectModal('card', ${card.id})">Rad etish</button>
          </div>
        `;
      } else {
        const toggleText = card.status === 'approved' ? 'Rad etishga o\'zgartirish' : 'Tasdiqlashga o\'zgartirish';
        const toggleApprove = card.status !== 'approved';
        actions = `
          <button class="btn-sm secondary" onclick="decideItem('card', ${card.id}, ${toggleApprove})">${toggleText}</button>
        `;
      }
    } else if (card.decision_reason) {
      actions = `<span style="font-size: 12px; color: var(--danger-text);">${card.decision_reason}</span>`;
    }

    tr.innerHTML = `
      <td>#${card.id}</td>
      <td style="font-size: 12px; color: var(--text-muted);">${dateFormatted}</td>
      <td><strong>${card.bot_name || card.employee_id}</strong></td>
      <td>
        <span style="font-family: var(--font-mono);">${card.card_number}</span>
        <button class="copy-btn" title="Karta raqamidan nusxa olish" onclick="copyToClipboard('${card.card_number}')">📋</button>
      </td>
      <td>${card.cardholder}</td>
      <td>${formatMoney(card.amount)}</td>
      <td><strong style="color: #a5b4fc;">${formatMoney(feeTotal)}</strong></td>
      <td>${statusBadge}</td>
      <td>${actions}</td>
    `;
    tbody.appendChild(tr);
  });
}

// Render Givings Table
function renderGivingsTable() {
  const tbody = document.getElementById('givings-tbody');
  tbody.innerHTML = '';
  const d = state.dashboard;
  if (!d) return;

  let givings = d.givings || [];
  if (state.givingFilter !== 'all') {
    givings = givings.filter(g => g.status === state.givingFilter);
  }

  if (givings.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 24px;">Topshirilgan summalar topilmadi.</td></tr>';
    return;
  }

  givings.forEach(giving => {
    const tr = document.createElement('tr');
    const isPending = giving.status === 'pending';
    let statusBadge = '<span class="badge badge-pending">⏳ Kutilmoqda</span>';
    if (giving.status === 'approved') statusBadge = '<span class="badge badge-approved">✅ Tasdiqlandi</span>';
    if (giving.status === 'rejected') statusBadge = `<span class="badge badge-rejected" title="${giving.decision_reason || ''}">❌ Rad etildi</span>`;

    let actions = '-';
    if (state.user.role === 'admin' && isPending) {
      actions = `
        <div class="btn-action-group">
          <button class="btn-sm approve" onclick="decideItem('giving', ${giving.id}, true)">Tasdiqlash</button>
          <button class="btn-sm reject" onclick="openRejectModal('giving', ${giving.id})">Rad etish</button>
        </div>
      `;
    } else if (giving.decision_reason) {
      actions = `<span style="font-size: 12px; color: var(--danger-text);">${giving.decision_reason}</span>`;
    }

    tr.innerHTML = `
      <td>#${giving.id}</td>
      <td>${giving.work_date}</td>
      <td><strong>${giving.bot_name || giving.employee_id}</strong></td>
      <td><strong>${formatMoney(giving.amount)}</strong></td>
      <td style="color: var(--text-muted);">${giving.note || '-'}</td>
      <td>${statusBadge}</td>
      <td>${actions}</td>
    `;
    tbody.appendChild(tr);
  });
}

// Render Reports Table
function renderReportsTable() {
  const tbody = document.getElementById('reports-tbody');
  tbody.innerHTML = '';
  const d = state.dashboard;
  if (!d) return;

  let reports = d.reports || [];
  if (state.reportFilter !== 'all') {
    reports = reports.filter(r => r.status === state.reportFilter);
  }
  if (state.reportEmployeeFilter) {
    reports = reports.filter(r => String(r.employee_id) === String(state.reportEmployeeFilter));
  }

  if (reports.length === 0) {
    tbody.innerHTML = '<tr><td colspan="14" style="text-align: center; color: var(--text-dim); padding: 24px;">Kunlik hisobotlar topilmadi.</td></tr>';
    return;
  }

  reports.forEach(report => {
    const tr = document.createElement('tr');
    const total = (
      Number(report.paynet) + Number(report.card_total) + Number(report.levy) + Number(report.daily)
      - Number(report.terminal) - Number(report.giving_total) - Number(report.discount) - Number(report.expense) + Number(report.debt_payment)
    );
    const isPending = report.status === 'pending';

    let statusBadge = '<span class="badge badge-pending">⏳ Kutilmoqda</span>';
    if (report.status === 'approved') statusBadge = '<span class="badge badge-approved">✅ Tasdiqlandi</span>';
    if (report.status === 'rejected') statusBadge = `<span class="badge badge-rejected" title="${report.decision_reason || ''}">❌ Rad etildi</span>`;

    let actions = '-';
    if (state.user.role === 'admin' && isPending) {
      actions = `
        <div class="btn-action-group">
          <button class="btn-sm approve" onclick="decideItem('report', ${report.id}, true)">Tasdiqlash</button>
          <button class="btn-sm reject" onclick="openRejectModal('report', ${report.id})">Rad etish</button>
        </div>
      `;
    } else if (report.decision_reason) {
      actions = `<span style="font-size: 12px; color: var(--danger-text);">${report.decision_reason}</span>`;
    }

    tr.innerHTML = `
      <td><strong>${report.work_date}</strong></td>
      <td>${report.bot_name || report.employee_id}</td>
      <td>${formatMoney(report.paynet)}</td>
      <td style="color: #a5b4fc;">${formatMoney(report.card_total)}</td>
      <td>${formatMoney(report.levy)}</td>
      <td>${report.simcard} dona</td>
      <td style="color: #34d399;">${formatMoney(report.giving_total)}</td>
      <td>${formatMoney(report.terminal)}</td>
      <td>${formatMoney(report.daily)}</td>
      <td style="color: #fb7185;">${formatMoney(report.expense)}</td>
      <td>${formatMoney(report.debt_payment)}</td>
      <td><strong style="color: #38bdf8;">${formatMoney(total)}</strong></td>
      <td>${statusBadge}</td>
      <td>${actions}</td>
    `;
    tbody.appendChild(tr);
  });
}

// Render Debts Section
function renderDebtsSection() {
  const d = state.dashboard;
  if (!d) return;

  // Render debt balances cards
  const grid = document.getElementById('debt-balances-grid');
  grid.innerHTML = '';
  const balances = d.debt_balances || [];
  if (state.user.role === 'employee') {
    grid.innerHTML = `
      <div class="kpi-card" style="border-color: ${d.debt_balance > 0 ? 'var(--accent-rose)' : 'var(--accent-emerald)'};">
        <div class="kpi-top">
          <span class="kpi-label">Sizning qarz balansingiz</span>
          <div class="kpi-icon rose">💰</div>
        </div>
        <div class="kpi-value">${formatMoney(d.debt_balance || 0)}</div>
        <div class="kpi-sub">${d.debt_balance > 0 ? 'Qarzdorlik mavjud' : 'Qarzdorlik yo\'q'}</div>
      </div>
    `;
  } else {
    if (balances.length === 0) {
      grid.innerHTML = '<p style="color: var(--text-dim); padding: 12px;">Hozircha hech qaysi xodimda qarz qayd etilmagan.</p>';
    } else {
      balances.forEach(b => {
        const emp = (state.employees || []).find(e => e.telegram_id === b.employee_id);
        const name = emp ? emp.bot_name : `Xodim ID ${b.employee_id}`;
        const hasDebt = b.balance > 0;
        const card = document.createElement('div');
        card.className = 'kpi-card';
        card.innerHTML = `
          <div class="kpi-top">
            <span class="kpi-label">${name}</span>
            <span style="font-size: 11px; color: var(--text-dim);">${b.employee_id}</span>
          </div>
          <div class="kpi-value" style="color: ${hasDebt ? '#fb7185' : '#34d399'};">${formatMoney(b.balance)}</div>
          <div class="kpi-sub">${hasDebt ? '⚠️ Qarz qoldig\'i' : '✅ Qarz to\'liq yopilgan'}</div>
        `;
        grid.appendChild(card);
      });
    }
  }

  // Render debts ledger audit table
  const tbody = document.getElementById('debts-tbody');
  tbody.innerHTML = '';
  const debts = d.debts || [];
  if (debts.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-dim); padding: 24px;">Qarz daftari yozuvlari topilmadi.</td></tr>';
    return;
  }
  debts.slice(0, 30).forEach(entry => {
    const tr = document.createElement('tr');
    const isNegative = entry.amount_delta < 0;
    const deltaFormatted = isNegative ? `- ${formatMoney(Math.abs(entry.amount_delta))}` : `+ ${formatMoney(entry.amount_delta)}`;
    const color = isNegative ? '#34d399' : '#fb7185';
    tr.innerHTML = `
      <td style="font-size: 12px; color: var(--text-muted);">${(entry.created_at || '').substring(0, 16).replace('T', ' ')}</td>
      <td><strong>${entry.employee_id}</strong></td>
      <td><strong style="color: ${color};">${deltaFormatted}</strong></td>
      <td>${entry.description}</td>
    `;
    tbody.appendChild(tr);
  });
}

// Render Employees Table (Admin only)
function renderEmployeesTable() {
  const tbody = document.getElementById('employees-tbody');
  tbody.innerHTML = '';
  const emps = state.dashboard.employees || [];
  if (emps.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--text-dim); padding: 24px;">Faol xodimlar topilmadi.</td></tr>';
    return;
  }

  emps.forEach(emp => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${emp.telegram_id}</strong></td>
      <td>${emp.bot_name}</td>
      <td><span style="font-family: var(--font-mono); background: var(--bg-surface); padding: 2px 8px; border-radius: 4px;">${emp.pin || '1234'}</span></td>
      <td><span class="badge badge-approved">Faol</span></td>
      <td>
        <div class="btn-action-group">
          <button class="btn-sm secondary" onclick="openPinModal(${emp.telegram_id}, '${emp.bot_name}', '${emp.pin || '1234'}')">PIN o'zgartirish</button>
          <button class="btn-sm reject" onclick="dismissEmployee(${emp.telegram_id}, '${emp.bot_name}')">Ishdan bo'shatish</button>
        </div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// Render Rankings & Podium
function renderRankings() {
  const d = state.dashboard;
  if (!d || !d.ratings) return;

  const list = d.ratings[state.rankingPeriod] || [];
  const podium = document.getElementById('podium-container');
  podium.innerHTML = '';

  const top1 = list.find(r => Number(r.rank) === 1);
  const top2 = list.find(r => Number(r.rank) === 2);
  const top3 = list.find(r => Number(r.rank) === 3);

  // Render Podium 2 - 1 - 3 order
  if (top2) podium.appendChild(createPodiumCard(top2, 2, '🥈'));
  if (top1) podium.appendChild(createPodiumCard(top1, 1, '👑'));
  if (top3) podium.appendChild(createPodiumCard(top3, 3, '🥉'));

  // Render Full Table
  const tbody = document.getElementById('rankings-tbody');
  tbody.innerHTML = '';
  if (list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: var(--text-dim); padding: 24px;">Ushbu davr uchun reyting ma\'lumotlari yo\'q.</td></tr>';
    return;
  }

  list.forEach(item => {
    const tr = document.createElement('tr');
    const isTop = Number(item.rank) <= 3;
    const rankIcon = item.rank === 1 ? '🥇' : item.rank === 2 ? '🥈' : item.rank === 3 ? '🥉' : `${item.rank}-o'rin`;
    tr.innerHTML = `
      <td><strong>${rankIcon}</strong></td>
      <td><strong>${item.bot_name}</strong></td>
      <td><strong style="color: #fbbf24; font-size: 15px;">${Number(item.score).toFixed(2)} ball</strong></td>
      <td>${formatMoney(item.card_total_with_fee)}</td>
      <td>${formatMoney(item.approved_giving_total)}</td>
      <td>${formatMoney(item.report_submission_total)}</td>
      <td style="color: #fb7185;">${formatMoney(item.debt_balance)}</td>
    `;
    tbody.appendChild(tr);
  });
}

function createPodiumCard(item, rank, icon) {
  const div = document.createElement('div');
  div.className = `podium-card rank-${rank}`;
  div.innerHTML = `
    <div class="podium-medal">${icon}</div>
    <div class="podium-name">${item.bot_name}</div>
    <div class="podium-score">${Number(item.score).toFixed(2)} ball</div>
    <div style="font-size: 11px; color: var(--text-dim); margin-top: 6px;">${rank}-o'rin</div>
  `;
  return div;
}

// Navigation View Switcher
function switchView(viewName) {
  state.activeView = viewName;
  document.querySelectorAll('.view-section').forEach(sec => sec.classList.remove('active'));
  const target = document.getElementById(`view-${viewName}`);
  if (target) target.classList.add('active');

  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.toggle('active', item.dataset.view === viewName);
  });

  const titles = {
    dashboard: 'Boshqaruv Paneli',
    cards: 'Karta To\'ldirish So\'rovlari',
    givings: 'Berilgan Pullar Nazorati',
    reports: 'Kunlik Hisobotlar Nazorati',
    debts: 'Qarzdorlik Daftari',
    employees: 'Xodimlar Boshqaruvi',
    rankings: 'Reyting va Leaderboard'
  };
  document.getElementById('topbar-page-title').textContent = titles[viewName] || 'Hisobot CRM';
  document.getElementById('topbar-breadcrumb').textContent = `Hisobot CRM > ${titles[viewName] || ''}`;

  // Mobile sidebar close
  document.getElementById('app-sidebar').classList.remove('open');
}

// Event Listeners Initialization
document.addEventListener('DOMContentLoaded', () => {
  startLiveClock();
  checkAuth();

  // Sidebar navigation click
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const view = item.dataset.view;
      if (view) switchView(view);
    });
  });

  // Mobile sidebar toggle
  document.getElementById('sidebar-toggle').addEventListener('click', () => {
    document.getElementById('app-sidebar').classList.toggle('open');
  });

  // Auth Switcher Tabs
  const tabAdmin = document.getElementById('tab-btn-admin');
  const tabEmp = document.getElementById('tab-btn-employee');
  const formAdmin = document.getElementById('admin-login-form');
  const formEmp = document.getElementById('employee-login-form');

  tabAdmin.addEventListener('click', () => {
    tabAdmin.classList.add('active');
    tabEmp.classList.remove('active');
    formAdmin.style.display = 'flex';
    formEmp.style.display = 'none';
    document.getElementById('auth-error').style.display = 'none';
  });

  tabEmp.addEventListener('click', () => {
    tabEmp.classList.add('active');
    tabAdmin.classList.remove('active');
    formEmp.style.display = 'flex';
    formAdmin.style.display = 'none';
    document.getElementById('auth-error').style.display = 'none';
  });

  // Quick Demo Buttons
  document.getElementById('quick-demo-admin').addEventListener('click', async () => {
    try {
      const res = await fetch('/crm/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ role: 'admin', username: 'admin', password: 'admin123' })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Kirish amalga oshmadi');
      showToast('Superadmin sifatida kirdingiz', 'success');
      await checkAuth();
    } catch (err) {
      document.getElementById('auth-error').textContent = err.message;
      document.getElementById('auth-error').style.display = 'block';
    }
  });

  document.getElementById('quick-demo-employee').addEventListener('click', async () => {
    try {
      if (!state.employees.length) await loadEmployeeSelectList();
      const firstEmp = state.employees[0];
      if (!firstEmp) throw new Error('Hozircha tizimda xodimlar yo\'q. Avval admin sifatida kiring.');
      const res = await fetch('/crm/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ role: 'employee', employee_id: firstEmp.telegram_id, pin: '1234' })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Kirish amalga oshmadi');
      showToast(`${firstEmp.bot_name} sifatida kirdingiz`, 'success');
      await checkAuth();
    } catch (err) {
      document.getElementById('auth-error').textContent = err.message;
      document.getElementById('auth-error').style.display = 'block';
    }
  });

  // Admin Login Form Submit
  formAdmin.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(formAdmin);
    try {
      const res = await fetch('/crm/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          role: 'admin',
          username: fd.get('username'),
          password: fd.get('password')
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Login yoki parol noto\'g\'ri');
      showToast('Superadmin sifatida tasdiqlandingiz', 'success');
      await checkAuth();
    } catch (err) {
      document.getElementById('auth-error').textContent = err.message;
      document.getElementById('auth-error').style.display = 'block';
    }
  });

  // Employee Login Form Submit
  formEmp.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(formEmp);
    const empId = fd.get('employee_id') || fd.get('manual_employee_id');
    const pin = fd.get('pin');
    try {
      const res = await fetch('/crm/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({
          role: 'employee',
          employee_id: Number(empId),
          pin: pin
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Xodim ID yoki PIN noto\'g\'ri');
      showToast('Xodim sifatida tizimga kirdingiz', 'success');
      await checkAuth();
    } catch (err) {
      document.getElementById('auth-error').textContent = err.message;
      document.getElementById('auth-error').style.display = 'block';
    }
  });

  // Logout
  document.getElementById('btn-logout').addEventListener('click', async () => {
    try {
      await fetch('/crm/api/logout', { method: 'POST', credentials: 'same-origin' });
      state.user = null;
      showToast('Tizimdan chiqdingiz', 'info');
      showAuthScreen();
      await loadEmployeeSelectList();
    } catch (err) {
      console.error(err);
    }
  });

  // Filter buttons listeners
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.target;
      const status = btn.dataset.filterStatus;
      if (target === 'cards') {
        state.cardFilter = status;
        document.querySelectorAll('[data-target="cards"]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderCardsTable();
      } else if (target === 'givings') {
        state.givingFilter = status;
        document.querySelectorAll('[data-target="givings"]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderGivingsTable();
      } else if (target === 'reports') {
        state.reportFilter = status;
        document.querySelectorAll('[data-target="reports"]').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderReportsTable();
      }
    });
  });

  // Report employee filter dropdown
  const repEmpFilter = document.getElementById('report-filter-employee');
  if (repEmpFilter) {
    repEmpFilter.addEventListener('change', (e) => {
      state.reportEmployeeFilter = e.target.value;
      renderReportsTable();
    });
  }

  // Ranking Period buttons
  const btnRankMonthly = document.getElementById('btn-rank-monthly');
  const btnRankOverall = document.getElementById('btn-rank-overall');
  btnRankMonthly.addEventListener('click', () => {
    state.rankingPeriod = 'monthly';
    btnRankMonthly.classList.add('active');
    btnRankOverall.classList.remove('active');
    renderRankings();
  });
  btnRankOverall.addEventListener('click', () => {
    state.rankingPeriod = 'overall';
    btnRankOverall.classList.add('active');
    btnRankMonthly.classList.remove('active');
    renderRankings();
  });

  // ================= FORM SUBMISSIONS =================
  // Card Number auto-format (spaces every 4 digits)
  const cardInput = document.getElementById('input-card-number');
  cardInput.addEventListener('input', (e) => {
    const raw = e.target.value.replace(/\D/g, '').slice(0, 16);
    e.target.value = raw.replace(/(\d{4})(?=\d)/g, '$1 ');
  });

  // Card Amount auto-format and real-time fee calculation
  const cardAmountInput = document.getElementById('input-card-amount');
  cardAmountInput.addEventListener('input', (e) => {
    const raw = cleanDigits(e.target.value);
    e.target.value = raw ? Number(raw).toLocaleString('ru-RU').replace(/,/g, ' ') : '';
    const feeTotal = calculateCardFee(raw);
    document.getElementById('card-fee-amount').textContent = formatMoney(feeTotal);
  });

  // Submit Card Request
  document.getElementById('form-submit-card').addEventListener('submit', async (e) => {
    e.preventDefault();
    const rawNum = cleanDigits(cardInput.value);
    const cardholder = document.getElementById('input-cardholder').value.trim();
    const amount = Number(cleanDigits(cardAmountInput.value));

    if (rawNum.length !== 16) {
      showToast('Karta raqami 16 ta raqam bo\'lishi shart', 'error');
      return;
    }
    if (amount < 10000) {
      showToast('Karta so\'rovi summasi kamida 10 000 so\'m bo\'lishi kerak', 'error');
      return;
    }

    try {
      const res = await fetch('/employee/api/cards', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        body: JSON.stringify({
          card_number: rawNum,
          cardholder: cardholder,
          amount: amount
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'So\'rovni yuborib bo\'lmadi');
      if (data.notification_warning) {
        showToast(data.notification_warning, 'warning');
      } else {
        showToast('Karta to\'ldirish so\'rovi muvaffaqiyatli yuborildi', 'success');
      }
      document.getElementById('form-submit-card').reset();
      document.getElementById('card-fee-amount').textContent = '0 so\'m';
      await loadDashboard();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  // Giving Amount auto-format
  const givingAmountInput = document.getElementById('input-giving-amount');
  givingAmountInput.addEventListener('input', (e) => {
    const raw = cleanDigits(e.target.value);
    e.target.value = raw ? Number(raw).toLocaleString('ru-RU').replace(/,/g, ' ') : '';
  });

  // Submit Giving Form
  document.getElementById('form-submit-giving').addEventListener('submit', async (e) => {
    e.preventDefault();
    const amount = Number(cleanDigits(givingAmountInput.value));
    const note = document.getElementById('input-giving-note').value.trim();

    if (!amount || amount <= 0) {
      showToast('Summa 0 dan katta bo\'lishi shart', 'error');
      return;
    }

    try {
      const res = await fetch('/employee/api/givings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        body: JSON.stringify({ amount: amount, note: note })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Topshirish amalga oshmadi');
      showToast('Berilgan summa yuborildi va admin tasdig\'iga tushdi', 'success');
      document.getElementById('form-submit-giving').reset();
      await loadDashboard();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  // Daily Report calculations and formatting
  const reportDateInput = document.getElementById('input-report-date');
  if (reportDateInput) {
    reportDateInput.value = new Date().toISOString().split('T')[0];
  }

  const reportNumericFields = [
    'input-report-paynet', 'input-report-levy', 'input-report-simcard',
    'input-report-debt-payment', 'input-report-terminal', 'input-report-daily',
    'input-report-discount', 'input-report-expense'
  ];

  reportNumericFields.forEach(id => {
    const input = document.getElementById(id);
    if (!input) return;
    input.addEventListener('input', (e) => {
      const raw = cleanDigits(e.target.value);
      e.target.value = raw ? Number(raw).toLocaleString('ru-RU').replace(/,/g, ' ') : '';
      recalculateReportTotal();
    });
  });

  function recalculateReportTotal() {
    function getVal(id) {
      return Number(cleanDigits(document.getElementById(id).value)) || 0;
    }

    const paynet = getVal('input-report-paynet');
    const levy = getVal('input-report-levy');
    const debtPayment = getVal('input-report-debt-payment');
    const terminal = getVal('input-report-terminal');
    const daily = getVal('input-report-daily');
    const discount = getVal('input-report-discount');
    const expense = getVal('input-report-expense');

    const cardTotal = state.dashboard ? (state.dashboard.card_total_with_fee || 0) : 0;
    const givingTotal = state.dashboard ? (state.dashboard.approved_giving_total || 0) : 0;

    const total = paynet + cardTotal + levy + daily + debtPayment - (terminal + givingTotal + discount + expense);
    document.getElementById('report-total-calculated').textContent = formatMoney(total);
  }

  // Submit Daily Report
  document.getElementById('form-submit-report').addEventListener('submit', async (e) => {
    e.preventDefault();
    function getVal(id) {
      return Number(cleanDigits(document.getElementById(id).value)) || 0;
    }

    const payload = {
      work_date: reportDateInput.value,
      paynet: getVal('input-report-paynet'),
      levy: getVal('input-report-levy'),
      simcard: getVal('input-report-simcard'),
      debt_payment: getVal('input-report-debt-payment'),
      terminal: getVal('input-report-terminal'),
      daily: getVal('input-report-daily'),
      discount: getVal('input-report-discount'),
      expense: getVal('input-report-expense'),
      comment: document.getElementById('input-report-comment').value.trim()
    };

    try {
      const res = await fetch('/employee/api/reports', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Hisobotni saqlab bo\'lmadi');
      if (data.notification_warning) {
        showToast(data.notification_warning, 'warning');
      } else {
        showToast('Kunlik hisobot topshirildi!', 'success');
      }
      document.getElementById('form-submit-report').reset();
      reportDateInput.value = new Date().toISOString().split('T')[0];
      await loadDashboard();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  // Admin Add Employee Form Submit
  const formAddEmp = document.getElementById('form-submit-employee');
  if (formAddEmp) {
    formAddEmp.addEventListener('submit', async (e) => {
      e.preventDefault();
      const telegramId = Number(document.getElementById('input-emp-telegram-id').value);
      const botName = document.getElementById('input-emp-name').value.trim();
      const pin = document.getElementById('input-emp-pin').value.trim() || '1234';

      try {
        const res = await fetch('/admin/api/employees', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
          },
          credentials: 'same-origin',
          body: JSON.stringify({ telegram_id: telegramId, bot_name: botName, pin: pin })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Xodimni qo\'shib bo\'lmadi');
        showToast(`${botName} ro'yxatga olindi`, 'success');
        formAddEmp.reset();
        await loadDashboard();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  // Admin Add Debt Form Submit
  const formAddDebt = document.getElementById('form-submit-debt');
  if (formAddDebt) {
    const debtAmountInput = document.getElementById('input-debt-amount');
    debtAmountInput.addEventListener('input', (e) => {
      const raw = cleanDigits(e.target.value);
      e.target.value = raw ? Number(raw).toLocaleString('ru-RU').replace(/,/g, ' ') : '';
    });

    formAddDebt.addEventListener('submit', async (e) => {
      e.preventDefault();
      const empId = Number(document.getElementById('debt-employee-select').value);
      const amount = Number(cleanDigits(debtAmountInput.value));
      const description = document.getElementById('input-debt-description').value.trim();

      if (!empId || !amount || !description) {
        showToast('Barcha maydonlarni to\'ldiring', 'error');
        return;
      }

      try {
        const res = await fetch(`/admin/api/employees/${empId}/debt`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest'
          },
          credentials: 'same-origin',
          body: JSON.stringify({ amount: amount, description: description })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Qarzni kiritib bo\'lmadi');
        showToast('Qarzdorlik muvaffaqiyatli qayd etildi', 'success');
        formAddDebt.reset();
        await loadDashboard();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });
  }

  // Reject Modal Confirm
  document.getElementById('modal-reject-confirm-btn').addEventListener('click', async () => {
    if (!state.pendingRejectAction) return;
    const reason = document.getElementById('modal-reject-reason').value.trim();
    if (!reason) {
      showToast('Rad etish sababi kiritilishi shart!', 'warning');
      return;
    }
    const { category, id } = state.pendingRejectAction;
    closeRejectModal();
    await decideItem(category, id, false, reason);
  });

  // PIN Modal Confirm
  document.getElementById('modal-pin-confirm-btn').addEventListener('click', async () => {
    if (!state.pendingPinAction) return;
    const newPin = document.getElementById('modal-pin-input').value.trim();
    if (!newPin) {
      showToast('PIN bo\'sh bo\'lishi mumkin emas', 'warning');
      return;
    }
    const empId = state.pendingPinAction.telegramId;
    closePinModal();
    try {
      const res = await fetch(`/crm/api/employees/${empId}/pin`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin',
        body: JSON.stringify({ pin: newPin })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'PIN kodni yangilab bo\'lmadi');
      showToast('PIN kod muvaffaqiyatli yangilandi', 'success');
      await loadDashboard();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });
});

// Admin Approve / Reject Handler
async function decideItem(category, id, approved, reason = '') {
  let endpoint = '';
  if (category === 'card') endpoint = `/admin/api/cards/${id}/decision`;
  else if (category === 'giving') endpoint = `/admin/api/givings/${id}/decision`;
  else if (category === 'report') endpoint = `/admin/api/reports/${id}/decision`;

  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest'
      },
      credentials: 'same-origin',
      body: JSON.stringify({ approved: approved, reason: reason })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Qarorni saqlab bo\'lmadi');
    const msg = approved ? 'So\'rov tasdiqlandi ✅' : 'So\'rov rad etildi ❌';
    if (data.notification_warning) {
      showToast(`${msg} (${data.notification_warning})`, 'warning');
    } else {
      showToast(msg, approved ? 'success' : 'info');
    }
    await loadDashboard();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// Admin Dismiss Employee
async function dismissEmployee(telegramId, name) {
  if (!confirm(`${name} (ID: ${telegramId}) ishdan bo'shatilsinmi? Uning kirishi darhol bloklanadi.`)) {
    return;
  }
  try {
    const res = await fetch(`/admin/api/employees/${telegramId}/dismiss`, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin'
    });
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || 'Ishdan bo\'shatib bo\'lmadi');
    }
    showToast(`${name} ishdan bo'shatildi va bloklandi`, 'warning');
    await loadDashboard();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// Modal Handlers
function openRejectModal(category, id) {
  state.pendingRejectAction = { category, id };
  document.getElementById('modal-reject-reason').value = '';
  document.getElementById('modal-reject').classList.add('active');
}

function closeRejectModal() {
  state.pendingRejectAction = null;
  document.getElementById('modal-reject').classList.remove('active');
}

function openPinModal(telegramId, name, currentPin) {
  state.pendingPinAction = { telegramId };
  document.getElementById('modal-pin-label').textContent = `${name} (ID: ${telegramId}) uchun yangi PIN:`;
  document.getElementById('modal-pin-input').value = currentPin || '';
  document.getElementById('modal-pin').classList.add('active');
}

function closePinModal() {
  state.pendingPinAction = null;
  document.getElementById('modal-pin').classList.remove('active');
}

// Copy to Clipboard
function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast(`Karta raqami nusxalandi: ${text}`, 'success');
  }).catch(() => {
    showToast('Nusxalashda xatolik', 'error');
  });
}
