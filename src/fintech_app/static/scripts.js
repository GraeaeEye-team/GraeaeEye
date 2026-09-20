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
	fetch("/health")
		.then((response) => response.json())
		.then(
			(json) => status.innerHTML = json.status == "ok" ? json.service + " is ok" : "Internal error!"
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

function init_forms() {
	document.getElementById('add-form').addEventListener('submit', async (e) => {
		e.preventDefault();
		const from = "/api/v1/scenarios/simulate";

		fetch(from, {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({ })
		})
			.then((response_post) => response_post.json())
			.then((json) => {
				const sim = document.getElementById('simulate');
				sim.innerHTML = json.status;
			})
	});

}

function restore_theme() {
	const button = document.getElementById("theming")
	config.getTheme().then((theme) => {switch (theme) {
		case "dark":  button.innerText = "🌙"; break;
		case "light": button.innerText = "🌣"; break;
		default :     button.innerText = "🌗";
	}});
}

document.addEventListener('DOMContentLoaded', function() {
	init_forms();
	restore_theme();
}, false);
