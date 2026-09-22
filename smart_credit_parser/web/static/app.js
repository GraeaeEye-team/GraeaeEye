// State variables
let currentSessionId = null;
let currentInspection = null;
let currentMapping = null;
let currentDryRun = null;
let currentRole = "UNDERWRITER";

document.addEventListener("DOMContentLoaded", () => {
  setupDragAndDrop();
  onRoleChange();
});

function onRoleChange() {
  currentRole = document.getElementById("userRoleSelect").value;
  updateCommitButtonState();
}

function updateCommitButtonState() {
  const commitBtn = document.getElementById("commitBtn");
  if (!commitBtn) return;

  if (currentRole === "ANALYST") {
    commitBtn.disabled = true;
    commitBtn.title = "Роль ANALYST может только запускать предпросмотр. Для записи в БД переключитесь на UNDERWRITER.";
    commitBtn.innerText = "Подтвердить запись (Требуется роль Underwriter / Admin)";
    return;
  }

  if (currentDryRun && currentDryRun.rows_accepted === 0) {
    commitBtn.disabled = true;
    commitBtn.title = "Невозможно зафиксировать: нет валидных строк (0 валидных записей). Проверьте целевую таблицу или сопоставление на Шаге 2.";
    commitBtn.innerText = "Запись заблокирована (0 валидных строк) — проверьте Шаг 2";
    return;
  }

  commitBtn.disabled = false;
  commitBtn.title = "";
  commitBtn.innerText = "Подтвердить и записать в базу данных →";
}

function setupDragAndDrop() {
  const dropZone = document.getElementById("dropZone");

  ["dragenter", "dragover"].forEach((event) => {
    dropZone.addEventListener(event, (e) => {
      e.preventDefault();
      dropZone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((event) => {
    dropZone.addEventListener(event, (e) => {
      e.preventDefault();
      dropZone.classList.remove("dragover");
    });
  });

  dropZone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      uploadFile(files[0]);
    }
  });
}

function handleFileSelected(event) {
  const file = event.target.files[0];
  if (file) {
    uploadFile(file);
  }
}

async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  try {
    const resp = await fetch("/api/upload", {
      method: "POST",
      headers: {
        "x-user-id": "demo_user",
        "x-user-role": currentRole,
      },
      body: formData,
    });

    if (!resp.ok) {
      const err = await resp.json();
      alert("Ошибка при загрузке: " + (err.detail || "Неизвестная ошибка"));
      return;
    }

    currentInspection = await resp.json();
    currentSessionId = currentInspection.session_id;

    displayInspectionSummary(currentInspection);
  } catch (err) {
    alert("Сетевая ошибка при загрузке: " + err);
  }
}

function displayInspectionSummary(info) {
  document.getElementById("fileInspectionSummary").classList.remove("hidden");
  document.getElementById("inspectFileName").innerText = `Файл: ${info.filename} (${(info.file_size_bytes / 1024).toFixed(1)} КБ)`;

  const badgeSpan = document.getElementById("inspectFastPathBadge");
  if (info.fast_path_eligible) {
    badgeSpan.innerHTML = '<span class="badge badge-green">⚡ Fast-Path (ИИ не требуется)</span>';
  } else {
    badgeSpan.innerHTML = '<span class="badge badge-yellow">🤖 Требуется AI-сопоставление</span>';
  }

  document.getElementById("inspectDetails").innerText = `Адаптер: ${info.detected_extractor} • Строк в выборке: ${info.sample_rows.length} • Предложенная таблица: ${info.suggested_table}`;

  const headersDiv = document.getElementById("inspectHeadersList");
  headersDiv.innerHTML = "";
  info.headers.forEach((h) => {
    const tag = document.createElement("span");
    tag.className = "badge badge-blue";
    tag.innerText = h;
    headersDiv.appendChild(tag);
  });
}

function resetUpload() {
  currentSessionId = null;
  currentInspection = null;
  currentMapping = null;
  currentDryRun = null;
  document.getElementById("fileInput").value = "";
  document.getElementById("fileInspectionSummary").classList.add("hidden");
  goToStep(1);
}

function goToStep(stepNum) {
  if (stepNum > 1 && !currentSessionId) {
    alert("Сначала загрузите файл на Шаге 1.");
    return;
  }

  for (let i = 1; i <= 4; i++) {
    document.getElementById(`step${i}`).classList.add("hidden");
    document.getElementById(`stepIndicator${i}`).classList.remove("active");
  }

  document.getElementById(`step${stepNum}`).classList.remove("hidden");
  document.getElementById(`stepIndicator${stepNum}`).classList.add("active");
  for (let i = 1; i < stepNum; i++) {
    document.getElementById(`stepIndicator${i}`).classList.add("completed");
  }
}

async function proceedToStep2() {
  goToStep(2);
  await loadMappingStep();
}

async function loadMappingStep() {
  const tableSelect = document.getElementById("targetTableSelect");
  tableSelect.innerHTML = "";
  currentInspection.available_tables.forEach((tbl) => {
    const opt = document.createElement("option");
    opt.value = tbl;
    opt.innerText = tbl;
    if (tbl === currentInspection.suggested_table) {
      opt.selected = true;
    }
    tableSelect.appendChild(opt);
  });

  await fetchAndRenderMapping(tableSelect.value);
}

async function onTargetTableChange() {
  const selectedTable = document.getElementById("targetTableSelect").value;
  await fetchAndRenderMapping(selectedTable);
}

async function fetchAndRenderMapping(targetTable) {
  try {
    const resp = await fetch(`/api/mapping/${currentSessionId}?target_table=${targetTable}`);
    currentMapping = await resp.json();
    renderMappingTable(currentMapping);
  } catch (err) {
    alert("Ошибка загрузки маппинга: " + err);
  }
}

function renderMappingTable(mappingData) {
  const tbody = document.getElementById("mappingTableBody");
  tbody.innerHTML = "";

  const availableCols = mappingData.available_target_columns || [];

  // Mapped dictionary
  const mappedDict = {};
  mappingData.column_mappings.forEach((m) => {
    mappedDict[m.source_column] = m;
  });

  currentInspection.headers.forEach((srcCol, idx) => {
    const tr = document.createElement("tr");
    tr.id = `row_map_${idx}`;
    const m = mappedDict[srcCol];

    // 1. Source col
    const tdSrc = document.createElement("td");
    tdSrc.innerHTML = `<b>${srcCol}</b>`;
    tr.appendChild(tdSrc);

    // 2. Target col dropdown
    const tdTgt = document.createElement("td");
    const select = document.createElement("select");
    select.className = "select-col";
    select.id = `map_select_${idx}`;
    select.dataset.header = srcCol;

    // Option: ignore
    const optIgnore = document.createElement("option");
    optIgnore.value = "IGNORE";
    optIgnore.innerText = "❌ Не загружать (Игнорировать)";
    if (!m) {
      optIgnore.selected = true;
    }
    select.appendChild(optIgnore);

    availableCols.forEach((col) => {
      const opt = document.createElement("option");
      opt.value = col.name;
      const reqBadge = col.is_required ? " [ОБЯЗАТЕЛЬНО]" : "";
      opt.innerText = `${col.name} (${col.data_type})${reqBadge}`;
      if (m && m.target_column.toLowerCase() === col.name.toLowerCase()) {
        opt.selected = true;
      }
      select.appendChild(opt);
    });

    select.addEventListener("change", () => {
      onMappingSelectChange(idx, srcCol, select.value);
    });

    tdTgt.appendChild(select);
    tr.appendChild(tdTgt);

    // 3. Confidence badge
    const tdConf = document.createElement("td");
    tdConf.id = `map_badge_${idx}`;
    if (m) {
      const pct = Math.round(m.confidence * 100);
      let badgeClass = "badge-green";
      if (pct < 70) badgeClass = "badge-red";
      else if (pct < 90) badgeClass = "badge-yellow";
      tdConf.innerHTML = `<span class="badge ${badgeClass}">${pct}%</span>`;
    } else {
      tdConf.innerHTML = '<span class="badge badge-gray">Пропуск (Игнор)</span>';
    }
    tr.appendChild(tdConf);

    // 4. Reasoning
    const tdReason = document.createElement("td");
    tdReason.id = `map_reason_${idx}`;
    tdReason.style.color = "var(--text-secondary)";
    tdReason.innerText = m ? m.reasoning : "Колонка не требуется схемой (будет пропущена)";
    tr.appendChild(tdReason);

    tbody.appendChild(tr);
  });

  checkMappingCollisions();
}

function onMappingSelectChange(idx, srcCol, selectedVal) {
  const badgeCell = document.getElementById(`map_badge_${idx}`);
  const reasonCell = document.getElementById(`map_reason_${idx}`);

  if (selectedVal === "IGNORE") {
    if (badgeCell) badgeCell.innerHTML = '<span class="badge badge-gray">Пропуск (Игнор)</span>';
    if (reasonCell) reasonCell.innerText = "Колонка исключена из импорта";
  } else {
    if (badgeCell) badgeCell.innerHTML = '<span class="badge badge-green">100%</span>';
    if (reasonCell) reasonCell.innerText = "Назначено оператором вручную";
  }

  checkMappingCollisions();
}

function checkMappingCollisions() {
  const alertBox = document.getElementById("mappingAlertBox");
  const alertText = document.getElementById("mappingAlertText");
  const dryRunBtn = document.getElementById("runDryRunBtn");

  const targetToHeaders = {};

  (currentInspection.headers || []).forEach((h, idx) => {
    const el = document.getElementById(`map_select_${idx}`);
    if (el) {
      el.style.borderColor = "";
      el.style.boxShadow = "";
      const val = el.value;
      if (val && val !== "IGNORE") {
        if (!targetToHeaders[val]) {
          targetToHeaders[val] = [];
        }
        targetToHeaders[val].push({ header: h, element: el });
      }
    }
  });

  const collisions = [];
  Object.keys(targetToHeaders).forEach((targetCol) => {
    const list = targetToHeaders[targetCol];
    if (list.length > 1) {
      collisions.push({
        targetCol: targetCol,
        headers: list.map((item) => item.header),
      });
      list.forEach((item) => {
        item.element.style.borderColor = "#ef4444";
        item.element.style.boxShadow = "0 0 0 2px rgba(239, 68, 68, 0.25)";
      });
    }
  });

  if (collisions.length > 0) {
    if (alertBox) alertBox.classList.remove("hidden");
    if (alertText) {
      const msgs = collisions.map(
        (c) => `Целевая колонка «${c.targetCol}» назначена сразу нескольким колонкам файла: [${c.headers.join(", ")}].`
      );
      alertText.innerHTML = `${msgs.join("<br>")} <b>Две разные колонки файла не могут записываться в одно поле таблицы!</b> Для лишней колонки выберите «❌ Не загружать (Игнорировать)».`;
    }
    if (dryRunBtn) {
      dryRunBtn.disabled = true;
      dryRunBtn.innerText = "Устраните дублирование колонок (см. предупреждение)";
    }
    return false;
  } else {
    if (alertBox) alertBox.classList.add("hidden");
    if (dryRunBtn) {
      dryRunBtn.disabled = false;
      dryRunBtn.innerText = "Запустить проверку (Dry-Run) →";
    }
    return true;
  }
}

async function runDryRunAndProceed() {
  if (!checkMappingCollisions()) {
    alert("Обнаружена коллизия: несколько колонок файла назначены на одну колонку БД. Пожалуйста, выберите 'Не загружать (Игнорировать)' для лишних колонок.");
    return;
  }

  // Read mappings from selects
  const customMappings = {};
  currentInspection.headers.forEach((h, idx) => {
    const el = document.getElementById(`map_select_${idx}`);
    if (el) {
      customMappings[h] = el.value;
    }
  });

  const targetTable = document.getElementById("targetTableSelect").value;
  const saveCache = document.getElementById("saveCacheCheckbox").checked;

  try {
    // 1. Save mapping
    const mapResp = await fetch(`/api/mapping/${currentSessionId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        target_table: targetTable,
        custom_mappings: customMappings,
        save_to_cache: saveCache,
      }),
    });

    if (!mapResp.ok) {
      const err = await mapResp.json();
      alert("Ошибка при сохранении сопоставления: " + (err.detail || "Неизвестная ошибка"));
      return;
    }

    // 2. Execute dry-run
    const resp = await fetch(`/api/dry-run/${currentSessionId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });

    currentDryRun = await resp.json();
    renderDryRunResults(currentDryRun);
    goToStep(3);
  } catch (err) {
    alert("Ошибка предварительной проверки: " + err);
  }
}

function renderDryRunResults(dry) {
  document.getElementById("dryRunTotal").innerText = dry.total_rows_read;
  document.getElementById("dryRunAccepted").innerText = dry.rows_accepted;
  document.getElementById("dryRunRejected").innerText = dry.rows_rejected;

  // Issues list
  const issuesCard = document.getElementById("dryRunIssuesCard");
  const issuesList = document.getElementById("dryRunIssuesList");
  issuesList.innerHTML = "";

  const allIssues = [];
  if (dry.rows_accepted === 0 && dry.total_rows_read > 0) {
    allIssues.push("⚠️ Внимание: 0 строк прошли валидацию! Проверьте, выбрана ли правильная целевая таблица на Шаге 2 (например, 'invoices' вместо 'businesses').");
  }
  (dry.human_review_required || []).forEach((hr) => {
    allIssues.push(`${hr.item}: ${hr.reason}`);
  });
  (dry.validation_issues || []).forEach((vi) => {
    allIssues.push(`Строка #${vi.row_index}: ${vi.errors.join("; ")}`);
  });

  if (allIssues.length > 0) {
    issuesCard.classList.remove("hidden");
    allIssues.slice(0, 15).forEach((iss) => {
      const li = document.createElement("li");
      li.innerText = iss;
      issuesList.appendChild(li);
    });
  } else {
    issuesCard.classList.add("hidden");
  }

  // Preview table
  const thead = document.getElementById("previewTableHead");
  const tbody = document.getElementById("previewTableBody");
  thead.innerHTML = "";
  tbody.innerHTML = "";

  if (dry.preview_records && dry.preview_records.length > 0) {
    const cols = Object.keys(dry.preview_records[0]);
    const headerRow = document.createElement("tr");
    cols.forEach((c) => {
      const th = document.createElement("th");
      th.innerText = c;
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);

    dry.preview_records.slice(0, 5).forEach((rec) => {
      const tr = document.createElement("tr");
      cols.forEach((c) => {
        const td = document.createElement("td");
        td.innerText = rec[c] !== null ? String(rec[c]) : "NULL";
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }

  updateCommitButtonState();
}

async function commitToDatabase() {
  if (currentRole === "ANALYST") {
    alert("Действие заблокировано: роль ANALYST не имеет права подтверждать запись в БД. Переключите роль на UNDERWRITER.");
    return;
  }

  try {
    const resp = await fetch(`/api/commit/${currentSessionId}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-user-id": "demo_user",
        "x-user-role": currentRole,
      },
      body: JSON.stringify({
        user_id: "demo_user",
        user_role: currentRole,
      }),
    });

    if (!resp.ok) {
      const err = await resp.json();
      alert("Ошибка фиксации: " + (err.detail || "Неизвестная ошибка"));
      return;
    }

    const commitResult = await resp.json();
    document.getElementById("commitResultHeading").innerText = `Успешно! Записано ${commitResult.inserted_count} строк в таблицу '${commitResult.target_table}'.`;
    document.getElementById("commitResultSub").innerText = `Атомарная транзакция зафиксирована пользователем ${commitResult.committed_by_user_id} (${commitResult.committed_by_role}) в ${commitResult.timestamp}.`;
    goToStep(4);
  } catch (err) {
    alert("Ошибка соединения при фиксации: " + err);
  }
}

async function downloadReport(formatType) {
  if (!currentSessionId) return;
  window.open(`/api/report/${currentSessionId}?format=${formatType}`, "_blank");
}

async function toggleHistoryModal() {
  const modal = document.getElementById("historyModal");
  if (modal.classList.contains("hidden")) {
    modal.classList.remove("hidden");
    await loadHistory();
  } else {
    modal.classList.add("hidden");
  }
}

async function loadHistory() {
  try {
    const resp = await fetch("/api/history");
    const list = await resp.json();
    const tbody = document.getElementById("historyTableBody");
    tbody.innerHTML = "";

    if (list.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align: center; color: var(--text-muted);">История пока пуста</td></tr>';
      return;
    }

    list.forEach((item) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><b>${item.filename}</b></td>
        <td><code>${item.target_table}</code></td>
        <td><span class="badge ${item.status === 'COMMITTED' ? 'badge-green' : 'badge-yellow'}">${item.status}</span></td>
        <td>${item.accepted_rows} / ${item.total_rows}</td>
        <td>${item.created_at} (${item.created_by})</td>
        <td>${item.committed_by || "—"}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Failed to load history", err);
  }
}
