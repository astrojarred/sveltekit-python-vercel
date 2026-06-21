import {type Plugin} from "vite";
import {
  type ProcessPromise,
  $ as run$,
  cd as cd$,
  which,
  path,
  chalk,
} from "zx";

const get_pyServerEndpointAsString = (app_url: URL, serve = false) => `
    const handle = (method) => (async ({ request, fetch, url }) => {
        const headers = new Headers()
        headers.append('content-type', request.headers.get('content-type'));
        headers.append('accept', request.headers.get('accept'));

        let fullURL;

        if (${serve}) {
          fullURL = new URL('/api' + url.pathname, new URL('${app_url}')) + url.search;
        } else {
          fullURL = new URL('/api' + url.pathname, url.origin) + url.search;
        }

        console.log(\`PY: Reached python endpoint of \${method} \${fullURL}\`)
        let requestBody = await request.clone().text();
        console.log(\`PY: Body: \${requestBody}\`);

        if (method === 'GET') {
          requestBody = null;
        }

        return fetch(fullURL, { headers, method, body: requestBody, signal: request.signal, duplex: 'half' });
    });
    
    export const GET = handle('GET');
    export const POST = handle('POST');
    export const PATCH = handle('PATCH');
    export const PUT = handle('PUT');
    export const DELETE = handle('DELETE');
`;

function getLoadRouteTemplate(id: string): string {
  const marker = "/src/routes/";
  const idx = id.indexOf(marker);
  if (idx === -1) {
    throw new Error(`Cannot derive load route from ${id}`);
  }

  let routePart = id.slice(idx + marker.length);
  routePart = routePart.replace(/\/\+(?:page|layout)\.server\.py$/, "");

  if (!routePart) {
    return "/api/_load";
  }

  const segments = routePart
    .split("/")
    .filter((part) => !(part.startsWith("(") && part.endsWith(")")))
    .map((part) => part.replace(/^\[(.+)\]$/, "{$1}"));

  return `/api/_load/${segments.join("/")}`;
}

const get_pyLoadAsString = (
  loadRouteTemplate: string,
  app_url: URL,
  serve = false
) => `
    import { error, redirect } from '@sveltejs/kit';

    const LOAD_ROUTE_TEMPLATE = ${JSON.stringify(loadRouteTemplate)};

    function buildLoadPath(params) {
        let path = LOAD_ROUTE_TEMPLATE;
        for (const [key, value] of Object.entries(params)) {
            path = path.replaceAll(\`{\${key}}\`, encodeURIComponent(String(value)));
        }
        return path;
    }

    export async function load(event) {
        const parent = event.parent ? await event.parent() : undefined;

        const body = JSON.stringify({
            params: event.params,
            route: { id: event.route.id },
            url: event.url.href,
            parent,
            data: event.data ?? undefined,
            cookies: Object.fromEntries(event.cookies.getAll().map((c) => [c.name, c.value])),
        });

        const apiPath = buildLoadPath(event.params);
        const fullURL = ${serve}
            ? new URL(apiPath, new URL('${app_url}'))
            : new URL(apiPath, event.url.origin);

        const res = await event.fetch(fullURL, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body,
        });

        const result = await res.json();

        if (result.type === 'redirect') redirect(result.status, result.location);
        if (result.type === 'error') error(result.status, result.body);
        return result.data;
    }
`;

function isPyServerFile(id: string): boolean {
  return /\+server\.py$/.test(id);
}

function isPyLoadFile(id: string): boolean {
  return /\+(?:page|layout)\.server\.py$/.test(id);
}

export interface SveltekitPythonOptions {
  python_path?: string;
  log?: boolean;
  host?: string;
  port?: number;
}

export async function sveltekit_python_vercel(
  opts: SveltekitPythonOptions = {}
): Promise<Plugin[]> {
  const child_processes: ProcessPromise[] = [];
  async function kill_all_process() {
    for (const ps of child_processes) {
      await ps.kill();
      await ps.exitCode;
    }
  }

  let sveltekit_url: URL | undefined;

  const plugin_python_serve: Plugin = {
    name: "vite-plugin-sveltekit-python-serve",
    apply: "serve",
    async closeBundle() {
      await kill_all_process();
    },
    async configureServer({config}) {
      const packagelocation = path.join(
        config.root,
        "node_modules",
        "sveltekit-python-vercel",
        "esm/src/vite"
      );

      run$.verbose = false;
      run$.env.PYTHONDONTWRITEBYTECODE = "1";

      cd$(packagelocation);

      const python_path = opts.python_path ?? (await which("python3"));
      const host = opts.host ?? "0.0.0.0";
      const port = opts.port ?? 8000;
      const local_process: ProcessPromise = run$`${python_path} -m sveltekit_python_vercel.serve --host ${host} --port ${port} --root ${config.root}`;
      child_processes.push(local_process);

      sveltekit_url ??= new URL(`http://${host}:${port}`);

      cd$(config.root);

      local_process.nothrow();

      local_process.stderr.on("data", (s) => {
        console.log(s.toString().trimEnd());
      });
      local_process.stderr.on("error", (s) => {
        console.error(chalk.red("Error: Python Serve Failed"));
        console.error(s.toString().trimEnd());
      });

      local_process.stdout.on("error", (s) => {
        console.error(chalk.red("Error: Python Serve Failed"));
        console.error(s.toString().trimEnd());
      });
    },
  };

  const plugin_python_build: Plugin = {
    name: "vite-plugin-sveltekit_python-build",
    apply: "build",
    async configResolved(config) {
      console.log("PY: ROOT PATH: " + config.root);
    },
  };

  const transformPyFile = (
    id: string,
    serve: boolean,
    app_url: URL
  ): {code: string; map: null} | undefined => {
    if (!/\.py$/.test(id)) return undefined;

    if (isPyServerFile(id)) {
      return {
        code: get_pyServerEndpointAsString(app_url, serve),
        map: null,
      };
    }

    if (isPyLoadFile(id)) {
      const loadRouteTemplate = getLoadRouteTemplate(id);
      return {
        code: get_pyLoadAsString(loadRouteTemplate, app_url, serve),
        map: null,
      };
    }

    return undefined;
  };

  const plugin_py_server_endpoint_serve: Plugin = {
    name: "vite-plugin-sveltekit_python-server-endpoint",
    apply: "serve",
    transform(src, id) {
      if (sveltekit_url === undefined) {
        throw new Error(
          `${plugin_python_serve.name} failed to produce a sveltekit_url`
        );
      }
      return transformPyFile(id, true, sveltekit_url);
    },
  };

  const plugin_py_server_endpoint_build: Plugin = {
    name: "vite-plugin-sveltekit_python-server-endpoint",
    apply: "build",
    transform(src, id) {
      return transformPyFile(id, false, new URL("http://localhost"));
    },
  };

  return [
    plugin_python_serve,
    plugin_python_build,
    plugin_py_server_endpoint_serve,
    plugin_py_server_endpoint_build,
  ];
}
