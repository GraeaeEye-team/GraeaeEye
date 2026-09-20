class ConfigSingleton {
	constructor() {
		this.applyTheme();
	}

	async set(name, value) {
		if (typeof cookieStore !== 'undefined') {
			try {
				await cookieStore.set(name, value);
				return;
			} catch (e) {
				console.warn("cookieStore.set failed:", e);
			}
		}

		try {
			localStorage.setItem(name, value);
		} catch (e) {
			console.warn("localStorage.set failed:", e);
		}

	}

	async get(name, defaultValue) {
		try {
			const vvalue = await cookieStore.get(name);
			return vvalue !== undefined && vvalue.value !== undefined ? vvalue.value : defaultValue;
		} catch {
			const local = localStorage.getItem(name);
			return (local !== null) ? local : defaultValue;
		}
	}

	async applyTheme() {
		this.getTheme().then((theme) => document.documentElement.setAttribute('data-theme', theme));
	}

	async setTheme(newTheme) {
		await this.set('theme', newTheme);
		await this.applyTheme();
	}

	async getTheme(defaultValue = "system") {
		const response = this.get("theme", defaultValue);
		return response;
	}
}

const config = new ConfigSingleton();

function upd_status() {
	const status = document.getElementById("status");
	fetch("/api/v1/health")
		.then((response) => response.json())
		.then(
			(json) => status.innerHTML = json.status == "ok" ? json.db + " is ok" : "Internal error!"
		)
}

function upd_theme() {
	const button = document.getElementById("theming")
	if (button.innerText == "🌗") {
		config.setTheme("dark")
		button.innerText = "🌙"
	} else if (button.innerText == "🌙") {
		config.setTheme("light")
		button.innerText = "🌣"
	} else {
		config.setTheme("system")
		button.innerText = "🌗"
	}
}

let currentUser = null;

function update_auth_ui() {
	const guestBlock = document.getElementById("auth-guest");
	const loggedInBlock = document.getElementById("auth-logged-in");

	if (currentUser) {
		if (guestBlock) guestBlock.style.display = "none";
		if (loggedInBlock) loggedInBlock.style.display = "block";

		const nameElem = document.getElementById("user-name");
		const roleElem = document.getElementById("user-role");
		const emailElem = document.getElementById("user-email");

		if (nameElem) nameElem.innerText = currentUser.full_name;
		if (roleElem) roleElem.innerText = currentUser.role;
		if (emailElem) emailElem.innerText = currentUser.email;
	} else {
		if (guestBlock) guestBlock.style.display = "block";
		if (loggedInBlock) loggedInBlock.style.display = "none";
	}
}

function init_auth() {
	const loginForm = document.getElementById("login-form");
	const loginError = document.getElementById("login-error");

	if (loginForm) {
		loginForm.addEventListener("submit", async (e) => {
			e.preventDefault();
			if (loginError) loginError.innerText = "";

			const email = document.getElementById("login-email").value;
			const password = document.getElementById("login-password").value;

			try {
				const response = await fetch("/api/v1/auth/token", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ email, password })
				});

				const data = await response.json();

				if (!response.ok) {
					if (loginError) {
						loginError.innerText = data.detail || "Ошибка авторизации";
					}
					return;
				}

				currentUser = data;
				sessionStorage.setItem("user", JSON.stringify(data));
				loginForm.reset();
				update_auth_ui();
			} catch (err) {
				if (loginError) loginError.innerText = "Не удалось связаться с сервером.";
			}
		});
	}

	const registerForm = document.getElementById("register-form");
	const registerError = document.getElementById("register-error");

	if (registerForm) {
		registerForm.addEventListener("submit", async (e) => {
			e.preventDefault();
			if (registerError) registerError.innerText = "";

			const fullName = document.getElementById("register-name").value;
			const email = document.getElementById("register-email").value;
			const password = document.getElementById("register-password").value;

			try {
				const response = await fetch("/api/v1/auth/register", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						email: email,
						password: password,
						full_name: fullName
					})
				});

				const data = await response.json();

				if (!response.ok) {
					let errorMsg = "Ошибка регистрации";
					if (typeof data.detail === "string") {
						errorMsg = data.detail;
					} else if (Array.isArray(data.detail)) {
						errorMsg = data.detail.map(d => d.msg || JSON.stringify(d)).join("; ");
					}
					if (registerError) registerError.innerText = errorMsg;
					return;
				}

				currentUser = data;
				sessionStorage.setItem("user", JSON.stringify(data));
				registerForm.reset();
				update_auth_ui();
			} catch (err) {
				if (registerError) registerError.innerText = "Не удалось связаться с сервером.";
			}
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

function restore_theme() {
	const button = document.getElementById("theming");
	if (!button) return;

	config.getTheme().then((theme) => {switch (theme) {
		case "dark":  button.innerText = "🌙"; break;
		case "light": button.innerText = "🌣"; break;
		default :     button.innerText = "🌗";
	}});
}

document.addEventListener('DOMContentLoaded', function() {
	restore_theme();
	init_auth();
}, false);
