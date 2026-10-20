# Faza 5 — lokalni Apache Airflow

Airflow upravlja jednim postojećim E2E pozivom. Ne prepisuje transformacije: jedan DAG
`warehouse_e2e`, jedan PythonOperator `run_warehouse_to_mart`, direktan poziv
`e2e_pipeline.runner.run`. CSV → Bronze → Silver → warehouse gate → mart gate → parent JSON.
CRM incremental demo nije deo DAG-a. Originalni Gold ostaje baseline.

LocalExecutor izvršava task u scheduler kontejneru. Potrebni su PostgreSQL metadata,
API server/UI, scheduler i DAG processor; nema Celery workera, Redis-a ili triggerera.
`airflow-init` je jednokratna metadata migracija u zasebnom Postgres-u, ne DataWarehouse migracija.
Compose project je `dw-airflow-phase5`; imenovani volumeni su samo njegovi metadata/log volumeni.
Postgres nema host port; jedini objavljeni port je `127.0.0.1:18080` za UI.
SimpleAuthManager je isključivo lokalni demo, ne produkciona autentifikacija.

## Fiksirane verzije

| Komponenta | Verzija |
|---|---|
| Airflow image / Python | apache/airflow:3.3.2-python3.12 |
| standard provider | 1.19.0 |
| PostgreSQL image | postgres:16.10-bookworm |
| psycopg2-binary | 2.9.13 |
| Microsoft ODBC 18 (Debian 12) | 18.7.1.1-1 |
| Projektni pandas / pyodbc | 3.0.6 / 5.3.0 |

Izabrana je podržana PostgreSQL 16 grana sa eksplicitnim patch tagom. Tagovi nisu digest lock;
image build i pip check moraju proći pre upotrebe. Airflow i provider se prvo instaliraju uz
zvanični constraints-3.3.2/constraints-3.12.txt. Potom se instalira postojeći projektni requirements
uz ponovljeni Airflow pin. Time namerno zadržavamo pandas 3.0.6 umesto constraints 3.0.5;
`pip check` proverava deklarisanu kompatibilnost. Ta kombinacija još nije potvrđena build-om
na ovom računaru jer Docker engine nije pokrenut. Airflow nije instaliran u Windows .venv.

Izvori provereni 20.10.2026:
[Airflow preduslovi](https://airflow.apache.org/docs/apache-airflow/stable/installation/prerequisites.html),
[Docker Compose](https://airflow.apache.org/docs/apache-airflow/3.3.2/howto/docker-compose/index.html),
[LocalExecutor](https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/executor/local.html),
[zvanični constraints](https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-3.12.txt),
[Connections](https://airflow.apache.org/docs/apache-airflow/stable/howto/connection.html),
[SimpleAuthManager](https://airflow.apache.org/docs/apache-airflow/3.3.2/core-concepts/auth-manager/simple/index.html),
[Microsoft instalacija](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server?view=sql-server-ver17),
[Microsoft paketi](https://packages.microsoft.com/debian/12/prod/pool/main/m/msodbcsql18/),
[Linux integrated authentication](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/using-integrated-authentication?view=sql-server-ver17).

## Prvo pokretanje (PowerShell, iz korena repozitorijuma)

Trenutno postoji blokada opisana u PHASE_5_VERIFICATION.md. Sledeće komande namenjene su
pokretanju nakon što korisnik pokrene Docker Desktop sa Linux containers/WSL2 backend-om.
Obezbediti najmanje 4 GB, poželjno 8 GB Docker memorije. Ne pokretati Docker/system cleanup.
Pre izbora porta proveriti da 18080 nije zauzet; ne menjati Museum portove ili servise.

```powershell
# Samo prvi put; već izvršeno u ovoj fazi. Odbija prepisivanje postojećih tajni.
.\orchestration\airflow\setup.ps1

docker compose -f orchestration/airflow/compose.yaml config --quiet
docker compose -f orchestration/airflow/compose.yaml build
docker compose -f orchestration/airflow/compose.yaml --profile init run --rm airflow-init
docker compose -f orchestration/airflow/compose.yaml --profile validate run --rm airflow-validate
docker compose -f orchestration/airflow/compose.yaml up -d airflow-api-server airflow-scheduler airflow-dag-processor
docker compose -f orchestration/airflow/compose.yaml ps
```

Planirana adresa: http://localhost:18080, korisnik `operator`. Lozinka je u lokalnom
`orchestration/airflow/runtime/ui-passwords.json`; otvoriti zaštićeni fajl lokalnim editorom,
ne ispisivati ga u terminal/log. Setup pravi nasumične lozinke i uklanja nasleđene ACL-ove samo
novog runtime foldera, dajući trenutnom Windows korisniku pristup. Docker Desktop mora da ima
pristup tim bind mount fajlovima. Fajl za UI je read-write jer SimpleAuthManager koristi a+/r+
i file lock čak i za unapred definisane lozinke. Unapred generisane lozinke sprečavaju njihovo
prvo generisanje/ispisivanje u Airflow log. Ne menjati username bez pripreme tog fajla.
Runtime nije u Git-u ni Docker build kontekstu. Docker environment je dostupan lokalnom Docker
administratoru; ovo nije spoljni secrets manager. Ne deliti `docker inspect`, pun `compose config`,
runtime direktorijum ili nezaštićene backup-e sa tajnama.

## Runtime konfiguracija i razdvojene putanje

DAG parsiranje ne otvara konekciju i ne čita SQL konfiguraciju. Task poziva
`airflow.sdk.Connection.get('warehouse_sqlserver')` tek u izvršavanju. Setup stavlja JSON Connection
u `AIRFLOW_CONN_WAREHOUSE_SQLSERVER` unutar zaštićenog `runtime/worker.env`, dostupnog samo scheduleru
(koji izvršava LocalExecutor taskove). Env Connection nije prikazana u Airflow UI listi.
Ne unositi password u DAG, CLI argument, Extra, Git ili log. Password ide u Connection.password,
login u Connection.login. Opciono `auth_mode=sql` dodato je Settings modelu; postojeći CLI i Windows
podrazumevani režim nisu promenjeni. Settings repr skriva login i password; adapter ne prosleđuje
sirove driver izuzetke u task greške.

| Polje | Značenje |
|---|---|
| host / port | Dostupan TCP host/port, npr. host.docker.internal i eksplicitni odobreni port |
| schema | DataWarehouse, druge baze adapter odbija |
| extra.expected_server | DESKTOP-N1402MQ\SQLEXPRESS; potvrđuje @@SERVERNAME pre učitavanja |
| extra.auth_mode | windows (podrazumevano) ili sql (zahteva login/password) |
| extra.driver | ODBC Driver 18 for SQL Server |
| extra.trust_server_certificate | JSON boolean; false podrazumevano, preferirati pouzdan sertifikat |
| extra.sql_dataset_root | Windows folder koji SQL Server koristi za BULK INSERT |
| DW_DATASET_ROOT | /opt/project/datasets, Linux mount za CSV validator |
| DW_REPORT_ROOT | /opt/project/reports/airflow, trajan host mount |
| DW_AIRFLOW_EXECUTE | isključivo false ili true; podrazumevano false |

Windows sql_dataset_root setup izvodi iz lokacije repozitorijuma. Ne zamenjivati ga Linux putanjom.
SQL Server servis i dalje mora imati pravo čitanja originalnih CSV-ova na hostu. Dataset mount je
read-only, originalni CSV-ovi se ne kopiraju u image. Kod se kopira u image; posle izmene koda/DAG-a
potreban je novi build i recreate servisa.

Linux `Trusted_Connection=yes` zahteva pravilno podešen Kerberos/AD principal i ticket, ne nasleđuje
Windows desktop NTLM/shared-memory prijavu. Trenutni template je bez SQL kredencijala i omogućava
CSV dry-run; nije funkcionalna Linux SQL konekcija. Ne uključivati execute dok zasebno odobrena
mreža/autentifikacija nisu pripremljene. Ako se koristi lokalni self-signed SQL sertifikat,
trust_server_certificate=true predstavlja svesnu demo odluku, ne promenu podrazumevanog režima.

## Dry-run, preflight, ručno učitavanje

Prvi ručni DAG run sa `DW_AIRFLOW_EXECUTE=false` proverava CSV i piše JSON, bez SQL konekcije.
U UI unpause DAG i Trigger. Nema automatskog schedule-a. Alternativno:

```powershell
docker compose -f orchestration/airflow/compose.yaml exec airflow-scheduler airflow dags unpause warehouse_e2e
docker compose -f orchestration/airflow/compose.yaml exec airflow-scheduler airflow dags trigger warehouse_e2e
```

Airflow SUCCESS uz JSON mode=dry-run nije dokaz SQL učitavanja.
Posle odvojeno odobrene pripreme SQL TCP/auth i unosa Connection u zaštićeni worker.env,
prvo izvršiti read-only proveru iz istog worker okruženja:

```powershell
docker compose -f orchestration/airflow/compose.yaml run --rm --no-deps airflow-scheduler python -m airflow_orchestration.preflight
```

Preflight otvara vezu i proverava @@SERVERNAME, DB_NAME i postojeće procedure, bez load-a/migracija.
Ne ispisuje kredencijale. Tek posle PASS, dok DAG nema aktivan run, postaviti DW_AIRFLOW_EXECUTE=true
u runtime/worker.env pa primeniti konfiguraciju i ručno triggerovati jedan run:

```powershell
docker compose -f orchestration/airflow/compose.yaml up -d --no-deps --force-recreate airflow-scheduler
docker compose -f orchestration/airflow/compose.yaml exec airflow-scheduler airflow dags trigger warehouse_e2e
```

E2E sam ponavlja target check pre mutacija. Ne koristiti `airflow tasks test` za execute proveru:
to bi takođe učitalo podatke. Posle dozvoljenog jednog stvarnog run-a vratiti execute=false i recreate
scheduler-a tek kada nema aktivnog run-a. Ne clear/retry task pre pregleda posledica prethodnog pokušaja.

## Rezultati, greške i oporavak

Task logovi: UI → DAG run → run_warehouse_to_mart → Logs, ili servisni logovi:

```powershell
docker compose -f orchestration/airflow/compose.yaml logs --tail 100 airflow-scheduler airflow-api-server airflow-dag-processor
# Zaustavlja samo ovaj Compose projekat; čuva metadata/log volumene i JSON.
docker compose -f orchestration/airflow/compose.yaml stop
```

Detaljni task logovi ostaju u projektnom airflow-logs volumenu. JSON je na hostu u reports/airflow;
XCom sadrži samo run_id/status/mode/report_path. Ime sadrži hash DAG/run/task identiteta, broj pokušaja i
UUID, pa više ručnih pokušaja ne prepisuje dokaze. Putanja u kontejneru mapira se na host reports/airflow.
Parent JSON sadrži postojeće warehouse/mart child rezultate, quality nalaze i završni sažetak.
SQL audit za execute je u audit.pipeline_runs, audit.pipeline_steps, audit.quality_results;
pronaći parent run_id iz XCom/JSON, zatim child parent_run_id. Nema nove audit migracije.

DAG je početno paused, schedule=None, catchup=False, max_active_runs=1, max_active_tasks=1,
retries=0, execution_timeout=30 minuta. Jedan task pozajmljuje postojeću jednu session konekciju i
Exclusive `datawarehouse.pipeline.v1` lock kroz ceo tok (timeout 10 sekundi). Konkurentni projektni
Python writer-i koriste isti protokol; ručni SQL mimo protokola nije zaštićen. Airflow max_active_runs
sam ne štiti od samostalnih Python učitavanja, zato SQL lock ostaje neophodan.

Full-load je statement autocommit i nema rollback celog toka. Mart zadržava svoju atomsku transakciju.
Warehouse ERROR/FAIL sprečava mart, WARNING dozvoljava nastavak. Mart FAIL daje parent FAIL i task FAILED,
uz prethodni mart ako je transakcija vraćena. JSON audit failure takođe ostaje FAIL. Ne uvodimo retry.

Pri timeout-u/prekidu običan Python izlazak pokušava postojeći finally cleanup; disconnect oslobađa
session lock, a otvorena mart transakcija se vraća pri prekidu SQL sesije. SIGKILL, nestanak Docker-a ili
mrežni prekid mogu ostaviti nepotpun JSON/audit i SQL zahtev još u radu dok server ne primeti prekid.
Ne tvrditi da su full-load izmene vraćene ili da RUNNING audit znači da task još radi.
Pregledati Airflow stanje, parent/child JSON, SQL audit i aktivne SQL sesije/lock pre ručnog ponavljanja.
Ne force-recreate scheduler tokom aktivnog učitavanja. Oporavak je svesno novo potpuno učitavanje nakon
utvrđenog uzroka, uz originalne E2E reconciliation/quality provere iz faze 4B.
Unknown proizvodi ostaju u ukupnom prihodu, bez pouzdanih istorijskih atributa/troška.

Provere iz ove sesije, uključujući stvarne blokade i šta nije izvršeno, nalaze se u
[PHASE_5_VERIFICATION.md](PHASE_5_VERIFICATION.md).
