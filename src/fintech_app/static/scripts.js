/**
 * GraeaeEye Smart Credit Engine - Single Page Architecture Frontend Controller
 * Aligned with Web Interface & Orchestration Layer Technical Architecture & Specification v2.0.
 * Manages tenant isolation, workspace resets, report history ledger, 9D submodules diagnostics,
 * and canonical 18D financial indices.
 */

class ConfigSingleton {
	constructor() {
		this.applyTheme();
	}

	async set(name, value) {
		try {
			localStorage.setItem(name, value);
		} catch (e) {
			console.warn("localStorage.set failed:", e);
		}
	}

	async get(name, defaultValue) {
		try {
			const local = localStorage.getItem(name);
			return (local !== null) ? local : defaultValue;
		} catch {
			return defaultValue;
		}
	}

	async applyTheme() {
		const theme = await this.getTheme();
		document.documentElement.setAttribute('data-theme', theme);
	}

	async setTheme(newTheme) {
		await this.set('theme', newTheme);
		await this.applyTheme();
	}

	async getTheme(defaultValue = "system") {
		return await this.get("theme", defaultValue);
	}
}

const config = new ConfigSingleton();

let currentUser = null;
let activeEventSource = null;

// =========================================================================
// 0. RUSSIAN LOCALIZATION & METADATA DICTIONARIES
// =========================================================================

const SUBMODULE_DICTIONARY_RU = {
	"OS": {
		title: "Структура собственности и корпоративное управление (OS)",
		code: "OS_4_1",
		description: "Оценка концентрации долей у основателей, прозрачности бенефициаров и независимости менеджмента.",
		verdicts: {
			"CONCENTRATED_OWNERSHIP": "Высокая концентрация долей у ключевых основателей",
			"BALANCED_OWNERSHIP": "Сбалансированная структура акционеров",
			"KEY_PERSON_RISK": "Концентрация управления у основателя (Риск ключевой фигуры)",
			"DATA_ABSENT": "Данные о собственниках не предоставлены (расчет пропущен без штрафа)",
			"OPAQUE_STRUCTURE": "Непрозрачная структура бенефициаров",
			"DEFAULT": "Оценка завершена"
		},
		index_labels: {
			"ownership_dispersion_index": "Индекс дисперсии владения",
			"governance_independence_index": "Индекс независимости корпоративного управления"
		}
	},
	"WPR": {
		title: "Цифровая репутация и юридическая чистота (WPR)",
		code: "WPR_4_2",
		description: "Проверка судебных реестров, санкционных списков, арбитражных производств и тональности в сети.",
		verdicts: {
			"LEGAL_INTEGRITY_CONFIRMED": "Юридическая чистота подтверждена (отсутствие арестов и санкций)",
			"LEGAL_RISKS_DETECTED": "Обнаружены открытые судебные претензии",
			"DEFAULT": "Репутационный аудит пройден"
		},
		index_labels: {
			"legal_cleanliness_index": "Индекс юридической чистоты",
			"public_reputation_index": "Индекс публичной деловой репутации"
		}
	},
	"MSR": {
		title: "Макроэкономический и отраслевой риск (MSR)",
		code: "MSR_4_3",
		description: "Оценка макроэкономической конъюнктуры, устойчивости отрасли и влияния валютно-инфляционных факторов.",
		verdicts: {
			"STABLE_SECTOR": "Стабильная динамика отраслевого сегмента",
			"VOLATILE_SECTOR": "Повышенная волатильность рынка",
			"DEFAULT": "Отраслевой анализ выполнен"
		},
		index_labels: {
			"sector_vitality_index": "Индекс витальности и динамики сектора"
		}
	},
	"CD": {
		title: "Концентрация клиентской базы (CD)",
		code: "CD_4_4",
		description: "Анализ риска потери ключевых заказчиков, доли ТОП-клиента в выручке и диверсификации портфеля счетов.",
		verdicts: {
			"MODERATE_CONCENTRATION": "Умеренная зависимость от ключевых покупателей",
			"HIGH_CLIENT_DEPENDENCY": "Критическая зависимость от якорного клиента",
			"WELL_DIVERSIFIED": "Высокая диверсификация клиентского портфеля",
			"DEFAULT": "Оценка диверсификации клиентской базы"
		},
		index_labels: {
			"client_diversification_index": "Индекс диверсификации клиентской базы",
			"top_client_exposure_index": "Индекс концентрации ТОП-клиента"
		}
	},
	"SD": {
		title: "Зависимость от поставщиков (SD)",
		code: "SD_4_5",
		description: "Анализ непрерывности цепочки поставок, концентрации закупок и риска срыва снабжения.",
		verdicts: {
			"DIVERSIFIED_SUPPLY_CHAIN": "Диверсифицированная цепочка поставщиков",
			"MONO_SUPPLIER_RISK": "Риск моно-поставщика сырья",
			"DEFAULT": "Анализ цепочки поставок завершен"
		},
		index_labels: {
			"supplier_diversification_index": "Индекс диверсификации базы поставщиков",
			"supply_chain_robustness_index": "Индекс устойчивости цепочки поставок"
		}
	},
	"ICR": {
		title: "Операционная ликвидность и покрытие долга (ICR)",
		code: "ICR_4_6",
		description: "Коэффициент покрытия процентных расходов и достаточность операционного денежного потока.",
		verdicts: {
			"PRIME_COVERAGE": "Высокое покрытие процентных выплат (> 3.0x)",
			"ADEQUATE_COVERAGE": "Достаточный запас покрытия обязательств",
			"CRITICAL_ILLIQUIDITY": "Дефицит ликвидности для обслуживания процентов",
			"DEFAULT": "Расчет покрытия долга"
		},
		index_labels: {
			"interest_coverage_ratio_index": "Индекс покрытия процентных расходов (ICR)",
			"operating_cash_liquidity_index": "Индекс операционной ликвидности"
		}
	},
	"CFS": {
		title: "Стабильность и волатильность денежного потока (CFS)",
		code: "CFS_4_7",
		description: "Оценка ритмичности поступлений на расчетные счета, коэффициента вариации чистого денежного потока.",
		verdicts: {
			"STABLE_INFLOWS": "Ритмичные и предсказуемые денежные притоки",
			"SEASONAL_VARIATION": "Выраженная сезонность поступлений выручки",
			"ERRATIC_FLOWS": "Высокая хаотичность денежных потоков",
			"DEFAULT": "Анализ кассовых разрывов"
		},
		index_labels: {
			"net_cash_flow_stability_index": "Индекс стабильности чистого денежного потока",
			"cash_inflow_rhythmicity_index": "Индекс ритмичности притоков на счета",
			"operating_cushion_index": "Индекс подушки операционной ликвидности"
		}
	},
	"RQ": {
		title: "Качество дебиторской задолженности (RQ)",
		code: "RQ_4_8",
		description: "Оборачиваемость коммерческой дебиторской задолженности, средний срок инкассации (DSO) и дисциплина оплаты.",
		verdicts: {
			"PROMPT_COLLECTIONS": "Своевременная инкассация дебиторской задолженности",
			"DSO_EXTENDED": "Затягивание сроков расчетов покупателями",
			"DEFAULT": "Оценка платежной дисциплины покупателей"
		},
		index_labels: {
			"receivables_safety_index": "Индекс надежности дебиторского портфеля",
			"client_payment_discipline_index": "Индекс платежной дисциплины контрагентов"
		}
	},
	"ICDL": {
		title: "Кредитная дисциплина и долговая нагрузка (ICDL)",
		code: "ICDL_4_9",
		description: "История погашения кредитов, просрочки (30+/90+ дней), долговой левередж и покрытие долга (DSCR).",
		verdicts: {
			"PRIME_CREDIT": "Безупречная кредитная история без дефолтов",
			"MODERATE_LEVERAGE": "Умеренная кредитная нагрузка",
			"OVERLEVERAGED_DELINQUENT": "Критическая долговая нагрузка или просрочки",
			"DEFAULT": "Оценка совокупной долговой нагрузки"
		},
		index_labels: {
			"debt_repayment_discipline_index": "Индекс платежной дисциплины по кредитам",
			"debt_service_coverage_index": "Индекс обслуживания совокупного долга (DSCR)",
			"solvency_leverage_index": "Индекс платежеспособности и финансового левереджа"
		}
	}
};

const CANONICAL_18D_METADATA_RU = [
	{ key: "ownership_dispersion_index", module: "OS", title: "Индекс дисперсии владения", desc: "Распределение долей капитала; отсутствие монопольного контроля одного владельца." },
	{ key: "governance_independence_index", module: "OS", title: "Индекс независимости управления", desc: "Независимость менеджмента от персональных решений собственников." },
	{ key: "legal_cleanliness_index", module: "WPR", title: "Индекс юридической чистоты", desc: "Отсутствие открытых исполнительных производств, налоговых арестов и судебных исков." },
	{ key: "public_reputation_index", module: "WPR", title: "Индекс публичной деловой репутации", desc: "Тональность упоминаний компании в деловых СМИ и отсутствие компрометирующих связей." },
	{ key: "sector_vitality_index", module: "MSR", title: "Индекс динамики сектора (NACE)", desc: "Макроэкономическая конъюнктура и темпы роста выручки предприятий отрасли." },
	{ key: "client_diversification_index", module: "CD", title: "Индекс диверсификации клиентов", desc: "Равномерность распределения клиентского портфеля по объему выставленных счетов." },
	{ key: "top_client_exposure_index", module: "CD", title: "Индекс концентрации ТОП-клиента", desc: "Доля крупнейшего покупателя в совокупной выручке и дебиторской задолженности." },
	{ key: "supplier_diversification_index", module: "SD", title: "Индекс диверсификации поставщиков", desc: "Отсутствие моно-зависимости от единственного поставщика ключевого сырья или услуг." },
	{ key: "supply_chain_robustness_index", module: "SD", title: "Индекс устойчивости цепочки поставок", desc: "Надежность и ритмичность снабжения операционного цикла сырьем." },
	{ key: "interest_coverage_ratio_index", module: "ICR", title: "Коэффициент покрытия процентов (ICR)", desc: "Отношение операционного денежного потока к объему обязательных процентных выплат." },
	{ key: "operating_cash_liquidity_index", module: "ICR", title: "Индекс операционной ликвидности", desc: "Достаточность доступного денежного остатка для финансирования текущих затрат." },
	{ key: "net_cash_flow_stability_index", module: "CFS", title: "Индекс стабильности чистого денежного потока", desc: "Коэффициент вариации ежемесячных сальдо чистого операционного денежного потока." },
	{ key: "cash_inflow_rhythmicity_index", module: "CFS", title: "Индекс ритмичности поступлений выручки", desc: "Регулярность поступления денежных средств на расчетные счета в течение месяца." },
	{ key: "operating_cushion_index", module: "CFS", title: "Индекс финансовой подушки безопасности", desc: "Период покрытия фиксированных затрат за счет неснижаемого остатка денежных средств (в днях)." },
	{ key: "receivables_safety_index", module: "RQ", title: "Индекс надежности дебиторской задолженности", desc: "Доля просроченных счетов-фактур в совокупном портфеле выставленной дебиторки." },
	{ key: "client_payment_discipline_index", module: "RQ", title: "Индекс платежной дисциплины покупателей", desc: "Средний период фактической оплаты относительно контрактного срока (DSO)." },
	{ key: "debt_repayment_discipline_index", module: "ICDL", title: "Индекс платежной дисциплины по кредитам", desc: "Отсутствие фактов просрочки кредитных траншей (30+, 60+, 90+ дней) в кредитной истории." },
	{ key: "debt_service_coverage_index", module: "ICDL", title: "Коэффициент обслуживания долга (DSCR)", desc: "Способность операционной прибыли предприятия покрывать выплаты долга и процентов." }
];

const VERDICT_TRANSLATIONS = {
	"PRIME_LOW_RISK": "Премиальный заемщик (Минимальный риск)",
	"MODERATE_RISK_WATCHLIST": "Умеренный риск (Мониторинг)",
	"HIGH_RISK_REJECT": "Высокий риск (Отказ)",
	"APPROVED": "ОДОБРЕНО КРЕДИТНЫМ КОМИТЕТОМ",
	"CONDITIONAL": "ОДОБРЕНО С ОБЕСПЕЧЕНИЕМ / УСЛОВИЯМИ",
	"REJECTED": "ОТКАЗ В ПРЕДОСТАВЛЕНИИ ЛИМИТА",
	"DEFERRED": "ОТЛОЖЕНО ДЛЯ ДОПОЛНИТЕЛЬНОГО АУДИТА",
	"DATA_ABSENT": "Данные не предоставлены (расчет пропущен без штрафа)",
	"SKIPPED": "Субмодуль пропущен",
	"KEY_PERSON_RISK": "Концентрация управления (Риск ключевой фигуры)"
};

// =========================================================================
// 1. SYSTEM HEALTH & THEME CONTROLS
// =========================================================================

function upd_status() {
	const statusElem = document.getElementById("system-status");
	if (!statusElem) return;
	fetch("/api/v1/health")
		.then(r => r.json())
		.then(data => {
			if (data.status === "ok") {
				const dbState = data.db || "connected";
				statusElem.className = "badge badge-success";
				statusElem.innerText = `Online (${dbState})`;
			} else {
				statusElem.className = "badge badge-danger";
				statusElem.innerText = "System Degraded";
			}
		})
		.catch(() => {
			statusElem.className = "badge badge-danger";
			statusElem.innerText = "Offline";
		});
}

const ICON_SYSTEM = "🌗";
const ICON_DARK = "🌙";
const ICON_LIGHT = "🌣";

function upd_theme() {
	const button = document.getElementById("theming");
	if (!button) return;
	if (button.innerText === ICON_SYSTEM) {
		config.setTheme("dark");
		button.innerText = ICON_DARK;
	} else if (button.innerText === ICON_DARK) {
		config.setTheme("light");
		button.innerText = ICON_LIGHT;
	} else {
		config.setTheme("system");
		button.innerText = ICON_SYSTEM;
	}
}

function restore_theme() {
	const button = document.getElementById("theming");
	if (!button) return;
	config.getTheme().then(theme => {
		switch (theme) {
			case "dark": button.innerText = ICON_DARK; break;
			case "light": button.innerText = ICON_LIGHT; break;
			default: button.innerText = ICON_SYSTEM;
		}
	});
}

// =========================================================================
// 2. AUTHENTICATION & MULTI-TENANT ISOLATION
// =========================================================================

function update_auth_ui() {
	const guestBlock = document.getElementById("auth-guest");
	const loggedInBlock = document.getElementById("auth-logged-in");
	const workspace = document.getElementById("workspace");

	if (currentUser && (currentUser.email || currentUser.user_id)) {
		if (guestBlock) guestBlock.style.display = "none";
		if (loggedInBlock) loggedInBlock.style.display = "block";
		if (workspace) workspace.style.display = "block";

		const nameElem = document.getElementById("user-name");
		const roleElem = document.getElementById("user-role");
		const emailElem = document.getElementById("user-email");

		if (nameElem) nameElem.innerText = currentUser.full_name || "Analyst";
		if (roleElem) roleElem.innerText = currentUser.role || "ANALYST";
		if (emailElem) emailElem.innerText = currentUser.email || "";
	} else {
		clear_report();
		if (guestBlock) guestBlock.style.display = "block";
		if (loggedInBlock) loggedInBlock.style.display = "none";
		if (workspace) workspace.style.display = "none";
	}
}

function reset_workspace(full = false) {
	if (activeEventSource) {
		activeEventSource.close();
		activeEventSource = null;
	}

	const telemetrySection = document.getElementById("telemetry-section");
	if (telemetrySection) telemetrySection.style.display = "none";

	const reportSection = document.getElementById("report-section");
	if (reportSection) reportSection.style.display = "none";

	clear_terminal();

	const fill = document.getElementById("pipeline-progress-bar");
	if (fill) {
		fill.style.width = "5%";
		fill.innerText = "5%";
	}

	const stages = document.querySelectorAll(".stage-tag");
	stages.forEach(s => s.classList.remove("active"));
	const q = document.getElementById("st-queued");
	if (q) q.classList.add("active");

	const badges = document.querySelectorAll(".submodule-badge");
	badges.forEach(b => {
		b.className = "submodule-badge";
		const stateSpan = b.querySelector(".sm-state");
		if (stateSpan) stateSpan.innerText = "PENDING";
	});

	const runBadge = document.getElementById("run-status-badge");
	if (runBadge) {
		runBadge.className = "badge";
		runBadge.innerText = "PROCESSING";
	}

	const btn = document.getElementById("btn-start-analysis");
	if (btn) {
		btn.disabled = false;
		btn.innerText = "🚀 Start Multi-Document Risk Analysis";
	}

	const wizardErr = document.getElementById("wizard-error");
	if (wizardErr) wizardErr.innerText = "";

	if (full) {
		const form = document.getElementById("analysis-form");
		if (form) form.reset();
		["name-statement", "name-invoices", "name-credits"].forEach(id => {
			const el = document.getElementById(id);
			if (el) {
				el.innerText = "No file chosen";
				el.classList.remove("file-selected");
			}
		});
	}
}

function reset_workspace_for_new_analysis() {
	reset_workspace(false);
	switch_tab("analysis");
	const wizard = document.getElementById("wizard-section");
	if (wizard) wizard.scrollIntoView({ behavior: "smooth" });
}

function init_auth() {
	const loginForm = document.getElementById("login-form");
	const loginError = document.getElementById("login-error");

	if (loginForm) {
		loginForm.addEventListener("submit", async (e) => {
			e.preventDefault();
			if (loginError) loginError.innerText = "";

			const email = document.getElementById("login-email").value.trim();
			const password = document.getElementById("login-password").value;

			try {
				const response = await fetch("/api/v1/auth/token", {
					method: "POST",
					headers: { "Content-Type": "application/x-www-form-urlencoded" },
					body: new URLSearchParams({ username: email, password: password })
				});

				const data = await response.json();
				if (!response.ok) {
					if (loginError) loginError.innerText = data.detail || "Authentication failed.";
					return;
				}

				currentUser = data;
				sessionStorage.setItem("user", JSON.stringify(data));
				reset_workspace(true);
				update_auth_ui();
				load_history();
			} catch (err) {
				if (loginError) loginError.innerText = "Network error connecting to auth server.";
			}
		});
	}

	const registerForm = document.getElementById("register-form");
	const registerError = document.getElementById("register-error");

	if (registerForm) {
		registerForm.addEventListener("submit", async (e) => {
			e.preventDefault();
			if (registerError) registerError.innerText = "";

			const fullName = document.getElementById("register-name").value.trim();
			const email = document.getElementById("register-email").value.trim();
			const password = document.getElementById("register-password").value;

			try {
				const response = await fetch("/api/v1/auth/register", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ email: email, password: password, full_name: fullName })
				});

				const data = await response.json();
				if (!response.ok) {
					if (registerError) registerError.innerText = data.detail || "Registration failed.";
					return;
				}

				currentUser = data;
				sessionStorage.setItem("user", JSON.stringify(data));
				reset_workspace(true);
				update_auth_ui();
				load_history();
			} catch (err) {
				if (registerError) registerError.innerText = "Network error connecting to auth server.";
			}
		});
	}

	const logoutForm = document.getElementById("logout-form");
	if (logoutForm) {
		logoutForm.addEventListener("submit", (e) => {
			e.preventDefault();
			currentUser = null;
			sessionStorage.removeItem("user");
			reset_workspace(true);
			update_auth_ui();
		});
	}

	const savedUser = sessionStorage.getItem("user");
	if (savedUser) {
		try {
			currentUser = JSON.parse(savedUser);
		} catch {}
	}
	update_auth_ui();
	if (currentUser) {
		load_history();
	}
}

// =========================================================================
// 3. WORKSPACE TABS & HISTORY LEDGER
// =========================================================================

function switch_tab(tabName) {
	const btnAnalysis = document.getElementById("tab-btn-analysis");
	const btnHistory = document.getElementById("tab-btn-history");
	const paneAnalysis = document.getElementById("analysis-tab-pane");
	const paneHistory = document.getElementById("history-tab-pane");

	if (tabName === "analysis") {
		if (btnAnalysis) btnAnalysis.classList.add("active");
		if (btnHistory) btnHistory.classList.remove("active");
		if (paneAnalysis) paneAnalysis.style.display = "block";
		if (paneHistory) paneHistory.style.display = "none";
	} else if (tabName === "history") {
		if (btnAnalysis) btnAnalysis.classList.remove("active");
		if (btnHistory) btnHistory.classList.add("active");
		if (paneAnalysis) paneAnalysis.style.display = "none";
		if (paneHistory) paneHistory.style.display = "block";
		load_history();
	}
}

async function load_history() {
	const tableBody = document.getElementById("history-table-body");
	if (!tableBody) return;

	const headers = {};
	if (currentUser && currentUser.access_token) {
		headers["Authorization"] = `Bearer ${currentUser.access_token}`;
	}

	try {
		const response = await fetch("/api/v1/analysis/history?limit=50", { headers });
		if (!response.ok) {
			tableBody.innerHTML = `<tr><td colspan="8" class="text-center">Не удалось загрузить историю анализов (${response.status})</td></tr>`;
			return;
		}

		const data = await response.json();
		const items = data.items || [];

		if (items.length === 0) {
			tableBody.innerHTML = `<tr><td colspan="8" class="text-center">В вашей истории пока нет проведенных анализов. Перейдите во вкладку "Новый экспресс-анализ" для запуска.</td></tr>`;
			return;
		}

		tableBody.innerHTML = items.map(run => {
			const dateStr = run.created_at ? new Date(run.created_at).toLocaleString("ru-RU") : "--";
			const scoreStr = run.universal_score != null ? `${Number(run.universal_score).toFixed(1)} / 100` : "--";

			let statusBadgeClass = "badge-info";
			if (run.status === "COMPLETED") statusBadgeClass = "badge-success";
			else if (run.status === "FAILED") statusBadgeClass = "badge-danger";
			else if (run.status === "PROCESSING" || run.status === "QUEUED") statusBadgeClass = "badge-warning";

			const verdictRu = run.verdict_category ? (VERDICT_TRANSLATIONS[run.verdict_category] || run.verdict_category) : "--";
			const recRu = run.recommendation ? (VERDICT_TRANSLATIONS[run.recommendation] || run.recommendation) : "--";

			return `
				<tr>
					<td><small>${dateStr}</small></td>
					<td><strong>${run.company_name}</strong></td>
					<td><code>${run.tax_id}</code></td>
					<td><span class="badge">${run.sector_code}</span></td>
					<td><span class="badge ${statusBadgeClass}">${run.status}</span></td>
					<td><strong>${scoreStr}</strong></td>
					<td><small>${recRu}</small></td>
					<td>
						<button class="btn btn-sm btn-primary" onclick="open_report_from_history('${run.run_id}')">
							Открыть досье
						</button>
					</td>
				</tr>
			`;
		}).join("");

	} catch (err) {
		console.error("Failed to load history ledger:", err);
		tableBody.innerHTML = `<tr><td colspan="8" class="text-center">Ошибка соединения при загрузке реестра.</td></tr>`;
	}
}

function open_report_from_history(runId) {
	switch_tab("analysis");
	fetch_and_render_report(runId);
}

// =========================================================================
// 4. MULTI-DOCUMENT INGESTION WIZARD
// =========================================================================

function init_wizard() {
	const setupFileInput = (inputId, displayId) => {
		const input = document.getElementById(inputId);
		const display = document.getElementById(displayId);
		if (input && display) {
			input.addEventListener("change", () => {
				if (input.files && input.files[0]) {
					const f = input.files[0];
					display.innerText = `✓ ${f.name} (${(f.size / 1024).toFixed(1)} KB)`;
					display.classList.add("file-selected");
				} else {
					display.innerText = "No file chosen";
					display.classList.remove("file-selected");
				}
			});
		}
	};

	setupFileInput("file-statement", "name-statement");
	setupFileInput("file-invoices", "name-invoices");
	setupFileInput("file-credits", "name-credits");

	const analysisForm = document.getElementById("analysis-form");
	const wizardError = document.getElementById("wizard-error");

	if (analysisForm) {
		analysisForm.addEventListener("submit", async (e) => {
			e.preventDefault();
			if (wizardError) wizardError.innerText = "";

			const companyName = document.getElementById("company_name").value.trim();
			const taxId = document.getElementById("tax_id").value.trim();
			const industryCode = document.getElementById("industry_code").value.trim();

			const statementFile = document.getElementById("file-statement").files[0];
			const invoicesFile = document.getElementById("file-invoices").files[0];
			const creditsFile = document.getElementById("file-credits").files[0];

			if (!statementFile) {
				if (wizardError) wizardError.innerText = "Файл банковской выписки (Bank Statement) обязателен для расчета денежного потока.";
				return;
			}

			const formData = new FormData();
			formData.append("input_company_name", companyName);
			formData.append("input_tax_id", taxId);
			formData.append("input_industry_code", industryCode);
			formData.append("bank_statement_file", statementFile);
			if (invoicesFile) formData.append("invoices_file", invoicesFile);
			if (creditsFile) formData.append("credit_obligations_file", creditsFile);

			const headers = {};
			if (currentUser && currentUser.access_token) {
				headers["Authorization"] = `Bearer ${currentUser.access_token}`;
			}

			const btn = document.getElementById("btn-start-analysis");
			if (btn) {
				btn.disabled = true;
				btn.innerText = "Запуск аналитического пайплайна...";
			}

			try {
				const response = await fetch("/api/v1/analysis/start", {
					method: "POST",
					headers: headers,
					body: formData
				});

				const data = await response.json();
				if (!response.ok) {
					if (wizardError) wizardError.innerText = data.detail || "Ошибка при запуске расчета.";
					if (btn) {
						btn.disabled = false;
						btn.innerText = "🚀 Start Multi-Document Risk Analysis";
					}
					return;
				}

				const runId = data.run_id;
				start_telemetry_streaming(runId, companyName, taxId);
			} catch (err) {
				if (wizardError) wizardError.innerText = "Сетевая ошибка при отправке задачи: " + err.message;
				if (btn) {
					btn.disabled = false;
					btn.innerText = "🚀 Start Multi-Document Risk Analysis";
				}
			}
		});
	}
}

// =========================================================================
// 5. REAL-TIME SSE STREAM TELEMETRY
// =========================================================================

function clear_terminal() {
	const terminal = document.getElementById("terminal-logs");
	if (terminal) terminal.innerText = "";
}

function append_terminal(severity, stage, message, timestamp) {
	const terminal = document.getElementById("terminal-logs");
	if (!terminal) return;
	const timeStr = timestamp ? timestamp.slice(11, 19) : new Date().toTimeString().slice(0, 8);
	const line = `[${timeStr}] [${severity.padEnd(5)}] [${stage}] ${message}\n`;
	terminal.innerText += line;
	terminal.scrollTop = terminal.scrollHeight;
}

function update_progress(percentage, stageName) {
	const fill = document.getElementById("pipeline-progress-bar");
	if (fill) {
		fill.style.width = `${percentage}%`;
		fill.innerText = `${percentage}%`;
	}

	const stageMap = {
		"QUEUED": "st-queued",
		"INGESTION": "st-ingestion",
		"DATA_LOAD": "st-dataload",
		"ML_EVALUATION": "st-mleval",
		"SCORING": "st-scoring",
		"LLM_SYNTHESIS": "st-scoring",
		"PIPELINE_COMPLETE": "st-complete",
		"COMPLETED": "st-complete"
	};

	const targetId = stageMap[stageName];
	if (targetId) {
		const elem = document.getElementById(targetId);
		if (elem) elem.classList.add("active");
	}
}

function update_submodule_badge(code, status, verdict) {
	const badge = document.getElementById(`badge-${code}`);
	if (!badge) return;
	const stateSpan = badge.querySelector(".sm-state");
	badge.className = "submodule-badge";

	if (status === "SUCCESS" || status === "COMPLETED") {
		badge.classList.add("state-success");
		if (stateSpan) stateSpan.innerText = verdict || "OK";
	} else if (status === "DATA_ABSENT" || status === "BYPASSED") {
		badge.classList.add("state-warning");
		if (stateSpan) stateSpan.innerText = "BYPASSED";
	} else if (status === "ERROR" || status === "FAILED") {
		badge.classList.add("state-danger");
		if (stateSpan) stateSpan.innerText = "FAIL";
	} else {
		badge.classList.add("state-running");
		if (stateSpan) stateSpan.innerText = "RUNNING";
	}
}

function start_telemetry_streaming(runId, companyName, taxId) {
	const telemetrySection = document.getElementById("telemetry-section");
	if (telemetrySection) telemetrySection.style.display = "block";
	telemetrySection.scrollIntoView({ behavior: "smooth" });

	document.getElementById("display-run-id").innerText = runId;
	document.getElementById("display-entity").innerText = companyName;
	document.getElementById("display-tax-id").innerText = taxId;

	clear_terminal();
	append_terminal("INFO", "SYS", `Подключение к потоку телеметрии для задачи ${runId}...`);

	if (activeEventSource) {
		activeEventSource.close();
		activeEventSource = null;
	}

	const tokenParam = (currentUser && currentUser.access_token) ? `?token=${encodeURIComponent(currentUser.access_token)}` : "";
	const sseUrl = `/api/v1/analysis/stream/${runId}${tokenParam}`;
	activeEventSource = new EventSource(sseUrl);

	activeEventSource.addEventListener("PIPELINE_STAGE_CHANGED", (e) => {
		try {
			const data = JSON.parse(e.data);
			update_progress(data.progress_percentage || 50, data.stage || "PROCESSING");
			append_terminal("INFO", "STAGE", `Переход на этап: ${data.stage}`);
		} catch (err) {
			console.error("Error parsing PIPELINE_STAGE_CHANGED:", err);
		}
	});

	activeEventSource.addEventListener("LOG_EMITTED", (e) => {
		try {
			const data = JSON.parse(e.data);
			append_terminal(data.severity || "INFO", data.stage || "CORE", data.message || "", data.timestamp);
		} catch (err) {
			console.error("Error parsing LOG_EMITTED:", err);
		}
	});

	activeEventSource.addEventListener("SUBMODULE_STATUS_UPDATED", (e) => {
		try {
			const data = JSON.parse(e.data);
			update_submodule_badge(data.submodule_id, data.status, data.verdict);
		} catch (err) {
			console.error("Error parsing SUBMODULE_STATUS_UPDATED:", err);
		}
	});

	activeEventSource.addEventListener("PIPELINE_COMPLETE", (e) => {
		try {
			const data = JSON.parse(e.data);
			append_terminal("INFO", "DONE", `Расчет завершен. Итоговый скоринг: ${data.universal_score}`);
			update_progress(100, "COMPLETED");
			document.getElementById("run-status-badge").innerText = "COMPLETED";
			document.getElementById("run-status-badge").className = "badge badge-success";

			const btn = document.getElementById("btn-start-analysis");
			if (btn) {
				btn.disabled = false;
				btn.innerText = "🚀 Start Multi-Document Risk Analysis";
			}

			if (activeEventSource) {
				activeEventSource.close();
				activeEventSource = null;
			}
			fetch_and_render_report(runId);
		} catch (err) {
			console.error("Error handling PIPELINE_COMPLETE:", err);
		}
	});

	activeEventSource.addEventListener("PIPELINE_FAILED", (e) => {
		try {
			const data = JSON.parse(e.data);
			append_terminal("ERROR", "FAIL", `Ошибка выполнения пайплайна: ${data.error}`);
			document.getElementById("run-status-badge").innerText = "FAILED";
			document.getElementById("run-status-badge").className = "badge badge-danger";

			const btn = document.getElementById("btn-start-analysis");
			if (btn) {
				btn.disabled = false;
				btn.innerText = "🚀 Start Multi-Document Risk Analysis";
			}

			if (activeEventSource) {
				activeEventSource.close();
				activeEventSource = null;
			}
		} catch (err) {
			console.error("Error handling PIPELINE_FAILED:", err);
		}
	});

	activeEventSource.onerror = (err) => {
		console.warn("EventSource closed or reconnecting:", err);
		const btn = document.getElementById("btn-start-analysis");
		if (btn) {
			btn.disabled = false;
			btn.innerText = "🚀 Start Multi-Document Risk Analysis";
		}
		setTimeout(() => fetch_and_render_report(runId), 2000);
	};
}

// =========================================================================
// 6. UNDERWRITING REPORT DOSSIER & DIAGNOSTICS RENDERING
// =========================================================================

function toggle_feature_vector() {
	const content = document.getElementById("feature-vector-content");
	const icon = document.getElementById("fv-toggle-icon");
	if (!content || !icon) return;

	if (content.style.display === "none") {
		content.style.display = "block";
		icon.innerText = "▲ Свернуть";
	} else {
		content.style.display = "none";
		icon.innerText = "▼ Развернуть";
	}
}

async function fetch_and_render_report(runId) {
	const headers = {};
	if (currentUser && currentUser.access_token) {
		headers["Authorization"] = `Bearer ${currentUser.access_token}`;
	}

	try {
		const resp = await fetch(`/api/v1/analysis/report/${runId}`, { headers });
		if (!resp.ok) return;
		const report = await resp.json();

		const reportSection = document.getElementById("report-section");
		if (reportSection) reportSection.style.display = "block";
		reportSection.scrollIntoView({ behavior: "smooth" });

		// Score banner
		const scoreElem = document.getElementById("report-score");
		if (scoreElem) scoreElem.innerText = (report.universal_score != null) ? Number(report.universal_score).toFixed(1) : "--";

		const verdictElem = document.getElementById("report-verdict-badge");
		if (verdictElem) {
			const riskCat = report.verdict_category || report.risk_band || "UNKNOWN";
			verdictElem.innerText = VERDICT_TRANSLATIONS[riskCat] || riskCat;
			verdictElem.className = "badge " + (riskCat === "PRIME_LOW_RISK" ? "badge-success" : (riskCat === "HIGH_RISK_REJECT" ? "badge-danger" : "badge-warning"));
		}

		const recElem = document.getElementById("report-rec-badge");
		if (recElem) {
			const recVal = report.recommendation || report.decision || "--";
			recElem.innerText = VERDICT_TRANSLATIONS[recVal] || recVal;
			recElem.className = "badge " + (recVal === "APPROVED" ? "badge-success" : (recVal === "REJECTED" ? "badge-danger" : "badge-info"));
		}

		const pdElem = document.getElementById("report-pd");
		if (pdElem) {
			pdElem.innerText = (report.probability_of_default != null) ? `${(Number(report.probability_of_default) * 100).toFixed(2)}%` : "--%";
		}

		// LLM Executive Summary Memo
		const memoElem = document.getElementById("report-memo");
		if (memoElem) {
			const summaryText = report.llm_final_summary || (report.llm_synthesis ? report.llm_synthesis.summary_markdown : "") || "Меморандум не сформирован.";
			const htmlText = summaryText
				.replace(/^### (.*$)/gim, "<h4>$1</h4>")
				.replace(/^## (.*$)/gim, "<h3>$1</h3>")
				.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
				.replace(/\n\n/g, "<br><br>")
				.replace(/\n- (.*$)/gim, "<li>$1</li>");
			memoElem.innerHTML = htmlText;
		}

		// Render Radar / Pillar Chart SVG
		render_submodules_chart(report.submodules || []);

		// Render Granular Submodules Breakdown Cards
		render_submodule_cards(report.submodules || []);

		// Render Canonical 18D Feature Vector Table
		render_feature_vector_table(report.feature_vector || report.features || {});

	} catch (err) {
		console.error("Failed to render report dossier:", err);
	}
}

function render_submodules_chart(submodules) {
	const svg = document.getElementById("submodule-radar-svg");
	if (!svg) return;
	svg.innerHTML = "";

	if (!submodules || submodules.length === 0) return;

	const barWidth = 38;
	const barGap = 14;
	const maxBarHeight = 180;
	const startX = 20;
	const baseY = 240;

	submodules.forEach((sm, i) => {
		const x = startX + i * (barWidth + barGap);
		const scoreVal = sm.impact_weight ? (sm.impact_weight * 100) : 50.0;
		const h = Math.max(10, (scoreVal / 100) * maxBarHeight);
		const y = baseY - h;

		const isOk = (sm.status === "SUCCESS" || sm.status === "COMPLETED");
		const isBypassed = (sm.status === "DATA_ABSENT" || sm.status === "BYPASSED");
		const color = isOk ? "#38bdf8" : (isBypassed ? "#fbbf24" : "#f87171");

		const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
		rect.setAttribute("x", x);
		rect.setAttribute("y", y);
		rect.setAttribute("width", barWidth);
		rect.setAttribute("height", h);
		rect.setAttribute("fill", color);
		rect.setAttribute("rx", "4");
		svg.appendChild(rect);

		const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
		text.setAttribute("x", x + barWidth / 2);
		text.setAttribute("y", baseY + 18);
		text.setAttribute("text-anchor", "middle");
		text.setAttribute("fill", "var(--clr-fg)");
		text.setAttribute("font-size", "11px");
		text.textContent = (sm.submodule_id || `SM${i+1}`).split("_")[0];
		svg.appendChild(text);
	});
}

function render_submodule_cards(submodules) {
	const container = document.getElementById("submodules-reports-list");
	if (!container) return;
	container.innerHTML = "";

	submodules.forEach(sm => {
		const shortCode = (sm.submodule_id || "").split("_")[0] || "SM";
		const dict = SUBMODULE_DICTIONARY_RU[shortCode] || {};

		const card = document.createElement("div");
		card.className = "submodule-report-card";

		const cardTitle = dict.title || sm.name || sm.title || sm.submodule_id;
		const cardDesc = dict.description || "";

		let statusBadgeClass = "badge-info";
		let statusLabel = sm.status || "ACTIVE";
		if (sm.status === "SUCCESS" || sm.status === "COMPLETED") {
			statusBadgeClass = "badge-success";
			statusLabel = "УСПЕШНО";
		} else if (sm.status === "DATA_ABSENT" || sm.status === "BYPASSED") {
			statusBadgeClass = "badge-warning";
			statusLabel = "ПРОПУЩЕН (НЕТ ДАННЫХ)";
		} else if (sm.status === "ERROR" || sm.status === "FAILED") {
			statusBadgeClass = "badge-danger";
			statusLabel = "ОШИБКА";
		}

		const verdictRu = (dict.verdicts && dict.verdicts[sm.verdict]) || sm.verdict || "Оценка выполнена";
		const weightStr = sm.impact_weight ? `${(sm.impact_weight * 100).toFixed(1)}%` : "N/A";

		// Submodule computed indices chips
		let indicesHtml = "";
		if (sm.indices && Object.keys(sm.indices).length > 0) {
			const chips = Object.entries(sm.indices).map(([idxKey, idxVal]) => {
				const label = (dict.index_labels && dict.index_labels[idxKey]) || idxKey;
				let valClass = "secondary";
				let valText = "Н/Д";
				if (idxVal !== null && idxVal !== undefined) {
					const num = Number(idxVal);
					valText = num.toFixed(1);
					if (num < 40) valClass = "danger";
					else if (num <= 70) valClass = "warning";
					else valClass = "success";
				}
				return `
					<div class="sm-index-chip">
						<span class="chip-name" title="${label}">${label}</span>
						<span class="chip-val ${valClass}">${valText}${idxVal !== null && idxVal !== undefined ? " / 100" : ""}</span>
					</div>
				`;
			}).join("");
			indicesHtml = `<div class="sm-indices-grid">${chips}</div>`;
		}

		const summaryText = sm.dry_report || sm.diagnostic_report || sm.summary || "Диагностические показатели обработаны успешно.";

		card.innerHTML = `
			<div class="sm-card-header">
				<div class="sm-card-title-group">
					<h4>${cardTitle}</h4>
					<div class="sm-card-desc">${cardDesc}</div>
				</div>
				<span class="badge ${statusBadgeClass}">${statusLabel}</span>
			</div>
			<div class="sm-card-body">
				<p><strong>Вердикт:</strong> ${verdictRu}</p>
				<p><strong>Вес фактора в скоринге:</strong> ${weightStr}</p>
				${indicesHtml}
				<div class="diagnostic-text">${summaryText}</div>
			</div>
		`;

		container.appendChild(card);
	});
}

function render_feature_vector_table(featureVector) {
	const tableBody = document.getElementById("indices-table-body");
	if (!tableBody) return;

	tableBody.innerHTML = CANONICAL_18D_METADATA_RU.map(meta => {
		const val = featureVector[meta.key];
		let valDisplay = "Н/Д";
		let riskClass = "badge";
		let riskLabel = "Данные отсутствуют";

		if (val !== null && val !== undefined) {
			const num = Number(val);
			valDisplay = `${num.toFixed(1)} / 100`;
			if (num < 40) {
				riskClass = "badge badge-danger";
				riskLabel = "Критический риск (< 40)";
			} else if (num <= 70) {
				riskClass = "badge badge-warning";
				riskLabel = "Умеренный риск (40-70)";
			} else {
				riskClass = "badge badge-success";
				riskLabel = "Надежный показатель (> 70)";
			}
		}

		return `
			<tr>
				<td><strong>${meta.title}</strong><br><small><code>${meta.key}</code></small></td>
				<td><span class="badge">${meta.module}</span></td>
				<td><strong>${valDisplay}</strong></td>
				<td><span class="${riskClass}">${riskLabel}</span></td>
				<td><small>${meta.desc}</small></td>
			</tr>
		`;
	}).join("");
}

// =========================================================================
// 7. INITIALIZATION HOOK
// =========================================================================

document.addEventListener("DOMContentLoaded", function() {
	restore_theme();
	upd_status();
	init_auth();
	init_wizard();
}, false);
