# 12 — PostgreSQL container provisioning

**Depends on:** 04, 07
**Reference:** ARCHITECTURE.md §3 (Docker, PostgreSQL), §4 (Hosts/Docker), §8.3 (PostgreSQL image
and version), §9.1 (PostgreSQL identity)

## Goal

Create, or reuse, the local PostgreSQL container that holds the JidoTa database, reachable from
`127.0.0.1` only.

## Job to do

1. `Hosts/Docker` drives the `docker` CLI through the process runner of ticket 07:
   - inspect: `docker container inspect <name>`;
   - create: `docker run -d --name <name> -p 127.0.0.1:<port>:5432 -v <volume>:/var/lib/postgresql/data -e POSTGRES_USER=<user> -e POSTGRES_PASSWORD -e POSTGRES_DB=<db> <image>`
     (`-e POSTGRES_PASSWORD` with no value takes it from the environment of the `docker` process);
   - start a stopped container: `docker start <name>`.
2. The port is published on `127.0.0.1` only, never on all interfaces (§3).
3. The password is random, generated once, stored in `secrets.json` (ticket 04), and passed to
   `docker` through the environment of the process, not as an argument: the command line of a
   process can be read by other local users. Never logged (Invariant 11).
4. Reuse: a container that exists is started if stopped, never recreated; its volume is never
   removed.
5. Wait until the database accepts a connection before returning.

> The PostgreSQL image and version are **Not decided** (§8.3, "chosen when `Hosts/Docker` is
> written"). Choose the current major `postgres` image, pin it by tag, and record the choice in the
> code and in ARCHITECTURE.md §8.3.

## Automated tests

- `Category=Unit`, fake runner: create sends `-p 127.0.0.1:<port>:5432` and no password in argv;
  an existing running container gives no `docker run`; a stopped one gives `docker start`.
- `Category=Integration` (Docker): provision a container with a test name, connect, provision again
  (reused, same data), remove it in the test cleanup.

## How to verify

`docker ps` after provisioning shows the container bound to `127.0.0.1:<port>` only.

## Acceptance criteria

- [ ] The port is bound to `127.0.0.1` only
- [ ] The password is in neither the argv, the logs nor `config.json`
- [ ] An existing container and its volume are reused, never recreated
- [ ] The image is pinned by tag and the choice recorded in §8.3
