// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
	integrations: [
		starlight({
			title: 'Ghost in the Droid',
			tagline: 'Open-source Android automation framework',
			social: [
				{ icon: 'github', label: 'GitHub', href: 'https://github.com/ghost-in-the-droid/android-agent' },
				{ icon: 'external', label: 'Home', href: '/' },
				{ icon: 'puzzle', label: 'Skill Hub', href: '/skills/' },
			],
			customCss: ['./src/styles/custom.css'],
			head: [
				{
					tag: 'script',
					content: `
document.addEventListener('DOMContentLoaded', function() {
	var nav = document.querySelector('header nav .right-group, header nav');
	if (!nav) return;
	var socialLinks = nav.querySelector('.social-icons, [class*="social"]');
	var wrap = document.createElement('div');
	wrap.style.cssText = 'display:flex;gap:1rem;align-items:center;margin-right:0.75rem;';
	['Home:/', 'Skill Hub:/skills/'].forEach(function(item) {
		var parts = item.split(':');
		var a = document.createElement('a');
		a.href = parts[1];
		a.textContent = parts[0];
		a.style.cssText = 'font-size:0.8rem;color:var(--sl-color-gray-3);text-decoration:none;transition:color 0.15s;white-space:nowrap;';
		a.onmouseover = function() { a.style.color = 'var(--sl-color-white)'; };
		a.onmouseout = function() { a.style.color = 'var(--sl-color-gray-3)'; };
		wrap.appendChild(a);
	});
	if (socialLinks) socialLinks.before(wrap);
	else nav.appendChild(wrap);
});
					`,
				},
				{
					tag: 'script',
					content: `
document.addEventListener('DOMContentLoaded', function() {
	var btn = document.createElement('button');
	btn.id = 'ghost-theme-toggle';
	btn.title = 'Toggle dark/light mode';
	function isDark() {
		var t = document.documentElement.dataset.theme;
		if (t === 'dark') return true;
		if (t === 'light') return false;
		return window.matchMedia('(prefers-color-scheme: dark)').matches;
	}
	function updateIcon() { btn.textContent = isDark() ? '🌙' : '☀️'; }
	updateIcon();
	btn.addEventListener('click', function() {
		var next = isDark() ? 'light' : 'dark';
		var sel = document.querySelector('starlight-theme-select select');
		if (sel) { sel.value = next; sel.dispatchEvent(new Event('change')); }
		setTimeout(updateIcon, 50);
	});
	new MutationObserver(updateIcon).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
	var rightGroup = document.querySelector('.right-group');
	if (rightGroup) {
		rightGroup.appendChild(btn);
	} else {
		var header = document.querySelector('header.header');
		if (header) header.appendChild(btn);
	}
});
					`,
				},
			],
			sidebar: [
				{
					label: '🚀 Getting Started',
					items: [
						{ label: '👻 Introduction', slug: 'getting-started/introduction' },
						{ label: '📥 Installation', slug: 'getting-started/installation' },
						{ label: '📱 Connect a Phone', slug: 'getting-started/connect-phone' },
						{ label: '🚀 Hello World', slug: 'getting-started/hello-world' },
					],
				},
				{
					label: '📚 Guides',
					items: [
						{ label: '🎵 TikTok Upload', slug: 'guides/tiktok-upload' },
						{ label: '🖥️ Phone Farm', slug: 'guides/phone-farm' },
						{ label: '🎬 Record Macros', slug: 'guides/macros' },
						{ label: '🥷 Stealth Mode', slug: 'guides/stealth' },
					],
				},
				{
					label: '🧩 Skills',
					items: [
						{ label: '🧩 What Are Skills?', slug: 'skills/overview' },
						{ label: '⚡ Using Skills', slug: 'skills/using-skills' },
						{ label: '🔨 Creating Skills', slug: 'skills/creating-skills' },
						{ label: '🎯 Elements & Locators', slug: 'skills/elements' },
						{ label: '📦 Publishing Skills', slug: 'skills/publishing' },
					],
				},
				{
					label: '⚡ Features',
					items: [
						{ label: '📲 ADB Device Control', slug: 'features/adb-device' },
						{ label: '🧠 Skill System', slug: 'features/skill-system' },
						{ label: '📦 Skill Hub', slug: 'features/skill-hub' },
						{ label: '⚙️ Execution Engine', slug: 'features/skill-execution-engine' },
						{ label: '🛠️ Skill Creator', slug: 'features/skill-creator' },
						{ label: '⛏️ App Explorer', slug: 'features/app-explorer' },
						{ label: '🔌 MCP Server', slug: 'features/mcp-server' },
						{ label: '📋 Dashboard', slug: 'features/dashboard' },
						{ label: '⏰ Scheduler', slug: 'features/scheduler' },
						{ label: '🎥 WebRTC Streaming', slug: 'features/webrtc' },
						{ label: '🎬 Macro Recorder', slug: 'features/macro-recorder' },
						{ label: '🥷 Stealth Mode', slug: 'features/stealth-mode' },
						{ label: '📎 Device Context', slug: 'features/device-context' },
						{ label: '🖥️ Emulators', slug: 'features/emulator', badge: { text: 'Coming Soon', variant: 'caution' } },
					],
				},
				{
					label: '📖 API Reference',
					items: [
						{ label: '📖 Device Methods', slug: 'api/device-methods' },
						{ label: '🌐 REST Endpoints', slug: 'api/rest-endpoints' },
						{ label: '🧬 Skill Classes', slug: 'api/skill-classes' },
						{ label: '💻 CLI', slug: 'api/cli' },
					],
				},
				{
					label: '🤝 Contributing',
					items: [
						{ label: '🏗️ Dev Setup', slug: 'contributing/setup' },
						{ label: '📝 Code Guidelines', slug: 'contributing/code' },
						{ label: '🧩 Contribute Skills', slug: 'contributing/skills' },
						{ label: '🎨 Style Guide', slug: 'contributing/style-guide' },
						{ label: '🖌️ Dashboard Theme', slug: 'contributing/dashboard-theme' },
					],
				},
				{ label: '⚠️ Troubleshooting', slug: 'troubleshooting' },
				{
					label: 'Legal',
					items: [
						{ label: 'Privacy Policy', slug: 'privacy' },
						{ label: 'Terms of Service', slug: 'terms' },
					],
				},
			],
		}),
	],
});
