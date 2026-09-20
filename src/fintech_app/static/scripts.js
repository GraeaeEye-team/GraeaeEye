class ConfigSingleton {
	constructor() {
		this.applyTheme();
	}

	async set(name, value) {
		await cookieStore.set(name, value);
	}

	async get(name, defaultValue) {
		try {
			const vvalue = await cookieStore.get(name);
			return vvalue !== undefined ? vvalue.value : defaultValue;
		} catch {
			return defaultValue;
		}
	}

	async applyTheme() {
		this.getTheme().then((theme) => document.documentElement.setAttribute('data-theme', theme));
	}

	async setTheme(newTheme) {
		await cookieStore.set('theme', newTheme);
		await this.applyTheme();
	}

	async getTheme(defaultValue = "system") {
		return this.get("theme", defaultValue);
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

	document.getElementById('theming-form').addEventListener('submit', async (e) => {
		e.preventDefault();

		fetch("/health")
			.then((response) => response.json())
		console.log("!")
		const theme = document.getElementById("themes");
		const themename = theme.options[theme.selectedIndex >= 0 ? theme.selectedIndex : 1].text;
		config.setTheme();
		console.log("Appling new theme!", themename);
		console.log(config.getTheme())
	});
}

document.addEventListener('DOMContentLoaded', function() {
	init_forms();
}, false);
