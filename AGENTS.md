## Learned User Preferences

- Prefer short one-line comments that explain purpose, not step-by-step operations.
- Prefer fine-grained, human-style commits over large single AI-generated commits.
- Remove AI-generated comments and replace with personal ones before committing.
- Prefer PR descriptions as clear ELI5-style bullet points; avoid AI-sounding prose.

## Learned Workspace Facts

- sveltekit-python-vercel is a Deno project; build the npm package with `deno task dnt` or `deno run -A dnt.ts <version>` (output in `npm/`, gitignored). `deno task build` does not pass a version to dnt.ts.
- Link consumer projects to the built package with `link:../sveltekit-python-vercel/npm` for local dev only — commit `^x.y.z` or `@beta` in deploy repos for Vercel.
- npm publishes only from `.github/workflows/publish.yml` (npm trusted publishing allows one workflow per package): `beta` on main push, `pr-<n>` on same-repo PRs, `latest` on GitHub Release.
- After rebuilding the linked package, restart the Vite dev server; reinstall in the consumer is usually not needed.
- Local dev requires the sveltekit-python-vercel Vite plugin, which starts uvicorn on port 8000; proxy-only setups cause "fetch failed".
- test-skpv-deploy is the test/deploy project for sveltekit-python-vercel.
- test-skpv-deploy uses vendored `_python/build.py` for Vercel deploy (`vercel.json` buildCommand).
- Pydantic: `field: type = default` works; prefer `Field(default=...)` for validation constraints; use `int` for params passed to numpy.
- CI/publish requires Deno 2.x (`deno.lock` v5 needs 2.3+); use `denoland/setup-deno@v2` with `deno-version: v2.x`.
- After dnt build, `dnt.ts` overwrites `npm/.npmignore` because dnt's default `src/` rule excludes needed `esm/src/` paths from the published tarball.
- Python load files (`+page.server.py`, `+layout.server.py`): no user pip install; use return tuples (`("error", 404, "msg")`) or injected `error()`/`redirect()` helpers without imports.
