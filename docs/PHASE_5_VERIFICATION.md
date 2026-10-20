# Faza 5 — zapis verifikacije

Datum: 20.10.2026. Implementacija i sve nezavisne lokalne provere završene.
Stvarni Airflow image build, DagBag import i Airflow SQL učitavanje nisu izvršeni zbog
konkretnih preduslova ispod. Dry-run nije predstavljen kao stvarno učitavanje.

## Okruženje: read-only nalazi

- Docker CLI 29.4.0; Compose v5.1.1; context desktop-linux.
- Docker Desktop Linux engine nije pokrenut: nedostaje dockerDesktopLinuxEngine named pipe.
- WSL podrazumevana verzija 2; docker-desktop distribucija Stopped.
- Nisu pronađeni Docker Desktop/com.docker.backend procesi.
- RAM ukupno 31.83 GB, raspoloživo 22.36 GB; C: slobodno 102.42 GB.
- Host port 18080 nema pronađen LISTEN zapis u read-only proveri; ponovo proveriti pri startu.
- Kontejneri se nisu mogli izlistati bez daemon-a. Museum inventar zato nije potvrđen;
  nijedan kontejner/volumen/port drugog projekta nije menjan niti je pokretan sistemski cleanup.
- Docker Desktop, WSL i sistemski servisi nisu pokretani. Korisnička dozvola za start Compose-a
  uslovljena je već pokrenutim Docker-om.

Stvarna read-only SQL provera sa Windows hosta potvrđuje
`DESKTOP-N1402MQ\SQLEXPRESS`, bazu `DataWarehouse`, IntegratedSecurityOnly=true,
Shared memory/NTLM transport, šifrovanu vezu, bez TCP listener-a i Tcp Enabled=0 u konfiguraciji.
Dokaz: lokalni ignorisani reports/phase5-sql-preflight.json. Nema promena SQL konfiguracije ili podataka.

Linux worker nema prenosivu desktop Windows prijavu, niti dostupnu TCP putanju. Zato ne postoji
bezbedna funkcionalna Linux SQL konekcija u trenutnom stanju i dozvoljeni stvarni Airflow load nije
pokušan. Nije pokrenut host full-load kao zamena za taj dokaz.

Minimalan sledeći korak: korisnik pokreće Docker Desktop. Za stvarni SQL pristup potrebno je zasebno
odobriti i pripremiti TCP pristup ovoj instanci (port i firewall samo ako je potreban), pa izabrati
podržanu autentifikaciju: pravilno AD/Kerberos okruženje ili mixed mode i namenski SQL login sa samo
potrebnim projektnim pravima. Obe putanje zahtevaju prethodno odobrenje server izmena; nisu izvedene.
Settings opciona SQL autentifikacija sama ne uključuje mixed mode niti kreira login.

## Izvršene provere

| Provera | Rezultat |
|---|---|
| Postojeći + novi pytest suite | 160 passed, 13 skipped, 5.36 s |
| Novi slučajevi faze 5 | 19 passed (uključeni u 160) |
| SQL integration suite | 13 opt-in slučajeva preskočeno; nisu ponavljana učitavanja |
| Compose config --quiet | PASS, bez daemon-a |
| Parsirana Compose konfiguracija | PASS: project, 4 runtime servisa, localhost UI, nema Postgres host porta, read-only datasets, SQL Connection samo worker-u |
| Adapter + stvarni postojeći E2E runner, originalni CSV, dry-run | PASS, bez SQL učitavanja |
| Statička zabrana parse-time Connection.get u DAG-u | PASS, nije stvarni Airflow import |
| Originalni CSV/SQL/CRM demo hash-evi | PASS: 25 fajlova neizmenjeno |
| Runtime/report Git ignore | PASS preko git check-ignore --no-index |
| Windows .venv | Airflow nije instaliran; korišćena za projektne testove i setup |

Unit testovi proveravaju uspeh/failure adaptera, eksplicitni execute režim, konfiguraciju i dve različite
putanje, unique report ime, mali XCom, sanitizaciju exception-a/loga, odbijanje neprojektne/nepotpune
konfiguracije, SQL credential escaping i repr, nepromenjen Windows režim, dry-run bez SQL i preflight
zatvaranje konekcije pri uspehu/grešci. Postojeći testovi i dalje pokrivaju shared session lock i E2E gates.

Dry-run parent run_id: `715d8d5d-4bf2-4d29-a32d-56358e063f8e`.
Lokalni sažetak sa apsolutnom putanjom: reports/phase5-adapter-dry-run.json;
parent/embedded child JSON: reports/airflow/e8a128fe9f45f75e338a-try1-426cda36ff334b5e972a2907ae858f3b.json.
Postojeći validator prijavljuje upozorenje o nedostajućem završnom newline-u; originalni podaci nisu menjani.
Dry-run nema nov SQL audit i ne osvežava mart. Brojke faze 4B nisu izmerene novim SQL učitavanjem.

Sandbox je pri Compose proveri prijavio nemogućnost čitanja korisničkog .docker/config.json;
Compose lokalna parsiranja ipak su završena exit=0. Eskalirani pokušaj nije mogao da pročita runtime
fajl sa ograničenim ACL-om; nije menjan ACL da bi se zaobišla zaštita. Taj pokušaj nije označen PASS.
Konfiguracija je zatim proverena u izvornom korisničkom kontekstu, bez ispisa tajni.
Git indeks je prethodno odsutan i nije kreiran/menjan; nema commita/pusha.

## Nije izvršeno — nije PASS

- Docker build / pip check unutar Linux image-a.
- Stvarni Airflow DagBag import i konfiguracioni check (`airflow-validate` servis je pripremljen).
- Compose start/health/UI login, stvarni DAG dry-run.
- Linux SQL preflight, stvarni Airflow E2E run i novo SQL reconciliation merenje.

Posle uklanjanja blokade pratiti docs/AIRFLOW.md: build → metadata init → stvarni DagBag validate →
start → ručni DAG dry-run → container-side read-only SQL preflight → tek onda jedan execute run.
Proveriti parent i child PASS, mart committed, audit_status PASS i reconciliation. Očekivani baseline
faze 4B: 60398 prodaja, količina 60423, prihod 29356250.00; unknown 18429 redova
(BEFORE_HISTORY 18410 / 8649691.00 i MISSING_ORDER_DATE 19 / 4992.00).
Unknown prihod ostaje uključen u ukupan prihod. Ove vrednosti su referenca za buduću proveru,
ne rezultat izvršavanja faze 5.

Operativne komande, lokacije log/JSON/audit rezultata i oporavak bez automatskog retry-a opisani su u
[AIRFLOW.md](AIRFLOW.md). Faza 5 se ovde završava; dodatne server promene nisu autorizovane.
