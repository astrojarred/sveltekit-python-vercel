<p align="middle">
<img width="100" alt="image" src="https://user-images.githubusercontent.com/20548516/218344678-d41f4c4a-6b1b-48cc-8553-2b9fbe2169d6.png"/>
<img width="100" alt="image" src="https://avatars.githubusercontent.com/u/1525981?s=200&v=4"/>
<img width="100" alt="image" src="https://avatars.githubusercontent.com/u/14985020?s=200&v=4"/>
</p>

# sveltekit-python-vercel

Write Python endpoints in [SvelteKit](https://kit.svelte.dev/) and seamlessly deploy them to Vercel.

- [Current Features](#current-features)
- [Installing](#installing)
- [Testing Locally](#testing-locally)
- [Deploying to Vercel](#deploying-to-vercel)
- [Example](#example)
  - [Backend Caveats](#backend-caveats)
- [Fork of `sveltekit-modal`](#fork-of-sveltekit-modal)
- [Possible future plans](#possible-future-plans)

**This is very much in beta.**

## Current Features

- Write `+server.py` files nearly the same way you would write `+server.js` files
- Write server `load` functions in `+page.server.py` and `+layout.server.py`
- Deploy automatically to Vercel Serverless (Python 3.12 runtime)

## Installing

- Open or set up your SvelteKit project
- Install SvelteKit's Vercel adapter: `pnpm i -D @sveltejs/adapter-vercel`
- Install with `pnpm i -D sveltekit-python-vercel`
- Update your `vite.config.js`

  ```javascript
  import { defineConfig } from "vite";
  import { sveltekit } from "@sveltejs/kit/vite";
  import { sveltekit_python_vercel } from "sveltekit-python-vercel/vite";

  export default defineConfig({
    plugins: [sveltekit(), ...(await sveltekit_python_vercel())],
  });
  ```

- Update your `svelte.config.js`:

  ```javascript
  import adapter from "@sveltejs/adapter-vercel";
  import { vitePreprocess } from "@sveltejs/kit/vite";

  /** @type {import('@sveltejs/kit').Config} */
  const config = {
    preprocess: vitePreprocess(),
    kit: {
      adapter: adapter(),
      moduleExtensions: [".js", ".ts", ".py"], // add ".py" to resolve +server.py endpoints
    },
  };

  export default config;
  ```

- Update your `vercel.json`

  - The build command first runs `vite build` (which generates `.vercel/output/` via the SvelteKit adapter), then runs our script to write the Python function into that same output directory and patch the routing config.
  - No `routes` or `functions` keys are needed — routing is handled automatically via the [Vercel Build Output API](https://vercel.com/docs/build-output-api/v3).

  ```json
  {
    "buildCommand": "vite build; node ./node_modules/sveltekit-python-vercel/esm/src/vite/sveltekit_python_vercel/bin.mjs"
  }
  ```

- Write some `+server.py` endpoints. See the example section below.

## Testing Locally

[uv](https://docs.astral.sh/uv/) is recommended for managing your Python environment.

- Run `uv init --python 3.12` to create a `pyproject.toml` pinned to Python 3.12 (the same version Vercel's runtime uses).
- Add the required packages: `uv add fastapi uvicorn`
- Add any other dependencies you need: `uv add numpy pandas ...`
- Run your dev server inside uv:
  - `uv run pnpm dev`
- You should see both the usual SvelteKit server start and the uvicorn server (by default on `http://0.0.0.0:8000`) in the console.

## Deploying to Vercel

Just push to your repository — no extra steps required.

- The `buildCommand` in `vercel.json` handles everything automatically:
  1. `vite build` runs the SvelteKit build and writes `.vercel/output/` via `@sveltejs/adapter-vercel`
  2. `bin.mjs` then writes your Python endpoints into `.vercel/output/functions/` using the [Build Output API](https://vercel.com/docs/build-output-api/v3) and patches the routing config
- Your `+server.py` files and dependency declarations (`requirements.txt`, `pyproject.toml`, `Pipfile`, etc.) are bundled automatically — there is no need to commit an `/api` folder or manually generate a `requirements.txt`.
- Python packages are pre-installed into the function bundle at build time using `pip install --target`, so they are available in Vercel's raw Python 3.12 Lambda environment without any extra configuration.

## Example

- Frontend: `/src/routes/py/+page.svelte`

  ```html
  <script>
    let a = $state(0);
    let b = $state(0);
    let total = $state(0);

    async function pyAddPost() {
      const res = await fetch("/py", {
        method: "POST",
        body: JSON.stringify({ a, b }),
        headers: { "content-type": "application/json" },
      });
      total = (await res.json()).sum;
    }

    async function pyAddGet() {
      const res = await fetch(`/py?a=${a}&b=${b}`);
      total = (await res.json()).sum;
    }
  </script>

  <h1>SvelteKit page with a Python backend</h1>

  <label>a: <input type="number" bind:value={a} /></label>
  <label>b: <input type="number" bind:value={b} /></label>

  <button type="button" onclick={pyAddPost}>POST</button>
  <button type="button" onclick={pyAddGet}>GET</button>

  <p>Total: {total}</p>
  ```

- Backend: `/src/routes/py/+server.py`

  ```python
  from pydantic import BaseModel


  class NumberSet(BaseModel):
      a: float
      b: float


  async def POST(data: NumberSet):
      return {"sum": data.a + data.b}


  async def GET(a: float, b: float):
      return {"sum": a + b}
  ```

### Backend Caveats

- `GET` endpoints receive query parameters directly as function arguments. Type annotations are used for coercion (e.g. `a: float` parses `?a=3` as `3.0`).
- All other HTTP methods receive the request body as JSON. The recommended pattern is a Pydantic model as the single argument — FastAPI handles validation and parsing automatically.

### Python load functions

Server-side `load` functions work in `+page.server.py` and `+layout.server.py`. No extra Python package install is required — the runtime is bundled automatically like `+server.py`.

```python
async def load(event):
    if event.params["id"] == "secret":
        return ("redirect", 307, "/demo/public")

    if event.params["id"] not in ("public", "1", "2"):
        return ("error", 404, "Not found")

    return {
        "title": f"Item {event.params['id']}",
        "parent_theme": event.parent.theme if event.parent else None,
    }
```

Errors and redirects can also use injected helpers (no import needed):

```python
async def load(event):
    if not event.cookies.get("session"):
        redirect(307, "/login")
    return {"ok": True}
```

Available on `event`: `params`, `url`, `route`, `parent` (layout data), `data` (from a sibling universal load), `cookies`.

**Current limitations:** no `event.fetch`, `setHeaders`, `depends`, or page options (`prerender`, etc.) in `.py` files yet.

## npm channels

| Tag | When it updates | Install |
|-----|-----------------|---------|
| `latest` | GitHub Release created | `pnpm add -D sveltekit-python-vercel` |
| `beta` | Every push to `main` | `pnpm add -D sveltekit-python-vercel@beta` |
| `pr-<n>` | Open/update PR `#n` (same-repo only) | `pnpm add -D sveltekit-python-vercel@pr-15` |

Beta versions look like `1.0.3-beta.abc1234` (main) or `1.0.3-beta.pr15.abc1234` (PRs).

All publishes run through `.github/workflows/publish.yml` because npm trusted publishing only allows one workflow filename per package.

### Developing the package locally

If you work on this repo and a consumer app side by side (e.g. `test-skpv-deploy`):

1. Build: `deno run -A dnt.ts $(npm view sveltekit-python-vercel version)` (or any version string)
2. In the consumer: `pnpm add -D sveltekit-python-vercel@link:../sveltekit-python-vercel/npm`
3. Rebuild and restart the consumer dev server after library changes

Commit `^x.y.z` or `@beta` in the consumer for Vercel — `link:` only works on your machine.

## Fork of `sveltekit-modal`

Check out the awesome [sveltekit-modal](https://github.com/semicognitive/sveltekit-modal) package by [@semicognitive](https://github.com/semicognitive), the original way to get your python code running in SvelteKit. Modal even has GPU support for running an entire ML stack within SvelteKit.

## Possible future plans

- [X] Add hot reloading in dev mode
- [X] Generate endpoints automatically during build (via Vercel Build Output API)
  - [X] Auto-bundle requirements.txt / pyproject.toml / Pipfile at build time
- [ ] Add form actions
- [X] Add load functions
- [ ] Add helper functions to automatically call API endpoints in project
