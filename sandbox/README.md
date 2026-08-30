# Sandbox devcontainer — hemat-token-router

## Firewall (egress DENY-BY-DEFAULT)

Container dibatasi egress via `iptables`/`nft` (allowlist). Karena devcontainer
memaksa entrypoint `/bin/sh` dan `postStartCommand` jalan sebagai user non-root
(`dev`), firewall **tidak bisa self-apply** — harus dipicu dari **host** via
`docker exec -u 0`.

### Langkah setelah `Reopen in Container`

```bash
# di host, setelah VS Code "Reopen in Container" selesai
bash sandbox/apply-firewall.sh
```

`apply-firewall.sh` otomatis menemukan container `vsc-hemat-token-router*` yang
running, atau pakai `CONTAINER=<id> bash sandbox/apply-firewall.sh`. Di dalam
container script ini menjalankan `/opt/csmart/init-firewall.sh` (butuh
`--cap-add=NET_ADMIN` — sudah diatur di `devcontainer.json` `runArgs`).

`init-firewall.sh` idempotent & deterministik: policy `OUTPUT DROP` + allowlist
`127.0.0.0/8` (loopback untuk `127.0.0.1:8080`), `DNS 53`, `TCP 443` ke
`${UPSTREAM_BASE_URL}` (default `api.deepseek.com`) + OpenCode + preflight
`api.anthropic.com`. Fallback ke `nft` bila `iptables` tidak ada.

### Verify

```bash
# di host — lihat policy OUTPUT = DROP dan allowlist
docker exec -u 0 <container> iptables -L OUTPUT -n -v
# atau via helper (exec sebagai root di dalam):
docker exec -u 0 <container> iptables -S OUTPUT
```

Tanpa firewall, `iptables -P OUTPUT` masih `ACCEPT`. Setelah `apply-firewall.sh`
harus `DROP` dengan rule `ACCEPT` untuk `127.0.0.0/8`, `dpt:53`, `dpt:443`.

> Opsional: aktifkan allowlist `git`/`registry` via `GIT_ALLOW="registry.npmjs.org github.com"`
> (default off — lihat comment di `init-firewall.sh:39`).

## UX attach

`devcontainer.json` set eksplisit:

- `workspaceFolder: /workspace` — sesuai `Dockerfile` `WORKDIR /workspace`
- `remoteUser: dev` — sesuai `Dockerfile` `USER dev` (uid 1000)

Tanpa ini VS Code kadang mount workspace ke path default yang salah dan terminal
jalan sebagai `root`.
