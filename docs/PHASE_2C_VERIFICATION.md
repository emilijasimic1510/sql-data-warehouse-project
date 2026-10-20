# Faza 2C — završna verifikacija

Datum: 11.10.2026. Cilj potvrđen pre mutacija: `DESKTOP-N1402MQ\SQLEXPRESS`, baza `DataWarehouse`.
Faza 2C je završena; nema prelaska na sledeću fazu, commita, pusha ili promene Git indeksa.

## Implementacija

- Jedinstven registar 28 SQL provera sa stabilnim ID-jevima, objektom/slojem, opisom, SQL-om,
  severity i pravilom prolaza. SSMS skripte se generišu iz njega; test sprečava razilaženje.
- Posle Silver-a slede SQL provere i stvarni brojevi redova svih 15 poslovnih objekata.
  ERROR nalaz ili greška izvršavanja daje FAIL / exit 1. WARNING sam ne obara izvršavanje.
- `--quality-only` ne validira CSV i ne poziva load procedure. Čita poslovne podatke i upisuje audit.
  Režimi `--dry-run`, `--quality-only`, `--execute` su međusobno isključivi.
- Eksplicitni audit DDL pravi tri tabele: `audit.pipeline_runs`, `audit.pipeline_steps`,
  `audit.quality_results`. Normalni pipeline radi samo DML; ne kreira objekte.
- `--report-path` čuva UTC vremena, UUID, statuse, trajanja, CSV sažetke, pravila, brojeve anomalija,
  dostupne brojeve redova i odvojene osnovne/audit greške. Bez ličnih podataka i sirovih SQL grešaka.
  Postojeći izveštaj ostaje netaknut bez `--overwrite-report`.

## Automatizovani testovi — odvojeno od stvarne baze

Kompletan suite pokrenut jednom po završetku implementacije:

```text
.\.venv\Scripts\python.exe -m pytest -q
51 passed in 4.33s
```

Zadržano 30 prethodnih testova; njihove SQL usluge izolovane od novih audit/quality poziva.
Dodat je 21 slučaj sa mock konekcijom i privremenim fajlovima: ERROR/WARNING, rana i kasna SQL greška,
quality-only bez učitavanja/CSV, dry-run bez konekcije/audita, Bronze/Silver greška uz audit grešku,
audit-only greška, nedostajući audit, neuspešna konekcija, privatnost CSV sažetka, zaštita izveštaja,
greška broja redova, odbijene kombinacije argumenata i podudarnost generisanih SQL skripti.
Nijedan test nije namerno kvario stvarne poslovne podatke.

## Stvarno izvršavanje

Prvi read-only preflight unutar sandbox-a nije mogao da koristi Windows bezbednosni kontekst (08001).
Isti identitet potvrđen je van sandbox-a, uz per-connection certificate trust. Nisu menjani servisi,
sertifikati, autentifikacija ni globalne postavke. Kreirana su samo tri nova audit objekta.

| Režim | Run ID | Status / exit |
| --- | --- | --- |
| dry-run | 621279f1-4142-4c51-833a-a5a3bc57ab1e | PASS / 0 |
| quality-only | 6f610872-ca1d-4e51-884e-bb40850f5ef8 | PASS / 0 |
| execute — tačno jedno potpuno učitavanje | dc018b72-5378-4fa9-bf7a-d768f29a3d47 | PASS / 0 |

Oba SQL izvršavanja: 26 PASS provera, S12 WARNING (15 redova sa datumom pre 1924), S14 INFO
(7 različitih vrednosti zemlje), nula ERROR nalaza ili grešaka provera. Budući datumi provereni zasebno:
S12F ima nula anomalija. Svi Gold kriterijumi imaju nula anomalija.
CSV upozorenje o završnom newline-u ostaje za PX_CAT_G1V2.csv; Python i baza imaju svih 37 redova.

Read-only verifikacija je uporedila SQL audit sa JSON-om: po jedan run zapis, svih 8 koraka i svih
28 rezultata provera po stvarnom izvršavanju; statusi, vremena, trajanja, severity i brojevi se podudaraju.
Dry-run nema audit zapis. Nije pokrenuto drugo potpuno učitavanje.

| Objekat | Bronze | Silver |
| --- | ---: | ---: |
| crm_cust_info | 18494 | 18484 |
| crm_product_info | 397 | 397 |
| crm_sales_info | 60398 | 60398 |
| erp_customer_info | 18484 | 18484 |
| erp_location_info | 18484 | 18484 |
| erp_product_category | 37 | 37 |

Gold: dim_customers **18484**, dim_products **295**, fact_sales **60398**.
Svih 15 stvarno izmerenih brojeva jednako je prethodnoj fazi; ovo nije nova potpuna provera sadržaja
svakog poslovnog reda. SHA-256 pre/posle deployment-a potvrđuje nepromenjene CSV i poslovne SQL fajlove,
kao i nepromenjeno stanje Git indeksa. Nisu menjane poslovne transformacije.

Trajni sažetak: [PHASE_2C_RESULTS.json](PHASE_2C_RESULTS.json).
Detaljni lokalni izveštaji: `reports/phase2c-dry-run.json`, `reports/phase2c-quality-only.json`,
`reports/phase2c-execute.json`. Ti generisani fajlovi ostaju ignorisani u Git-u.

## Komande i SSMS

Tačne PowerShell komande za sva tri režima i SQL za poslednji audit zapis nalaze se u
[PIPELINE.md](PIPELINE.md). Komande biraju nova UUID imena izveštaja. Svako novo korišćenje --execute
ponovo učitava Bronze/Silver; u ovoj fazi je već iskorišćeno jedno odobreno učitavanje.

Uspešan primer je stvarni execute: validacija i učitavanje uspeju, 15 starih datuma dobije WARNING,
sve ERROR provere prođu, audit i JSON se zatvore sa PASS, exit 0. Datumi ostaju nepromenjeni.
Neuspešan primer iz mock testa: Bronze vrati SQLSTATE 22018, Silver/provere ostaju SKIPPED,
JSON beleži FAIL i izlaz je 1. Ako i audit upis padne, prvobitna Bronze greška ostaje sačuvana uz zasebnu
audit grešku. Drugi test potvrđuje da dve ERROR anomalije obaraju status i posle uspešnog učitavanja.

## Ograničenja

Autocommit ostaje uključen; nema rollback-a celog učitavanja. Quality FAIL ne vraća stare podatke i ne
sprečava direktno čitanje Gold-a. Nema snapshot izolacije kroz sve provere, niti podrške za paralelne load-ove.
Brojevi redova su metrike, ne fiksni pragovi: prazna baza može proći mnoge postojeće kriterijume.
Domain poređenja koriste SQL collation; nisu byte-exact. NULL/whitespace/date pokrivenost ostaje ograničena.

CSV validacija je preflight bez SQL konekcije: ako padne, postoji lokalni JSON, ali ne SQL audit zapis.
Nedostupna konekcija ili nepotvrđen cilj takođe ne dozvoljavaju audit upis. Gubitak veze tokom finalizacije
može ostaviti RUNNING zapis i delimične audit detalje; lokalni izveštaj tada prijavljuje FAIL.
Naglo gašenje procesa ili disk greška mogu sprečiti završni JSON; nema automatskog retry-a ni oporavka.
Nema nove infrastrukture, SCD-a ili inkrementalnog učitavanja.
