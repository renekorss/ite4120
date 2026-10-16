# ITE4120 — Driving Licence Reminder

Team: Rene Korss, Cibele Yuri Kojima De Paula, Dwitama Alfret Wuwung.

## Requirements

Docker with Compose v2.24.4+, Python 3.11+, POSIX shell and OpenSSL.
Start Docker and run the commands below from the repository root.

## Run

```sh
./scripts/init-local.sh
docker compose up -d --wait postgres
docker compose run --rm liquibase update
```

Local configuration is in `.env`, created from `.env.example`. The setup script
also generates the database password in `.secrets/`; both are ignored by Git.

To open a database console:

```sh
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

To stop the services while keeping database data:

```sh
docker compose down
```

See [operations and test commands](docs/database-operations.md),
[database design and ERD](docs/database.md), and [user stories](user-stories.md).
