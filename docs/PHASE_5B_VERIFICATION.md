# Faza 5B — stvarna Airflow verifikacija

Datum: 20.10.2026. Status: PASS za build, metadata init, stvarni DAG import, servise/UI i jedno
ručno DAG dry-run izvršavanje. Linux SQL preflight i stvarni SQL load NISU izvršeni.
SQL Server nije kontaktiran niti su menjani SQL autentifikacija, TCP, firewall, servisi ili kredencijali.

## Okruženje i izolacija

Docker Desktop u početku ipak nije radio. Pokrenuta je već instalirana aplikacija, bez promene
podešavanja. Linux engine 29.4.0, Compose 5.1.1, WSL2; engine vidi 4 CPU i 16681340928 bajtova RAM-a
(15.54 GiB). Host je imao približno 21.83 GiB slobodne memorije i 102.41 GiB slobodnog C: diska.
Port 18080 bio je slobodan; konačno vezivanje je samo 127.0.0.1:18080.

Compose project: dw-airflow-phase5. Četiri runtime servisa: postgres, airflow-api-server,
airflow-scheduler, airflow-dag-processor. Nema Redis/Celery workera, SQL Server kontejnera ili
host porta PostgreSQL-a. Samo projektni metadata i airflow-logs volumeni su kreirani.
Docker Desktop je po svom postojećem restart ponašanju pokrenuo i neke ranije kontejnerske servise;
nijedan od tih projekata nije ručno startovan/stopiran/menjan ovim postupkom.
Museum kontejneri su ostali zaustavljeni, sa istim identitetima i StartedAt vrednostima.
Nema brisanja volumena, system prune-a ili rada sa tuđim portovima/podacima.

## Konkretne popravke koje je stvarno izvršavanje otkrilo

- Osnovni image već ima Microsoft APT izvor i msodbcsql18 18.7.1.1-1. Prvi build je pao zbog
  duplog izvora sa konfliktom Signed-By. Uklonjeno je ponovno dodavanje repozitorijuma; Dockerfile
  sada proverava postojeću tačnu driver verziju i libgssapi paket.
- Airflow 3.3 DagBag nema include_examples parametar. validate_dag.py koristi podržani
  airflow.dag_processing.dagbag import i konstruktor; DAG uzima direktno iz bag.dags, bez nepotrebnog
  metadata upita za get_dag. Nema promene poslovnog DAG-a/E2E logike.
- Dodate su Docker health provere API-a i oba job procesa. Prvobitnih 15 sekundi bilo je premalo
  za stvarni jobs check CLI, iako su heartbeat-ovi bili zdravi. Scheduler/processor probe sada imaju
  timeout 45 s i start period 90 s. Posle primene svi servisi su healthy, up --wait je exit=0.
  Početni up --wait nije smatran uspešnim; njegov zapis je sačuvan odvojeno.
- Projektni runtime folder prethodno je dozvoljavao pristup samo CodexSandboxOffline nalogu.
  Dodat je puni pristup samo lokalnom vlasniku korisniku DESKTOP-N1402MQ\DELL; postojeće tajne nisu
  regenerisane ni ispisane. Docker Desktop i korisnik sada mogu pročitati potrebne runtime fajlove.

## Proverene i fiksirane verzije

| Komponenta | Stvarno potvrđeno |
|---|---|
| Airflow | 3.3.2 |
| Python | 3.12.14 |
| standard provider | 1.19.0 |
| psycopg2-binary | 2.9.13 |
| pandas / pyodbc | 3.0.6 / 5.3.0 |
| Microsoft ODBC | ODBC Driver 18 for SQL Server, paket 18.7.1.1-1 |
| PostgreSQL | image 16.10-bookworm |

Airflow base image digest:
`sha256:9df9c8be4096b9cc626bd7cb1f2b8c712eef66c59c615f8c7e6200871ca10bd1`.
PostgreSQL digest:
`sha256:38471f330eb885e04de130b768d6db4e10469e2311879c7e5c699f6d2d8a1c74`.
Oba su fiksirana u projektnim fajlovima. Stvarni Linux build i pip check su PASS
(No broken requirements found), uključujući projektni pandas pin posle Airflow constraints instalacije.
Windows .venv nije menjana niti je u nju instaliran Airflow.

Zvanični izvori korišćeni za konkretne korekcije:
[Airflow Compose](https://airflow.apache.org/docs/apache-airflow/3.3.2/howto/docker-compose/index.html),
[DagBag 3.3.2 source](https://github.com/apache/airflow/blob/3.3.2/airflow-core/src/airflow/dag_processing/dagbag.py),
[SimpleAuthManager](https://airflow.apache.org/docs/apache-airflow/3.3.2/core-concepts/auth-manager/simple/index.html).

## Stvarni dokazi

| Provera | Rezultat |
|---|---|
| Projektni image build + pip check | PASS |
| Airflow metadata init | exit=0; samo projektni PostgreSQL |
| Stvarni airflow-validate servis | exit=0, 0 import grešaka, 1 DAG/task |
| runtime importErrors API | 0 grešaka |
| schedule / catchup / concurrency | None / false / max_active_runs=1, max_active_tasks=1 |
| retries / timeout | 0 / 1800 sekundi |
| UI HTML / lokalna autentifikacija | HTTP 200 / PASS |
| Docker health | sva 4 servisa healthy |
| API heartbeat | metadatabase, scheduler i DAG processor healthy; triggerer namerno nije podignut |
| Stvarni DAG dry-run | SUCCESS, jedan manual run, jedan pokušaj |
| Autentifikovan task log API | PASS; 8944 bajtova preuzetog log odgovora |
| Windows host JSON | PASS; 5827 bajtova |
| XCom value | samo mode/run_id/status/report_path, 198 bajtova |
| Ciljani adapter testovi | 19 passed in 3.75s |

Prethodni kompletan suite 160 passed / 13 SQL skipped nije ponavljan: izmenjeni su samo Dockerfile,
Compose health/digest konfiguracija, pomoćni Airflow validator i dokumentacija. Poslovni Python/SQL
kod i podaci nisu menjani u fazi 5B.

## Jedini stvarni DAG run

- DAG: warehouse_e2e; task: run_warehouse_to_mart.
- Airflow run_id: phase5b_dry_run_20261020; run_type=manual; state=success.
- Početak: 2026-10-20T11:05:09.776227Z; kraj: 2026-10-20T11:05:34.347575Z.
- Task: success, try_number=1, max_tries=0. Nije bilo drugog run-a, retry-a ili task clear-a.
- Parent E2E run_id: 17d4aec2-ed83-42ba-8746-8e4b9934f37f.
- Warehouse child: b99d3386-4556-4294-bc57-12ef2df47929; child parent_id provereni prema parent-u.
- Šest stvarnih read-only montiranih CSV-ova, ukupno 116294 zapisa, svi strukturno PASS.
- Postojeće upozorenje o nedostajućem završnom newline-u ostaje; CSV nije popravljan/menjan.
- mode=dry-run, parent/child PASS; connection, target_check, coordination, audit_start,
  Bronze, Silver, SQL quality i row_counts su SKIPPED. Audit NOT_APPLICABLE, lock NOT_ACQUIRED,
  mart committed=false. Nema SQL konekcije ni promene DataWarehouse.
- DAG je posle uspeha vraćen na paused. Runtime execute=false, timetable Never/external triggers only,
  next_dagrun=null. Nema automatskog rasporeda ili retry-a.

Host JSON:
`reports/airflow/6dbddee2f19611cfbd41-try1-44f09fc86d034fadb0c96e7c72e4bb3d.json`.
SHA-256: `8035b6e597aee606504f90920022ed147ac41daaf665d050262f0ea59cb27ebe`.
Kontejnerska putanja iz XCom-a: /opt/project/reports/airflow/isto-ime.json, mapirana na taj host folder.
Task log u airflow-logs volumenu:
`/opt/airflow/logs/dag_id=warehouse_e2e/run_id=phase5b_dry_run_20261020/task_id=run_warehouse_to_mart/attempt=1.log`.
UI prikazuje isti log preko uspešno proverene autentifikovane log API putanje.

Lokalni ignorisani dokazi su reports/phase5b-*: build/init/import/start logovi, image-versions.json,
dag-run.json (sa XCom-om i host JSON proverom), final-health.json, containers-final.txt,
task-log-api.log i services-final.log. Nema novog SQL audit run-a za ovaj dry-run.

## Pristup i svakodnevne komande

UI: http://localhost:18080. Korisnik operator. Lozinku otvoriti lokalnim editorom iz zaštićenog
orchestration/airflow/runtime/ui-passwords.json; nije navedena u dokumentaciji, CLI argumentima ili logovima.
Ne ponavljati setup.ps1 niti prepisivati runtime tajne. Komande iz korena repozitorijuma:

```powershell
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml ps
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml logs --tail 100 airflow-scheduler airflow-api-server airflow-dag-processor
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml stop --timeout 60
docker --context desktop-linux compose -f orchestration/airflow/compose.yaml up -d --wait --wait-timeout 300 airflow-api-server airflow-scheduler airflow-dag-processor
```

Stop/up ne brišu metadata/log volumene ili host JSON. Ne zaustavljati aktivan budući SQL load;
whole-load rollback ne postoji. U ovoj fazi servisi su ostavljeni pokrenuti i healthy, DAG paused.

## Još nije provereno i nije izvršeno

Linux SQL preflight, SQL autentifikacija/mreža/privilegije i stvarni Airflow SQL E2E load ostaju
odvojena buduća faza. DataWarehouse SQL Server nema TCP i koristi Windows autentifikaciju.
Ne prenositi desktop NTLM prijavu u Linux pretpostavkom Trusted_Connection=yes.
Konkretan predlog mreže, namenskog naloga, modulskih privilegija i čuvanja tajne je u
[SQL_CONNECTION_PROPOSAL.md](SQL_CONNECTION_PROPOSAL.md); nijedan predlog nije primenjen.

Završne provere: hash-evi svih 25 originalnih CSV/SQL/CRM demo fajlova su isti kao na početku;
6 Museum kontejnera ima iste ID/status/StartedAt vrednosti. Tačne runtime tajne nisu pronađene
u projektnim izvornim fajlovima ili sačuvanim kompletnim service/task logovima.

Nijedna komanda za izmenu Git indeksa, commit ili push nije pokrenuta. Završna read-only provera
ipak je pronašla .git/index kreiran/izmenjen u 11:06:53–11:06:54 UTC tokom sesije, čiji uzrok ovim
postupkom nije utvrđen. Nije brisan, vraćan niti dalje menjan. Pošto na početku 5B nije sačuvan njegov
hash, ne tvrdimo byte-for-byte nepromenljivost indeksa; istorijski zapis faze 5 o odsutnom indeksu
ne opisuje ovo završno stanje. Izvorni završni SHA-256 indeksa je
A3F157399D2B5DD5778B005BB010D647B91C26F2CA2ACAD28AC7D9C6A0163BED.

Faza 5B se završava ovde, bez commita/pusha ili SQL security migracije.
