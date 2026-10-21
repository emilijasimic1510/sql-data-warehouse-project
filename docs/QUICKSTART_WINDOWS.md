# Windows: svakodnevni rad bez ponovne instalacije

Faza 6A, 21.10.2026. Komande se izvršavaju u **PowerShell terminalu**, iz korena repozitorijuma.
Na ovom računaru baza i objekti već postoje. Za svakodnevni rad preskoči odeljak „Prva instalacija”.
Nijedna execute/deploy/SQL integration/Airflow start komanda nije pokrenuta radi pisanja ovog vodiča.
Provere stvarno izvršene sada navedene su u [izveštaju](PHASE_6A_VERIFICATION.md).

## 1. Otvori projekat i proveri okruženje

U VS Code-u: File → Open Folder →
`C:\Users\DELL\Desktop\data-warehouse\sql-data-warehouse-project`, zatim Terminal → New Terminal.
Ili iz PowerShell-a (VS Code `code.cmd` je pronađen):

```powershell
Set-Location 'C:\Users\DELL\Desktop\data-warehouse\sql-data-warehouse-project'
code .
Test-Path .\.venv\Scripts\python.exe
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -c "import pandas,pytest,pyodbc; print(pandas.__version__,pytest.__version__,pyodbc.version); print(pyodbc.drivers())"
```

Ako Test-Path vrati False, prvo pripremi `.venv` iz odeljka instalacije. Aktivacija nije potrebna.
Sada provereno: Python 3.14.3, pandas 3.0.6, pytest 9.1.1, pyodbc 5.3.0; pip check je PASS.
Windows CLI podrazumeva **ODBC Driver 17 for SQL Server**, prisutan je i Driver 18.
Airflow koristi zasebno Linux okruženje; ne instaliraj Airflow u ovu `.venv`.

## 2. Unit/mock testovi — bez baze

```powershell
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/integration
$LASTEXITCODE
```

Sada: **160 passed**, 0 neuspešnih. Eksplicitno izostavljanje integration direktorijuma radi čak
i ako u terminalu slučajno ostanu uključene DW_RUN_* promenljive. Ne koristi opšti `pytest` uz te
promenljive ako želiš samo testove bez SQL konekcije.

## 3. CSV validacija i E2E dry-run — bez SQL konekcije

```powershell
.\.venv\Scripts\python.exe -m csv_validation --dataset-root .\datasets --report-path ('.\reports\csv-' + [guid]::NewGuid() + '.validation.json')
$LASTEXITCODE
.\.venv\Scripts\python.exe -m e2e_pipeline --dataset-root .\datasets --dry-run --report-path ('.\reports\e2e-dry-' + [guid]::NewGuid() + '.json')
$LASTEXITCODE
```

Očekuj 6 PASS, 116294 zapisa ukupno i poznato newline upozorenje za `PX_CAT_G1V2.csv` (37 zapisa).
Exit 0 je uspeh; 1 runtime/validation neuspeh; 2 neispravne opcije. Dry-run ne proverava SQL pristup,
konverzije tipova, SQL quality ili pristup SQL servisa CSV fajlovima. JSON se čuva u ignorisanom reports/.

## 4. SQL read-only pregled u SSMS-u

Connect → Database Engine → Server name `DESKTOP-N1402MQ\SQLEXPRESS` → Windows Authentication.
Izaberi DataWarehouse. Ako lokalni razvojni sertifikat zahteva trust, koristi samo opciju ove
konekcije; ona preskače proveru identiteta sertifikata, nije opšte rešenje za udaljeni server.
Ne menjaj autentifikaciju, servise ili druge instance. Prvo New Query:

```sql
SELECT @@SERVERNAME AS server_name, DB_NAME() AS database_name;
```

Nastavi samo ako rezultat odgovara cilju. File → Open → File, otvori i izvrši:

1. `tests/quality_checks_silver.sql`, zatim `tests/quality_checks_gold.sql`: 28 registry provera.
   ERROR treba da bude 0; S12 stari datumi rođenja je upozorenje, S14 broj zemalja je INFO.
2. `powerbi/sql/03_reconciliation.sql`: postojeći **read-only** `EXEC mart.check_quality`, totals,
   join grain, date raspon i BI dijagnostika porudžbina. M01–M14 treba da su 0. U02/U07 su istih
   19 redova, U04 18410: ne sabiraj preklapajuća upozorenja. Poslednja BI dijagnostika trenutno
   daje 13 porudžbina sa poznatim i nepoznatim datumom; nije novi blokirajući pipeline test.
3. `powerbi/sql/01_kpis.sql`: agregati iz stvarnog mart-a, uključujući unknown redove.
4. `powerbi/sql/02_audit.sql`: poslednji E2E parent, njegova deca, svi njihovi koraci/check-ovi,
   poslednji uspeh i dostupni statusi. `RUNNING` nije dokaz da je proces još živ.

Ovi fajlovi ne upisuju trajne podatke. **`warehouse_pipeline --quality-only` nije strogo read-only:**
ne učitava poslovne tabele, ali upisuje audit; zato nije zamena za ovaj odeljak.
Ne izvršavaj `scripts/mart/quality.sql` kao proveru: to je definicija procedure/deployment.

## 5. Stvarni E2E execute — NAMERNO PONOVNO UČITAVANJE

Ovo nije potrebno za gledanje postojećih podataka u Power BI-ju. Prvo pregledaj prethodni audit,
potvrdi instancu, odsustvo paralelnog load-a, PASS CSV/dry-run i da želiš da zameniš postojeće podatke.

```powershell
$target = @('--server', 'DESKTOP-N1402MQ\SQLEXPRESS', '--expected-server', 'DESKTOP-N1402MQ\SQLEXPRESS', '--database', 'DataWarehouse', '--trust-server-certificate')
.\.venv\Scripts\python.exe -m e2e_pipeline @target --dataset-root .\datasets --execute --report-path ('.\reports\e2e-run-' + [guid]::NewGuid() + '.json')
$LASTEXITCODE
```

Komanda radi postojeći Bronze/Silver **TRUNCATE/full-load**, quality gate i mart refresh.
SQL Server je lokalni: resolved dataset-root koristi i BULK INSERT na SQL hostu. Na drugom hostu
potreban je poseban `--sql-dataset-root`; SQL servis mora imati pristup toj putanji.
Ne pokreći DDL ili init pre svakog load-a. Autocommit warehouse nema globalni rollback;
mart ima zasebnu transakciju. Pri grešci pročitaj failure_stage i [oporavak](E2E_PIPELINE.md),
ne ponavljaj automatski. Zatim ponovi SQL read-only provere i Power BI Refresh.

## 6. SQL integration testovi — odvojeno i samo namerno

U fazi 6A **nisu izvršeni**. Trenutni test fajlovi imaju fiksiran lokalni cilj
`DESKTOP-N1402MQ\SQLEXPRESS / DataWarehouse` i Windows autentifikaciju.

| Test | Efekat |
|---|---|
| test_project_lock_sql.py (2) | Dve konekcije, session lock/release; bez učitavanja tabela, kratko može blokirati podržani writer. |
| test_mart_sql.py (4) | Ponovo objavljuje mart, proverava redeployment i nameran rollback. Nije read-only. |
| test_crm_incremental_sql.py (7) | Menja izolovani CRM demo/ledgere, radi redeployment, koristi rezervisane test ID-eve i seed42 demo. Nije read-only. |

Pokreni samo izabrani blok nakon što prihvatiš njegove efekte; ne tokom E2E/BI refresh-a.
`finally` uklanja opt-in promenljivu i pri grešci. Ne uključuj sve tri pa pokreći ceo suite.

```powershell
try {
  $env:DW_RUN_PROJECT_LOCK_INTEGRATION='1'
  .\.venv\Scripts\python.exe -m pytest -q -s -p no:cacheprovider tests\integration\test_project_lock_sql.py
} finally { Remove-Item Env:DW_RUN_PROJECT_LOCK_INTEGRATION -ErrorAction SilentlyContinue }
```

Samo kada želiš mutirajuće mart testove:

```powershell
try {
  $env:DW_RUN_MART_INTEGRATION='1'
  .\.venv\Scripts\python.exe -m pytest -q -s -p no:cacheprovider tests\integration\test_mart_sql.py
} finally { Remove-Item Env:DW_RUN_MART_INTEGRATION -ErrorAction SilentlyContinue }
```

Samo kada želiš mutirajuće CRM demo testove (preduslovi i rezervisani ID-evi: [CRM vodič](CRM_INCREMENTAL.md)):

```powershell
try {
  $env:DW_RUN_SQL_INTEGRATION='1'
  .\.venv\Scripts\python.exe -m pytest -q -s -p no:cacheprovider tests\integration\test_crm_incremental_sql.py
} finally { Remove-Item Env:DW_RUN_SQL_INTEGRATION -ErrorAction SilentlyContinue }
```

## 7. Airflow: start → dry-run → logovi → stop

Za postojeći setup ne ponavljaj setup.ps1 ili metadata init. Ručno otvori Docker Desktop sa
postojećim Linux backend-om. Ne menjaj tuđe kontejnere. Proveri samo bezbedno, nesekretno polje:

```powershell
Select-String -Path .\orchestration\airflow\runtime\worker.env -Pattern '^DW_AIRFLOW_EXECUTE='
```

Mora biti tačno `DW_AIRFLOW_EXECUTE=false`; ako nije ili nema rezultata, **stani pre trigger-a**.
Ne ispisuj ceo env ili compose config: sadrže tajne. Zatim:

```powershell
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml config --quiet
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml up -d --wait --wait-timeout 300 airflow-api-server airflow-scheduler airflow-dag-processor
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml ps
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml exec airflow-scheduler python -c "import os; print('execute=' + os.environ.get('DW_AIRFLOW_EXECUTE','MISSING'))"
```

Proveri healthy servise i još jednom `execute=false` u stvarnom worker-u. Ako se runtime razlikuje,
stani; samo `up` ne garantuje primenu promenjenog env fajla postojećem kontejneru.
UI: http://localhost:18080, operator; lozinku pogledaj samo lokalnim editorom u zaštićenom
`orchestration/airflow/runtime/ui-passwords.json`. Ne kopiraj je u log, Git ili ovaj vodič.

```powershell
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml exec airflow-scheduler airflow dags unpause warehouse_e2e
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml exec airflow-scheduler airflow dags trigger warehouse_e2e
```

UI → DAG warehouse_e2e → izaberi novi run → run_warehouse_to_mart → Logs.
Sačekaj SUCCESS, proveri XCom/report_path i JSON u `reports/airflow`: **mode=dry-run**, SQL SKIPPED,
mart committed=false. To nije dokaz SQL load-a. Posle završetka:

```powershell
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml exec airflow-scheduler airflow dags pause warehouse_e2e
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml logs --tail 100 airflow-scheduler airflow-api-server airflow-dag-processor
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml stop --timeout 60
```

Stop čuva volumene i izveštaje. Ne zaustavljaj aktivni SQL load; nema rollback-a celog toka.
Airflow SQL execute nije potvrđen: Linux ne nasleđuje Windows NTLM prijavu; mreža/auth nisu menjani.
[AIRFLOW.md](AIRFLOW.md) i [izveštaj 5B](PHASE_5B_VERIFICATION.md) ostaju izvor runtime instrukcija.
Ove komande su sada pregledane prema lokalnoj konfiguraciji, ne ponovo izvršene.

## Prva instalacija — samo za novo okruženje

Za postojeći računar ovaj odeljak preskoči. Ako `.venv` ne postoji:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
```

Koristi instalirani kompatibilni Python (ovde proverena 3.14.3); ne prepisuj postojeću `.venv`
bez razloga. Ako mreža blokira pip, istu komandu pokreni lokalno sa dozvoljenim pristupom mreži.
Za sasvim novu bazu slediti [README početnu SQL instalaciju](../README.md#first-installation-in-ssms),
zatim audit, mart i E2E migraciju prema pripadajućim vodičima. Bronze/Silver DDL briše postojeće
tabele: nikada ga ne koristiti kao svakodnevno pokretanje. Poseban CRM demo nije preduslov za BI.
Prvi Docker setup/build/metadata init nalazi se u [AIRFLOW.md](AIRFLOW.md#prvo-pokretanje-powershell-iz-korena-repozitorijuma).
Nijedan deployment nije automatski deo ovog quickstart-a.
