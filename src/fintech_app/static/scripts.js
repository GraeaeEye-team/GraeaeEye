/**
 * GraeaeEye Smart Credit Engine - Single Page Architecture Frontend Controller
 * Manages theme preferences, session authentication, file intake wizard,
 * real-time SSE stream telemetry (/api/v1/analysis/stream), and final dossier dashboard.
 */

class ConfigSingleton {
	constructor() {
		this.applyTheme();
	}

	set(name, value) {
		try {
			localStorage.setItem(name, value);
		} catch (e) {
			console.warn("localStorage.set failed:", e);
		}
	}

	get(name, defaultValue) {
		try {
			const local = localStorage.getItem(name);
			return (local !== null) ? local : defaultValue;
		} catch {
			return defaultValue;
		}
	}

	applyTheme() {
		const theme = this.getTheme();
		document.documentElement.setAttribute('data-theme', theme);
	}

	setTheme(newTheme) {
		this.set('theme', newTheme);
		this.applyTheme();
	}

	getTheme(defaultValue = "system") {
		return this.get("theme", defaultValue);
	}
}

const config = new ConfigSingleton();

let currentUser = null;
let activeEventSource = null;

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
	switch (config.getTheme()) {
		case "dark": button.innerText = ICON_DARK; break;
		case "light": button.innerText = ICON_LIGHT; break;
		default: button.innerText = ICON_SYSTEM;
	};
}

// =========================================================================
// 2. AUTHENTICATION CONTROLS
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

function init_auth() {
	const loginForm = document.getElementById("login-form");
	const loginError = document.getElementById("login-error");

	if (loginForm) {
		loginForm.addEventListener("submit", (e) => {
			e.preventDefault();
			if (loginError) loginError.innerText = "";

			const email = document.getElementById("login-email").value.trim();
			const password = document.getElementById("login-password").value;

			fetch("/api/v1/auth/token", {
				method: "POST",
				headers: { "Content-Type": "application/x-www-form-urlencoded" },
				body: new URLSearchParams({ username: email, password: password })
			})
				.then((response) => response.json())
				.then((data) => {
					if (!response.ok) {
						if (loginError) loginError.innerText = data.detail || "Authentication failed.";
						return;
					}

					currentUser = data;
					sessionStorage.setItem("user", JSON.stringify(data));
					update_auth_ui();
				})
				.catch(() => {
					if (loginError) loginError.innerText = "Network error connecting to auth server.";
				})
		});
	}

	const registerForm = document.getElementById("register-form");
	const registerError = document.getElementById("register-error");

	if (registerForm) {
		registerForm.addEventListener("submit", (e) => {
			e.preventDefault();
			if (registerError) registerError.innerText = "";

			const fullName = document.getElementById("register-name").value.trim();
			const email = document.getElementById("register-email").value.trim();
			const password = document.getElementById("register-password").value;

			fetch("/api/v1/auth/register", {
				method: "POST",
				headers: { "Content-Type": "application/json" },
				body: JSON.stringify({ email: email, password: password, full_name: fullName })
			})
				.then( (response) => response.json())
				.then( (data) => {
					if (!response.ok) {
						if (registerError) registerError.innerText = data.detail || "Registration failed.";
						return;
					}

					currentUser = data;
					sessionStorage.setItem("user", JSON.stringify(data));
					update_auth_ui();
				})
				.catch(() => {
					if (registerError) registerError.innerText = "Network error connecting to auth server."
				});
		});
	}

	const logoutForm = document.getElementById("logout-form");
	if (logoutForm) {
		logoutForm.addEventListener("submit", (e) => {
			e.preventDefault();
			currentUser = null;
			sessionStorage.removeItem("user");
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
}

// =========================================================================
// 3. MULTI-DOCUMENT INGESTION WIZARD
// =========================================================================

function init_wizard() {
	// Setup file input indicators
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
		analysisForm.addEventListener("submit", (e) => {
			e.preventDefault();
			if (wizardError) wizardError.innerText = "";

			const companyName = document.getElementById("company_name").value.trim();
			const taxId = document.getElementById("tax_id").value.trim();
			const industryCode = document.getElementById("industry_code").value.trim();

			const statementFile = document.getElementById("file-statement").files[0];
			const invoicesFile = document.getElementById("file-invoices").files[0];
			const creditsFile = document.getElementById("file-credits").files[0];

			if (!statementFile) {
				if (wizardError) wizardError.innerText = "Bank statement file is required for cashflow analysis.";
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
				btn.innerText = "Dispatching pipeline...";
			}

			fetch("/api/v1/analysis/start", {
				method: "POST",
				headers: headers,
				body: formData
			})
				.then((response) => response.json())
				.then((data) => {
					if (!response.ok) {
						if (wizardError) wizardError.innerText = data.detail || "Failed to start analysis.";
						if (btn) {
							btn.disabled = false;
							btn.innerText = "🚀 Start Multi-Document Risk Analysis";
						}
						return;
					}

					const runId = data.run_id;
					start_telemetry_streaming(runId, companyName, taxId);
				})
				.catch((err) => {
					if (wizardError) wizardError.innerText = "Failed to dispatch analysis job: " + err.message;
					if (btn) {
						btn.disabled = false;
						btn.innerText = "🚀 Start Multi-Document Risk Analysis";
					}
				});
		});
	}
}

// =========================================================================
// 4. REAL-TIME SSE STREAM TELEMETRY (/api/v1/analysis/stream/{run_id})
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
	// Reveal telemetry section
	const telemetrySection = document.getElementById("telemetry-section");
	if (telemetrySection) telemetrySection.style.display = "block";
	telemetrySection.scrollIntoView({ behavior: "smooth" });

	document.getElementById("display-run-id").innerText = runId;
	document.getElementById("display-entity").innerText = companyName;
	document.getElementById("display-tax-id").innerText = taxId;

	clear_terminal();
	append_terminal("INFO", "SYS", `Connecting to telemetry stream for run ${runId}...`);

	if (activeEventSource) {
		activeEventSource.close();
	}

	const sseUrl = `/api/v1/analysis/stream/${runId}`;
	activeEventSource = new EventSource(sseUrl);

	activeEventSource.addEventListener("PIPELINE_STAGE_CHANGED", (e) => {
		try {
			const data = JSON.parse(e.data);
			update_progress(data.progress_percentage || 50, data.stage || "PROCESSING");
			append_terminal("INFO", "STAGE", `Transitioned to pipeline stage: ${data.stage}`);
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
			append_terminal("INFO", "DONE", `Evaluation completed. Final score: ${data.universal_score}`);
			update_progress(100, "COMPLETED");
			document.getElementById("run-status-badge").innerText = "COMPLETED";
			document.getElementById("run-status-badge").className = "badge badge-success";
			if (activeEventSource) activeEventSource.close();
			fetch_and_render_report(runId);
		} catch (err) {
			console.error("Error handling PIPELINE_COMPLETE:", err);
		}
	});

	activeEventSource.addEventListener("PIPELINE_FAILED", (e) => {
		try {
			const data = JSON.parse(e.data);
			append_terminal("ERROR", "FAIL", `Pipeline execution failed: ${data.error}`);
			document.getElementById("run-status-badge").innerText = "FAILED";
			document.getElementById("run-status-badge").className = "badge badge-danger";
			if (activeEventSource) activeEventSource.close();
		} catch (err) {
			console.error("Error handling PIPELINE_FAILED:", err);
		}
	});

	activeEventSource.onerror = (err) => {
		console.warn("EventSource connection encountered error / closed:", err);
		// Try fetching report once after short delay in case stream finished cleanly
		setTimeout(() => fetch_and_render_report(runId), 2000);
	};
}

// =========================================================================
// 5. UNDERWRITING REPORT DOSSIER RENDERING
// =========================================================================

function fetch_and_render_report(runId) {
	const headers = {};
	if (currentUser && currentUser.access_token) {
		headers["Authorization"] = `Bearer ${currentUser.access_token}`;
	}

	fetch(`/api/v1/analysis/report/${runId}`, { headers })
		.then((resp) => {
			if (!resp.ok)  {
				throw new Error("Guard failed: resp is not ok");
			}
			return resp.json()})
		.then((report) => {

			const reportSection = document.getElementById("report-section");
			if (reportSection) reportSection.style.display = "block";
			reportSection.scrollIntoView({ behavior: "smooth" });

			// Score & verdicts
			const scoreElem = document.getElementById("report-score");
			if (scoreElem) scoreElem.innerText = (report.universal_score != null) ? Number(report.universal_score).toFixed(1) : "--";

			const verdictElem = document.getElementById("report-verdict-badge");
			if (verdictElem) {
				verdictElem.innerText = report.risk_band || report.verdict || "UNKNOWN";
				verdictElem.className = "badge " + (report.risk_band === "PRIME_LOW_RISK" ? "badge-success" : (report.risk_band === "HIGH_RISK_REJECT" ? "badge-danger" : "badge-warning"));
			}

			const recElem = document.getElementById("report-rec-badge");
			if (recElem) {
				recElem.innerText = report.recommendation || report.verdict || "--";
				recElem.className = "badge " + (report.recommendation === "APPROVED" ? "badge-success" : (report.recommendation === "REJECTED" ? "badge-danger" : "badge-info"));
			}

			const pdElem = document.getElementById("report-pd");
			if (pdElem) {
				pdElem.innerText = (report.probability_of_default != null) ? `${(Number(report.probability_of_default) * 100).toFixed(2)}%` : "--%";
			}

			// LLM Executive Summary Memo
			const memoElem = document.getElementById("report-memo");
			if (memoElem) {
				const summaryText = report.executive_summary || report.llm_final_summary || "No memorandum available.";
				// Convert markdown headers and bolding to HTML
				const htmlText = summaryText
					.replace(/^### (.*$)/gim, '<h4>$1</h4>')
					.replace(/^## (.*$)/gim, '<h3>$1</h3>')
					.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
					.replace(/\n\n/g, '<br><br>')
					.replace(/\n- (.*$)/gim, '<li>$1</li>');
				memoElem.innerHTML = htmlText;
			}

			// Render Radar / Bar Chart SVG
			render_submodules_chart(report.submodules || []);

			// Render Submodules Cards
			render_submodule_cards(report.submodules || []);

		}).catch((err) => {
			console.error("Failed to render report dossier:", err)
		})

}

function render_submodules_chart(submodules) {
	const svg = document.getElementById("submodule-radar-svg");
	if (!svg) return;
	svg.innerHTML = "";

	if (!submodules || submodules.length === 0) return;

	const barWidth = 40;
	const barGap = 12;
	const maxBarHeight = 180;
	const startX = 20;
	const baseY = 240;

	submodules.forEach((sm, i) => {
		const x = startX + i * (barWidth + barGap);
		const scoreVal = sm.impact_weight ? (sm.impact_weight * 100) : 50.0;
		const h = (scoreVal / 100) * maxBarHeight;
		const y = baseY - h;

		const color = (sm.verdict === "STABLE" || sm.verdict === "PRIME" || sm.status === "ACTIVE") ? "#38bdf8" : (sm.status === "BYPASSED" ? "#fbbf24" : "#f87171");

		// Bar rect
		const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
		rect.setAttribute("x", x);
		rect.setAttribute("y", y);
		rect.setAttribute("width", barWidth);
		rect.setAttribute("height", h);
		rect.setAttribute("fill", color);
		rect.setAttribute("rx", "4");
		svg.appendChild(rect);

		// Label text
		const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
		text.setAttribute("x", x + barWidth / 2);
		text.setAttribute("y", baseY + 18);
		text.setAttribute("text-anchor", "middle");
		text.setAttribute("fill", "var(--clr-fg)");
		text.setAttribute("font-size", "11px");
		text.textContent = (sm.submodule_id || `SM${i+1}`).slice(0, 5);
		svg.appendChild(text);
	});
}

function render_submodule_cards(submodules) {
	const container = document.getElementById("submodules-reports-list");
	if (!container) return;
	container.innerHTML = "";

	submodules.forEach(sm => {
		const card = document.createElement("div");
		card.className = "submodule-report-card";

		const header = document.createElement("div");
		header.className = "sm-card-header";
		header.innerHTML = `
			<h4>[${sm.submodule_id || "SM"}] ${sm.title || "Diagnostic Submodule"}</h4>
			<span class="badge ${sm.status === 'ACTIVE' ? 'badge-success' : (sm.status === 'BYPASSED' ? 'badge-warning' : 'badge-info')}">
				${sm.status || 'ACTIVE'}
			</span>
		`;

		const body = document.createElement("div");
		body.className = "sm-card-body";
		body.innerHTML = `
			<p><strong>Verdict:</strong> ${sm.verdict || "Evaluated"}</p>
			<p><strong>Impact Weight:</strong> ${sm.impact_weight ? (sm.impact_weight * 100).toFixed(1) + '%' : "N/A"}</p>
			<div class="diagnostic-text">${sm.diagnostic_report || sm.summary || "Diagnostic metrics processed successfully."}</div>
		`;

		card.appendChild(header);
		card.appendChild(body);
		container.appendChild(card);
	});
}

function clear_report() {
	const company_name = document.getElementById("company_name");
	if (company_name) company_name.value = company_name.placeholder;

	const input_tax_id = document.getElementById("input_tax_id");
	if (input_tax_id) input_tax_id.value = input_tax_id.placeholder;

	const industry_code = document.getElementById("industry_code");
	if (industry_code) industry_code.value = industry_code.placeholder;

	const name_statement = document.getElementById("name-statement");
	if (name_statement) {
		name_statement.innerHTML = "No file chosen";
		verdictElem.className = "";
	}

	const name_invoices = document.getElementById("name-invoices");
	if (name_invoices) {
		name_invoices.innerHTML = "No file chosen";
		verdictElem.className = "";
	}

	const name_credits = document.getElementById("name-credits");
	if (name_credits) {
		name_credits.innerHTML = "No file chosen";
		verdictElem.className = "";
	}

	const file_statement = document.getElementById("file-statement");
	if (file_statement) file_statement.value = "";

	const file_invoices = document.getElementById("file-invoices");
	if (file_invoices) file_invoices.value = "";

	const file_credits = document.getElementById("file-credits");
	if (file_credits) file_credits.value = "";

	const reportSection = document.getElementById("report-section");
	if (reportSection) reportSection.style.display = "none";

	// Score & verdicts
	const scoreElem = document.getElementById("report-score");
	if (scoreElem) scoreElem.innerText = "--";

	const verdictElem = document.getElementById("report-verdict-badge");
	if (verdictElem) {
		verdictElem.innerText = "--";
		verdictElem.className = "badge";
	}

	const recElem = document.getElementById("report-rec-badge");
	if (recElem) {
		recElem.innerText = "--";
		recElem.className = "badge";
	}

	const pdElem = document.getElementById("report-pd");
	if (pdElem) {
		pdElem.innerText = "--%";
	}

	const memoElem = document.getElementById("report-memo");
	if (memoElem) {
		memoElem.innerHTML = "Awaiting analysis completion...";
	}

	const svg = document.getElementById("submodule-radar-svg");
	if (svg) svg.innerHTML = "";

	const container = document.getElementById("submodules-reports-list");
	if (container) container.innerHTML = "";
}


// =========================================================================
// 6. INITIALIZATION HOOK
// =========================================================================

document.addEventListener('DOMContentLoaded', function() {
	restore_theme();
	upd_status();
	init_auth();
	init_wizard();
}, false);
