# Faza 3A: deterministički simulator CRM kupaca

Ovaj dokument čuva ugovor i istorijski plan faze 3A. Faza 3B je naknadno implementirala
[izolovani loader u crm_incremental šemi](CRM_INCREMENTAL.md), bez izmene postojeće Silver tabele ili Gold-a.

Ovo je **SYNTHETIC CRM DEMO ONLY**: mali, potpuno sintetički skup događaja za buduće inkrementalno
učitavanje. Nije kopija stvarnih kupaca, produkcioni izvor, SQL loader ili dokaz integracije sa bazom.
Nema SQL konekcije, izmene šest originalnih CSV izvora niti promene postojećeg full-load toka.

## Pokretanje

Iz korena `sql-data-warehouse-project`, koristeći postojeću .venv:

```powershell
.\.venv\Scripts\python.exe -m crm_demo generate --output-dir .\demo_output\phase3a-seed42 --seed 42 --start-date 2026-01-01
.\.venv\Scripts\python.exe -m crm_demo verify --output-dir .\demo_output\phase3a-seed42
```

`generate` zahteva novi output folder. Ne prepisuje postojeće fajlove i odbija originalne datasets,
SQL, Python i druge zaštićene projektne direktorijume. Za ponovnu demonstraciju izaberi novo ime foldera;
isti seed i start-date daju identične bajtove, manifest i identifikatore i u drugom folderu.
Default seed je 42, scenario datum je fiksni 2026-01-01; datum računara se nikada ne koristi.
`--start-date` podešava početni dan priče, a ne vreme generisanja. Promena verzije generatora može
promeniti rezultat: determinističnost se odnosi na isti ugovor/verziju, seed i parametre.

Samo jedan paket:

```powershell
.\.venv\Scripts\python.exe -m crm_demo validate --package-dir .\demo_output\phase3a-seed42\01_changes
.\.venv\Scripts\python.exe -m crm_demo validate --package-dir .\demo_output\phase3a-seed42\06_negative
$LASTEXITCODE
```

Validan paket daje exit 0. Negativni paket mora dati **FAIL / exit 1**; etiketa negative ga ne izuzima
iz validatora. `verify` proverava ceo poznati demo skup, očekuje šest validnih paketa i baš definisanu
negativnu grešku, pa tada daje PASS / exit 0. Koristi se za proveru test fixture-a, ne za prihvatanje
proizvoljnih ulaznih podataka. CLI sintaksne greške daju 2, neuspeh generisanja/provere daje 1.

Paket koristi samo Python standardnu biblioteku: csv, hashlib, json, datetime, pathlib i argparse.
Nema novih zavisnosti niti importa pyodbc/Pandas. Postojeći `csv_validation` i `warehouse_pipeline`
ostaju odvojeni i ne pozivaju simulator.

## Organizacija i izlaz

- `crm_demo/config.py`: zaseban demo ugovor i ID prostor; originalni EXPECTED_FILES nije proširen.
- `generator.py`: eksplicitni scenariji i očekivanja, deterministička serijalizacija i zaštita output-a.
- `validation.py`: strukturne, ugovorne i manifest provere; read-only provera kompletnog fixture-a.
- `__main__.py`: generate / validate / verify komande.
- `tests/test_crm_demo.py`: determinističnost, integritet, ugovor, očuvanje izvora i nezavisna provera očekivanja.

Svaki od sedam podfoldera sadrži `customers.csv` i `manifest.json`. Zajednički `expectations.json`
definiše redosled isporuka, njihove datume, očekivane akcije po događaju i kompletno očekivano stanje.
`SYNTHETIC_DEMO.txt` označava namenu. `demo_output/` je ignorisan u projektnom Git-u; svaki generisani
output dobija i sopstveni `.gitignore` sa `*`, tako da se runtime fajlovi ignorišu i u prilagođenom folderu.
Generator ne poziva Git i ne menja indeks. Nepotpuno generisanje usled disk greške ne prolazi verify;
izaberi novi folder umesto automatskog nastavljanja/prepisivanja.

## Ugovor v1

CSV je UTF-8 bez BOM-a, sa zaglavljem u tačnom redosledu, zarezom, standardnim CSV quoting pravilima i
LF završecima redova uključujući poslednji. Svaki red ima devet kolona. Snapshot koristi isti envelope
kao delta, da bi i početna stanja imala event_id i source_updated_at.

| Kolona | Značenje i validacija |
| --- | --- |
| event_id | `evt-` + 64 lowercase hex znaka; identitet jednog nepromenljivog izvornog događaja |
| source_updated_at | Stvarno vreme verzije izvora, UTC `YYYY-MM-DDTHH:MM:SSZ`; validan kalendarski datum |
| cst_id | Poslovni ključ kupca, decimalni SQL INT iz rezervisanog demo opsega |
| cst_key | Alternativni CRM broj, ovde `DEMOCRM0001` itd.; mora odgovarati demo cst_id |
| cst_firstname | Sintetički `DemoFirst_...`, ASCII, najviše 50 znakova |
| cst_lastname | Sintetički `DemoFamily_...`, ASCII, najviše 50 znakova |
| cst_marital_status | Izvorna CRM vrednost S, M ili n/a |
| cst_gndr | Izvorna CRM vrednost F, M ili n/a |
| cst_create_date | Datum kreiranja kupca, YYYY-MM-DD; ne sme biti posle source_updated_at datuma |

Demo prostor: **1900000000–1900000999**, unutar SQL INT opsega. Koristi se pet kupaca
1900000001–1900000005; šesti je samo predložak negativnog zapisa bez cst_id. Imena su oznake i hash
sufiksi, bez čitanja ili kopiranja originalnih imena. Seed menja sufikse i event identitete, ali ne
numeraciju uloga kupaca. Različiti seed-ovi su alternativni demo svetovi: ne mešati ih u istu buduću
test bazu bez resetovanja izolovanog demo stanja. Rezervacija nije globalna garancija protiv budućih
kolizija; pre budućeg SQL rada koristiti odvojen demo cilj. Originalni ID-jevi trenutno su 11000–29483.

`cst_id` prati postojeću Silver deduplikaciju i Gold customer_id. `cst_key` je alternativni broj koji
služi i ERP join-ovima. Simulator ne uvodi ERP redove. Event_id je jedinstven za različite događaje;
ponovna isporuka ISTOG događaja namerno ponavlja isti ID i ceo payload. Novi no-change događaj ima
nov ID i nov source_updated_at, iako su sve poslovne kolone iste.

`cst_create_date` je datum nastanka kupca i ostaje nepromenjen kroz njegove izmene. Postojeći full-load
koristi `ROW_NUMBER() OVER (PARTITION BY cst_id ORDER BY cst_create_date DESC)` i isključuje NULL ID.
To nije pouzdano pravilo za poslednju izmenu, a ista create-date vrednost ne razrešava dve verzije.
Budući inkrementalni tok mora koristiti source_updated_at; postojeća procedura u fazi 3A nije menjana.

Izvorne S/M i F/M vrednosti u očekivanjima su sirovi CRM podaci, ne već transformisani Silver redovi.
Budući loader treba da primeni postojeća pravila: TRIM imena, S -> Single, M -> Married za marital status,
F -> Female, M -> Male za gender, ostalo -> n/a. Očekivanja ne uključuju dwh_create_date ili Gold ključ.

## Manifest i determinističnost

Svaki manifest ima contract_version, jasnu simulator oznaku, seed, start_date, batch_id,
package_type (snapshot/delta/negative), record_count, sha256 i data_file=customers.csv.
Broj redova isključuje zaglavlje i uključuje negativan zapis. SHA-256 je nad TAČNIM CSV bajtovima,
uključujući zaglavlje, quoting i newline; nije hash parsiranih redova ili samog manifesta.

Event_id je SHA-256 tekstualnog `crm-demo-v1|seed|start_date|event-tag`, sa evt- prefiksom.
Batch_id je `batch-` + SHA-256 od `crm-demo-v1|package_type|csv_sha256`.
JSON ima sortirane ključeve, indent 2 i završni LF. Putanja, locale, trenutno vreme, random UUID i
Python hash randomization ne učestvuju u sadržaju. Namerno ponovljeni paket 05 ima IDENTIČAN CSV,
manifest i batch_id kao 01; datum ponovne isporuke je samo u expectations.json, ne u manifestu.
Hash pokazuje integritet/determinističnost, ne autentičnost potpisanog izvora.

## Scenariji, seed 42 i podrazumevani datum

Oznaka C1 znači cst_id=1900000001, analogno do C5. Brojevi ubačenih/ažuriranih odnose se na
različite kupce nakon celog paketa; nepromenjeni uključuju i kupce koji nisu pomenuti u paketu.
Broj obrađenih update događaja može biti veći: paket 02 ima dva događaja, ali jednog izmenjenog kupca.

| Paket / datum isporuke | Redova | Ubačeni | Ažurirani | Poslovno nepromenjeni | Scenario |
| --- | ---: | --- | --- | --- | --- |
| 00_snapshot / 01.01.2026 | 3 | C1,C2,C3 | — | — | Početno stanje u praznom demo cilju |
| 01_changes / 02.01.2026 | 3 | C4 | C1 | C2,C3 | Novo prezime C1 v2; C2 nov događaj bez izmene |
| 02_versions / 03.01.2026 | 2 | — | C1 | C2,C3,C4 | C1 v4 u 15h naveden PRE v3 u 09h; poslednje stanje mora biti v4 |
| 03_late_arrival / 04.01.2026 | 3 | C5 | C2 | C1,C3,C4 | Ponovljen C1 događaj iz 01; zakasneli novi C5 i izmena C2 iz 02.01 u 12h |
| 04_stale / 05.01.2026 | 2 | — | — | C1–C5 | Nepoznat ali zastareo C1 događaj iz 02.01 u 13h; C2 no-change iz 05.01 |
| 05_replay / 06.01.2026 | 3 | — | — | C1–C5 | Identično ponavljanje celog paketa 01, sa istim batch_id |
| 06_negative / 07.01.2026 | 1 | — | — | C1–C5 | Nedostaje obavezni cst_id; ceo paket odbijen |

C1 se prvo ubacuje sa početnim sintetičkim prezimenom. Paket 01 ga menja na sufiks _v2.
Paket 02 mora sortirati njegove događaje po source_updated_at: _v3 u 09h, zatim _v4 u 15h,
bez obzira na obrnut fizički redosled CSV redova. U paketu 03 ponovljeni _v2 događaj je duplicate,
ne nova izmena. Paket 04 nosi drugačiji event_id, ali stariju verziju: stale, bez vraćanja na _stale.
Ponavljanje paketa 01 i negativni paket ga ne menjaju. Konačno ostaje _v4, sa prvobitnim create_date.

C2 pokazuje razliku poslovnog i tehničkog stanja. No-change u 01 unapređuje prihvaćeno source vreme,
iako poslovne kolone ostaju iste. Zakasnela izmena u 03 ima vreme 02.01 u 12h, novije od C2 verzije
u 11h, pa menja marital status S u M. No-change u 04 ponovo unapređuje source vreme; to je važno
za odbijanje kasnijih zastarelih događaja. Nepromenjene poslovne vrednosti ne znače zamrznut watermark.

## Slojevi validacije i očekivanja

- **structure_errors**: encoding, quoting, tačno zaglavlje, širina reda, prazan paket, završni newline.
- **contract_errors**: obavezni/validni demo ID-jevi, tipovi, UTC format, domeni, sintetička imena.
  Negativni paket ima ispravan CSV oblik i manifest, ali jednu ugovornu grešku: nedostaje cst_id.
- **integrity_errors**: nedostajući fajlovi, neispravan manifest, broj redova/hash/batch_id koji se ne poklapa.
- Ponovljen event_id i stari/out-of-order timestamp sami ne izazivaju nijednu od tih grešaka.
  Razlikovanje duplicate od konfliktnog ponavljanja zahteva trajni ledger budućeg loadera.

`expectations.json` je eksplicitna specifikacija, a ne rezultat izvršenog SQL-a. Navodi akcije
insert/update/no_change/duplicate/stale/batch_replay/reject i očekivano izvorno stanje, sa poslednjim
prihvaćenim event_id/vremenom. Generator nema opšti upsert engine. Nezavisan interpreter samo u testovima
primenjuje pravila nad memorijom i poredi stanje, akcije i skupove promenjenih kupaca sa specifikacijom.
`verify` poredi i sadržaj sa poznatim fixture specifikacijama, pa izmena očekivanja ne može prikriti grešku.
Ovo ne zamenjuje buduće integration testove transakcija, zaključavanja, SQL tipova i oporavka baze.

## Plan faze 3B — dokumentacija, bez SQL implementacije

1. Definisati izolovan demo cilj i staging tabelu sa batch_id, ordinal reda, event_id, source_updated_at
   i sirovim CRM kolonama. Validirati ceo paket i njegov hash pre izmene Silver-a. Snapshot je bootstrap
   praznog demo stanja; nije zahtev za TRUNCATE postojeće baze. Ne uvoditi brisanje.
2. Trajno čuvati ledger obrađenih paketa (batch_id + content hash + status) i događaja
   (event_id + payload hash + ishod). Isti batch/event sa istim payload-om je bezbedno ponavljanje.
   Isti ID sa drugim payload-om je konflikt i mora zaustaviti paket, ne tiho prepisivanje.
3. Upsert Silver CRM kupaca po cst_id, uz jedinstvenost poslovnog ključa u budućem demo modelu:
   nepostojeći ključ -> INSERT; novija verzija sa izmenjenim normalizovanim poslovnim vrednostima -> UPDATE;
   iste poslovne vrednosti -> no_change, ali unaprediti prihvaćeni source_updated_at.
   To je **SCD Type 1**: jedno poslednje poslovno stanje, bez istorijskih dimenzionih redova.
   Tehnički ledger događaja služi idempotentnosti i ne predstavlja SCD Type 2.
4. Obrađivati događaje po source_updated_at rastuće po kupcu, ne fizičkom redosledu CSV-a. Čuvati
   poslednje prihvaćeno vreme po kupcu (u ciljnoj tehničkoj koloni ili posebnoj tabeli stanja izvora).
   Starija verzija -> evidentirati stale i označiti događaj obrađenim bez izmene kupca. Za isti timestamp:
   identičan payload može biti no_change; različite poslovne vrednosti zahtevaju konflikt/review i odbijanje
   paketa. Leksički event_id nije poslovni dokaz da je jedna takva promena novija. V1 nema taj konflikt,
   pa ga treba dodati u integration testove budućeg loadera.
5. Jedna transakcija obuhvata proveru trajnog ledger-a, sve upsert-e, source-version stanje, oznake
   obrađenih događaja i uspeh paketa. Greška -> rollback celog paketa. Odgovarajuća zaključavanja i
   jedinstveni indeksi moraju sprečiti trku pri istovremenom ponavljanju. Retry posle pada treba ili da
   obradi ceo ranije necommitovan paket ili prepozna ranije commitovan batch_id i ne uradi ništa.
   Postojeći full-load sa autocommit=True nema ove garancije i neće se prepravljati usput.
6. Integration testovi treba da primene svih sedam isporuka u kontrolisanom test cilju, proveravaju
   stanje posle svake, ponove događaje/pakete, simuliraju pad pre/posle commit-a i provere konkurentnost.

**Zašto globalni timestamp watermark nije dovoljan:** nakon paketa 02 najveće viđeno vreme je
03.01.2026 u 15h. Ako sledeće čitanje uzme samo `source_updated_at > watermark`, odbaciće oba nova
za sistem događaja iz paketa 03 sa vremenom 02.01 u 12h: novog C5 i validnu izmenu C2. Potrebno je
preuzeti svaku novu isporuku (ili source log/cursor sa garantovanom pokrivenošću), deduplikovati događaje
trajno i odlučiti o zastarelosti po kupcu. Sam lookback prozor bez garancije kašnjenja takođe nije dovoljan.

**Zašto Gold ROW_NUMBER nije trajni ključ:** postojeći gold.dim_customers računa customer_key preko
`ROW_NUMBER() OVER (ORDER BY cst_id)` pri čitanju view-a. Promena skupa ili redosleda može promeniti
brojeve; oni nisu jednom dodeljeni i trajno sačuvani surrogate ključevi. Ne čuvati ih u event ledger-u
ili budućim trajnim referencama. Faza 3B treba da se oslanja na poslovni cst_id; eventualni trajni Gold
surrogate ključevi zahtevaju zaseban, eksplicitno projektovan mehanizam, ne prećutnu pretpostavku.

Faza 3A se završava generatorom, ugovorom, testovima i verifikovanim runtime fajlovima. SQL plan iznad
nije implementiran i nije izvršeno nijedno povezivanje sa bazom za ovu fazu.
