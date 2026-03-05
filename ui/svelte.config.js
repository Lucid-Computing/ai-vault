import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		adapter: adapter({
			pages: '../ai_vault/static',
			assets: '../ai_vault/static',
			fallback: 'index.html',
			precompress: false
		}),
		paths: {
			base: ''
		}
	}
};

export default config;
