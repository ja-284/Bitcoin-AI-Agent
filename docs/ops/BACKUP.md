# Database backups: protecting the prospective record (since 2026-10-20)

> **STATUS (2026-10-21): PAUSED BY THE USER. NO VERIFIED, RECOVERABLE BACKUP OF THE DATABASE EXISTS.**
>
> **What happened:**
> - The tool below was built and tested on synthetic data on 2026-10-20 (`1820d8a`).
> - The user's attempt to create the owner's GPG key on Windows failed with a `keyboxd` configuration error.
> - The user then stopped the backup setup. This is an explicit change in scope, not a request to find another method.
>
> **Where things stand:**
> - The tool has **never been run on real data**. Nothing schedules, imports or runs it.
> - Its GPG round-trip integration tests are switched off by default (`BITCOIN_AGENT_BACKUP_TESTS=1` to opt in), so the
>   weekly integration suite runs no GPG command.
> - Everything below is a design, kept for a possible later decision. It is **not** an active safety measure.
>
> **The unresolved risk:** the Supabase database still holds the **only copy** of the prospective record, and Supabase's
> Free plan keeps no backups. Losing that project would lose the live record, the move-size shadow record, the blind
> direction track and the news scores permanently. None of it can be re-collected. Recorded in `docs/ops/STATUS.md`.

## Why this exists

The Supabase database holds the only copy of the prospective evidence, and none of it can be re-collected:
- the live BUY/HOLD/SELL record and its outcomes;
- the move-size shadow record and its checkpoint inputs;
- the blind direction track (E034);
- the news scores.

**Supabase's Free plan keeps no backups.** Daily backups start with the Pro plan. Supabase's documentation asks free
projects to "regularly export their data" and keep copies off-site (docs: *Database Backups*, *Backup and Restore
using the CLI*; read 2026-10-20). Until 2026-10-20 no copy existed anywhere (`research/EVIDENCE_ASSESSMENT_2026-10-20.md`,
P5).

## The design (the user's decisions, 2026-10-20)

| question | decision |
|---|---|
| how the backup is encrypted | to the owner's **GPG public key**. Making a backup needs no secret, and only the owner's private key and passphrase open one |
| where copies are kept | **this PC** (a folder outside the repository) **and OneDrive** (off this machine). Encrypted files only |
| which connection reads the data | the **existing maintenance connection** (the local `.env` owner role, as for migrations and weekly reports), inside a read-only transaction. No new role or credential |

**What a backup is** (`agent/database/backup.py`):
- **One read-only `REPEATABLE READ` transaction**, so all tables come from the same instant (pg_dump's method). It
  covers every base table in `public`, 13 on 2026-10-20: the record, both shadow tracks, the caches, the incidents and
  the dispatch log.
- **Data:** each table is taken with `COPY`, as pg_dump does for data, with its column list.
- **Also recorded:** every sequence's position, and a catalog of the live constraints, indexes, triggers, RLS flags,
  policies, grants and functions.
- **Structure:** a restore rebuilds it with `python -m agent.migrate` from the commit the manifest names. The weekly
  drift check proves the live database matches what those files build.
- **Encryption:** the archive (gzip'd tar) is built in memory and piped straight into `gpg --encrypt`. No unencrypted
  byte of the record is ever written to disk.
- **Beside it, a plaintext manifest:** snapshot time, server and schema version, repository commit, each table's row
  count and SHA-256, and the encrypted file's size and SHA-256. Never a value.
  - A table's hash is taken over its rows in sorted order, so a restored copy hashes the same.
  - The blind direction table appears only as a row count and a hash, an operational figure under Amendment 1.1.

**Never** (each enforced or tested):
- in git: the tool refuses any folder inside the repository, `.gitignore` lists the file patterns, and a unit test
  checks both;
- as a GitHub artifact, or anywhere public. Nothing in a workflow runs or imports the backup (tested);
- unencrypted on disk. `verify` decrypts in memory only and prints counts and hashes.

**Not covered.** These live in Supabase's own schemas and are re-created by hand on restore:
- the two pg_cron jobs (SQL in `docs/ops/supabase_dispatch.sql` and `docs/ops/dispatch_responses_cron.sql`);
- the Vault token (a new one is stored, `docs/ops/external_trigger.md`);
- auth users (2 on 2026-10-20) and storage;
- role passwords (`bitcoin_agent` is re-created with `python -m agent.database.setup_role`).

## One-time setup: the backup key (the user)

Run these in PowerShell. GnuPG comes with Git for Windows. The passphrase is typed into GnuPG's own pop-up window and
never appears in a terminal, a file, a chat or a log.

```powershell
$gpg = "$env:LOCALAPPDATA\Programs\Git\usr\bin\gpg.exe"
& $gpg --quick-generate-key "Bitcoin AI Agent backup" default default never
& $gpg --fingerprint "Bitcoin AI Agent backup"
```

1. The first command creates the key pair. Choose a strong passphrase in the pop-up, and store it in your password
   manager.
2. The second command shows the **fingerprint**: 40 hexadecimal characters. It is not secret.
3. Export a copy of the private key. It stays protected by the passphrase. Keep it **somewhere other than OneDrive and
   this PC**, for example a USB stick kept safe or an attachment in your password manager. Then delete the exported
   file:

   ```powershell
   & $gpg --armor --export-secret-keys "Bitcoin AI Agent backup" > "$env:USERPROFILE\Desktop\bitcoin-agent-backup-key.asc"
   ```

**If the private key or its passphrase is lost, every backup is unreadable.** That is the price of nobody else being
able to read them.

## Making a backup

```powershell
.venv\Scripts\python.exe -m agent.database.backup create --recipient <FINGERPRINT> --out C:\Users\aarsn\BitcoinAgentBackups --copy-to C:\Users\aarsn\OneDrive\BitcoinAgentBackups
```

- It writes `bitcoin-agent-db_<UTC time>.tar.gz.gpg` and its `.manifest.json` to both folders, and checks that the two
  copies are byte-identical.
- It reads only. It cannot change the database: read-only transaction, then rollback.
- It takes about a minute.

## Checking and verifying

- `python -m agent.database.backup check FILE` needs **no secret**. It checks that the encrypted file matches its
  manifest and is addressed to the manifest's key. Use it on both copies after every backup.
- `python -m agent.database.backup verify FILE` asks for **the passphrase** in GnuPG's pop-up. It then:
  - decrypts in memory;
  - recomputes every table's row count and hash, the catalog and the archive against the manifest;
  - prints only counts and hashes.

## Restoring: disaster recovery only

The restore never writes to the production database:
- it refuses a target URL equal to `DATABASE_URL`;
- it refuses any target table that already holds rows;
- after loading, it re-hashes every table against the manifest, and commits only if all match. Otherwise it rolls back.

Steps:
1. Create a new, empty Supabase project (free). Do not delete or reset the old one while there is any chance it is
   readable.
2. Put the new project's owner connection string in an environment variable, for example `RESTORE_DATABASE_URL`, in
   your own terminal. Never paste it into a chat.
3. Build the structure at the manifest's commit (`git checkout <commit>`). Run `python -m agent.migrate` with
   `DATABASE_URL` pointing at the **new** project, in that one terminal only.
4. Load the data: `python -m agent.database.backup restore FILE --target-url-env RESTORE_DATABASE_URL`. It verifies
   the backup first and asks for the passphrase.
5. Re-create the job role (`python -m agent.database.setup_role`), the two pg_cron jobs and the Vault token
   (`docs/ops/external_trigger.md`). Then point the GitHub secrets `DATABASE_URL` at the new project.
6. Run the checks:
   - `python -m agent.database.security`;
   - `python -m agent.database.role_check`;
   - the integration drift check;
   - `python -m agent.research.checkpoint_precheck`, which must still reproduce every stored probability.
7. Write down what happened. The hours between the last backup and the restore are **missing for good**: nothing is
   ever backfilled.

**Proven so far.** The whole path has been run on synthetic rows in disposable scratch schemas
(`tests/integration/test_backup_restore.py`):
- a backup is encrypted, checked and verified;
- restored into a schema `agent.migrate` built, every table hashes exactly as before, and the sequences continue;
- a restore into a schema holding rows is refused;
- a damaged backup rolls back and leaves the target empty.

**Not yet done:** restoring the real backup into a second project. That needs a new Supabase project, which is the
user's decision (the restore drill below).

## Frequency, retention, recovery test and alert (proposed 2026-10-20)

- **Frequency:**
  - at **every weekly audit**, as part of its checklist;
  - **before** any migration, any registered checkpoint reading and any holdout decision.
  - A daily automatic backup would need a standing Windows scheduled task on this PC. That is the user's decision, not
    set up.
- **Retention:**
  - keep every weekly backup for 3 months, then one a month indefinitely;
  - **never delete** the backups taken right before a registered reading.
  - Each file is a few MB. Deleting old copies is always the user's action.
- **Recovery test:**
  - `check` on both copies after every backup;
  - `verify` (the passphrase) at least monthly;
  - a full restore drill into a free second Supabase project before the 2,000-hour reading (≈ 2026-12-14), if the user
    agrees to create one.
- **Failure alert:** no new alert service. The weekly audit records the newest backup's age and its `check` result.
  An age over 8 days is a finding.

## Limitations, stated plainly

- **Recovery point:** everything since the last backup. Weekly backups mean up to 7 days lost in the worst case,
  permanently, because missing hours are never backfilled.
- **Recovery time:** about 1–2 hours of manual work (the steps above), plus GitHub's next hourly slot.
- **Manual:** a backup happens only when someone runs it. The hourly system keeps collecting either way.
- **Key:** one private key and passphrase. Lose both copies of either and the backups are unreadable.
- **OneDrive:** the off-site copy depends on OneDrive syncing. Check that the folder shows "synced".
- **Reading access:** the backup reads with the owner role (the user's choice), which can read everything, though
  only inside a read-only transaction.
- **Not covered:** Supabase-owned objects (above).
