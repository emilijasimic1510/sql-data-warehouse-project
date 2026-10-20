# Faza 3B: izolovani CRM inkrementalni SQL loader

Demo radi isključivo u `crm_incremental` šemi baze DataWarehouse. Tabela `customers` je SCD Type 1:
jedan red poslednjeg prihvaćenog stanja po poslovnom ključu `cst_id`. **Nije povezan sa Gold analitikom.**
Bronze/Silver/Gold, njihove procedure i postojeći `warehouse_pipeline` nisu menjani.

## Arhitektura

| Objekat | Uloga |
| --- | --- |
| crm_incremental.customers | Normalizovano poslednje stanje, PK cst_id, UNIQUE cst_key, source_updated_at, last_event_id, business_hash |
| crm_incremental.attempts | Svaka commitovana uspešna isporuka/pokušaj, uključujući REPLAY; UTC početak/kraj i odvojene metrike |
| crm_incremental.batches | Jedan zapis po prihvaćenom batch_id, originalni SHA-256 sadržaja, tip i broj događaja |
| crm_incremental.events | Jedan zapis po jedinstvenom event_id: kanonski hash, kupac/vreme, izvorni batch i prvi ishod |
| crm_incremental.staging | Redovi izolovani po attempt_id + ordinal; na uspeh ostaju kao evidencija svake isporuke i njenog ishoda |
| crm_incremental.apply_batch | Provera konflikata, uređena obrada događaja, upsert i izračunavanje metrika |

Staging nema UNIQUE na event_id jer su ponovljeni događaji dozvoljeni. PK sprečava ponavljanje ordinala
unutar istog pokušaja. Indeksi podržavaju obradu staging-a po kupcu/vremenu, pretragu događaja po
kupcu/vremenu i pokušaja po batch_id. FK povezuju staging–attempts, events–customers/batches i
batches–prvi pokušaj. CHECK ograničava demo ID prostor, normalizovane domene, datume, statuse i brojeve.
Ledger sadrži tehničku evidenciju, ne istorijske verzije dimenzije; to nije SCD Type 2.

`crm_incremental/inputs.py` učitava bajtove CSV-a i manifesta, kopira ih u privatni privremeni direktorijum,
i poziva postojeći `crm_demo.validation.validate_package`. Tako se ponovo koristi ceo validator i
njegova SHA-256 provera bez kopiranja pravila. Parsiraju se baš zamrznuti, validirani bajtovi; naknadna
izmena originalnog fajla ne menja događaje poslate u SQL. Negativan paket se odbija pre SQL konekcije.
Python šalje parametrizovane vrednosti u staging; SQL Server ne čita CSV fajlove sa diska.

`inputs.py` priprema normalizovane vrednosti po postojećem CRM pravilu: TRIM imena, S/M -> Single/Married,
F/M -> Female/Male, ostalo -> n/a. Nema izvršavanja ili izmene postojeće Silver procedure.
`database.py` upravlja transakcijom; `runner.py` dodaje paket/suite režim i JSON; `deploy.py` je poseban,
eksplicitni deployment ulaz. Koriste se postojeći connection/target-check i reporting pomoćni moduli.
Nema novih zavisnosti.

## Tačne komande

PowerShell, iz korena repozitorijuma:

```powershell
$target = @('--server', 'DESKTOP-N1402MQ\SQLEXPRESS', '--expected-server', 'DESKTOP-N1402MQ\SQLEXPRESS', '--database', 'DataWarehouse', '--trust-server-certificate')

# Eksplicitni deployment ili read-only potvrda nepromenjene postojeće deployment strukture:
.\.venv\Scripts\python.exe -m crm_incremental.deploy @target

# Dry-run jednog paketa: lokalna validacija, bez SQL konekcije.
.\.venv\Scripts\python.exe -m crm_incremental --package-dir .\demo_output\phase3a-seed42\01_changes --dry-run --report-path ('.\reports\incremental-dry-' + [guid]::NewGuid() + '.json')

# Stvarno izvršavanje jednog paketa (postojeći obrađeni paket postaje REPLAY).
.\.venv\Scripts\python.exe -m crm_incremental @target --package-dir .\demo_output\phase3a-seed42\01_changes --execute --report-path ('.\reports\incremental-one-' + [guid]::NewGuid() + '.json')

# Uređeni kompletan demo skup: šest validnih isporuka, zatim obavezno odbijanje negativne.
.\.venv\Scripts\python.exe -m crm_incremental @target --suite-dir .\demo_output\phase3a-seed42 --execute --report-path ('.\reports\incremental-suite-' + [guid]::NewGuid() + '.json')
$LASTEXITCODE
```

Kompletan suite namerno uključuje negativni paket: finalni status je **FAIL / exit 1** zbog REJECTED
paketa, čak i kada svih šest validnih isporuka prođe. To nije rollback prethodnih paketa: transakcija je
po paketu. Izveštaj čuva zasebne statuse svih pokušaja. Isto važi za suite dry-run; samostalni validni
paket daje exit 0. Zaustavljanje je na prvom REJECTED/FAIL. Ne postoji opcija koja neispravan zapis
proglašava uspešno učitanim. `crm_demo verify` ostaje posebna provera fixture-a sa očekivanim negativnim
ishodom, dok incremental CLI prijavljuje stvarne ishode prihvatanja paketa.

Pre suite obrade radi se postojeći `verify_suite`, pa izmenjen redosled/očekivanja ili oštećen demo skup
ne pokreću nijedan SQL paket. Svaki pojedinačan paket se ponovo zamrzne i validira neposredno pre obrade.

Default je dry-run; --execute je eksplicitna opcija, bez environment prečice. --execute i --dry-run su
međusobno isključivi, kao i --package-dir i --suite-dir. Execute zahteva server, database i expected-server.
Podržani su DW_SERVER, DW_DATABASE, DW_EXPECTED_SERVER i DW_ODBC_DRIVER; driver je podrazumevano
ODBC Driver 17 for SQL Server. Windows autentifikacija i Encrypt=yes su sačuvani; certificate trust je
samo per-connection opcija. Deployment u ovom projektu dodatno zahteva DB_NAME() = DataWarehouse.
Pre prve mutacije proveravaju se stvarno ime instance i baza; nema automatskog kreiranja baze.

## Deployment i kompatibilnost

`scripts/crm_incremental/deploy.sql` je eksplicitna, nedestruktivna skripta sa jednom transakcijom i
TRY/CATCH/XACT_ABORT. Početno pravi samo pet tabela, njihove constraints/indekse i proceduru u novoj šemi.
Nema DROP/TRUNCATE. Postojeće nepoznate objekte odbija ako nemaju odgovarajuću verziju i metapodatke.

Prvi deployment čuva contract_version=1 i SHA-256 potpis stvarnih objekata u schema extended properties.
Potpis obuhvata kolone/tipove/nullability/defaults, indekse, FK/CHECK definicije i status, objekte i tekst
procedure. Ponovni deployment mora dobiti isti potpis; promenjena/nepotpuna/nekompatibilna šema dobija
51191 i rollback. Ne prepisuje se procedura niti popravljaju tabele prećutno. Skripta nije migration engine:
za buduću promenu modela potreban je eksplicitan migration i nova verzija ugovora. Potpis je zaštita od
drift-a, ne od administratora koji može menjati i potpis i objekte. Normalan loader ne izvršava DDL.

## Jedina transakciona granica paketa

1. Lokalna validacija celog paketa završi se pre konekcije/mutacije.
2. Konekcija koristi `autocommit=True`, kao postojeći connection helper; to isključuje skrivenu pyodbc
   transakciju. Loader eksplicitno šalje `SET XACT_ABORT ON; BEGIN TRANSACTION`.
3. Pre staging-a uzima se ekskluzivan transaction-owned application lock `crm_incremental.loader.v1`.
   Timeout je 10 sekundi. Za ovaj mali demo svi loader pokušaji su serijalizovani, uključujući replay.
4. U istoj transakciji INSERT attempts, parametrizovani INSERT staging i EXEC apply_batch. Procedura
   zahteva @@TRANCOUNT=1 i ponovo proverava isti application lock za pozive van Python CLI-ja.
   Ne otvara drugu/nested transakciju i ne radi COMMIT.
5. SQL procedura rešava sve događaje i upisuje uspešne ledgere i metrike. Python mora da pročita rezultat
   i iscrpi nextset() pre slanja jedinog COMMIT TRANSACTION. Tek nakon potvrde commit-a izveštava uspeh.
6. SQL TRY/CATCH vraća celu aktivnu transakciju i THROW. Python pri grešci dodatno pokušava rollback
   ako transakcija postoji. Zatvaranje neuspešne konekcije ne ostavlja necommitovane promene.

Ne koriste se connection.commit()/rollback() niti savepoint-i koji bi podelili paket. Attempts sa
RUNNING statusom postoje samo unutar necommitovane transakcije. Neuspešni pokušaji ne ostavljaju staging,
customers izmene ili uspešne ledger zapise. Njihova greška ostaje u lokalnom JSON-u; SQL nema zaseban
failure-audit van transakcije. Gubitak konekcije pri COMMIT potvrdi može značiti nepoznat ishod: report
navodi committed=null za SQL neuspeh i traži proveru batch_id. Ponovno slanje je idempotentno ako je
commit ipak uspeo. Greška pisanja JSON-a posle SQL commit-a ne može poništiti već završenu transakciju.

## Idempotentnost i redosled

- Isti batch_id, content SHA, tip i broj redova -> REPLAY, nula poslovnih promena. Novi attempt/staging
  beleže ponovnu isporuku; ne nastaje drugi batch ili novi event ledger red.
- Isti batch_id sa drugim sadržajem -> 51110. Standardni validator obično odbije to još pre SQL-a;
  integration test proverava i SQL odbranu direktnim parametrima.
- Isti event_id i kanonski event hash -> duplicate. Isti ID sa drugim payload-om -> 51111, ceo paket pada.
  Proveravaju se i međusobni konflikti unutar istog staging-a.
- Jednako source vreme istog kupca sa različitim normalizovanim poslovnim vrednostima -> 51112, odbijanje.
  Provera pokriva staging, postojeći event ledger (i istorijska vremena) i trenutno stanje kupca.
  Jednako vreme i iste vrednosti -> no_change; prethodni last_event_id ostaje prihvaćeni pointer.
- Novi događaji obrađuju se po cst_id, source_updated_at, event_id, ordinal. Tie-break po event_id
  razrešava samo jednake vrednosti; ne koristi se da prikrije dvosmislen konflikt.
- Nepostojeći kupac -> insert. Novija promena -> update. Novije iste vrednosti -> no_change, ali se
  source vreme i last_event_id unapređuju. Stariji događaj -> stale, bez vraćanja stare verzije.
- Snapshot je skup početnih/additivnih događaja; nikada ne briše kupce koji nisu prisutni.

Batch hash pokriva tačne CSV bajtove, pa drugi redosled redova može biti drugi batch. Event hash se
računa iz imenovanih polja u sortiranoj kanonskoj JSON reprezentaciji: cst_id je int, datum je ISO datum,
source_updated_at je parsiran timezone-aware i pretvoren u UTC sa fiksnih šest decimala. Ne zavisi od
redosleda dict/CSV mapiranja, niti od ekvivalentnog zapisa vremenske zone/fractional seconds. Event_id
ne ulazi u payload hash: dva različita ID-ja mogu identifikovati sadržajno iste događaje.
Business hash obuhvata normalizovane CRM kolone, bez event_id i source vremena. Verzija kanonizacije je 1.
Strogi CSV ugovor faze 3A i dalje zahteva tačno zaglavlje i UTC Z format; normalizacija ne proširuje taj
validator. Integration SQL granica veruje kanonskim vrednostima/hash-evima ovog klijenta; direktan DML
pristup drugim piscima nije podržan i treba ga ograničiti dozvolama u budućem produkcionom dizajnu.

## Metrike i JSON

Svaki paket prijavljuje batch_id, status, input_events, inserted_customers, updated_customers,
insert_events, update_events, no_change_events, stale_events, duplicate_events, UTC vremena i bezbednu
poruku neuspeha. Pokušaj ima poseban UUID, za razliku od determinističkog batch_id.

inserted_customers je broj različitih novih ključeva posle paketa. updated_customers je broj postojećih
kupaca čije se konačne poslovne vrednosti razlikuju od stanja pre paketa. Paket 02 ima dva update_events,
ali updated_customers=1. Ako bi izmene unutar paketa vratile početne vrednosti, broj poslovno promenjenih
kupaca bio bi nula uprkos update događajima. Event metričke kategorije su odvojene; na REPLAY se svi
ulazni redovi broje kao duplicate_events, dok staging preciznije kaže batch_replay.

JSON ne sadrži imena, vrednosti kupaca, raw driver tekst ili kredencijale. SQL greške prikazuju SQLSTATE
plus prepoznatljivu internu šifru 511xx kada postoji. --report-path rezerviše novi .json pre rada, van
ulaznog i originalnog dataset foldera. Postojeći report ostaje netaknut osim uz --overwrite-report.
Report je prvo RUNNING, zatim finalizovan. Nagli prekid procesa/disk greška mogu ostaviti nezavršen
lokalni report; SQL ledger je autoritativan za commitovane pakete. Fajlovi pod reports/ su ignorisani.

## SSMS pregled

```sql
USE DataWarehouse;
SELECT cst_id,cst_key,cst_firstname,cst_lastname,cst_marital_status,cst_gndr,
       cst_create_date,source_updated_at,last_event_id
FROM crm_incremental.customers ORDER BY cst_id;

SELECT * FROM crm_incremental.batches ORDER BY committed_at_utc;
SELECT * FROM crm_incremental.attempts ORDER BY started_at_utc,attempt_id;
SELECT event_id,cst_id,source_updated_at,outcome,batch_id
FROM crm_incremental.events ORDER BY cst_id,source_updated_at,event_id;

DECLARE @attempt uniqueidentifier = (
    SELECT TOP (1) attempt_id FROM crm_incremental.attempts ORDER BY started_at_utc DESC,attempt_id DESC
);
SELECT ordinal,event_id,cst_id,source_updated_at,outcome
FROM crm_incremental.staging WHERE attempt_id=@attempt ORDER BY ordinal;
```

## Testiranje i granice

```powershell
# Svi unit testovi; live SQL testovi ostaju jasno preskočeni.
.\.venv\Scripts\python.exe -m pytest -q

# Eksplicitni integration testovi za dozvoljeni lokalni cilj.
$env:DW_RUN_SQL_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest -q -s tests\integration\test_crm_incremental_sql.py
Remove-Item Env:DW_RUN_SQL_INTEGRATION
```

Live suite je namenjen jednokratnoj prvoj verifikaciji praznog demo prostora 1900000000–1900000899.
Nakon ove faze demo je popunjen: nemoj slepo ponavljati taj test suite niti brisati demo rezultate da bi
ponovo prošao početni assert. Za dalje replay provere koristi CLI nad sačuvanim paketima. Posebni testovi
koriste 1900000900–1900000999, proveravaju da je prostor prazan i čiste samo registrovane test identitete.
Detaljni izvršeni rezultati su u [PHASE_3B_VERIFICATION.md](PHASE_3B_VERIFICATION.md).

Ovo je mali serijalizovani demo, ne visokopropusni CDC sistem. Nema delete događaja, SCD Type 2,
automatskog retry-a, retention posla za staging/attempts, ni migracija šeme. Rast replay evidencije je
namerno vidljiv. Nisu testirani nasilni prekid servera ili gubitak mreže baš u toku COMMIT-a.
Gold ROW_NUMBER ključevi nisu trajni ključevi i ovde se ne koriste. Globalni source watermark se ne koristi:
svaka isporuka se pregleda, a zastarelost određuje po kupcu. Nema Airflow/Docker/cloud dodataka.
