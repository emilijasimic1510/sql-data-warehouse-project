# Faza 4A: trajni prodajni mart

Faza 4B dodaje [koordinisani E2E runner](E2E_PIPELINE.md). Samostalni mart sada uzima zajednički
session project lock pre postojeće mart transakcije; unutar E2E pozajmljuje parent konekciju/lock.
SQL model, istorijska/unknown pravila i sopstveni precommit quality gate ostaju isti.

Nova `mart` šema fizički čuva dim_customer, dim_product, dim_date i fact_sales. Postojeći Gold view-ovi
ostaju baseline za poređenje. `crm_incremental` demo nije izvor mart-a i nije povezan sa prodajom.
Pre-implementation nalazi i odluke: [MART_SOURCE_FINDINGS.md](MART_SOURCE_FINDINGS.md).

## Objekti i grain

| Objekat | Grain / ključ | Strategija |
| --- | --- | --- |
| mart.dim_customer | Jedan CRM customer_id; trajni IDENTITY customer_key | SCD Type 1, Silver CRM + ERP customer/location atributi |
| mart.dim_product | Jedna izvorna verzija (product_number, valid_from); trajni IDENTITY product_key | Uvoz sve istorije već prisutne u Silver-u |
| mart.dim_date | Jedan kalendarski datum; deterministički YYYYMMDD date_key | Raspon svih order/shipping/due datuma, aditivno |
| mart.fact_sales | Jedan izvorni Silver prodajni zapis, sa sačuvanim multiplicitetom | Full-refresh; fact_key je tehnički ključ publikacije |

Order_number nije jedinstven: 60398 prodajnih redova pripada 27659 porudžbina. U trenutnom uzorku je
(order_number, product_number, customer_id) jedinstveno, ali izvor nema line_id ili ugovor koji to
garantuje ubuduće. Ne deduplikuje se prodaja i ne proglašava se hash/ROW_NUMBER identitetom stavke.
Fact identity se može promeniti pri svakom osvežavanju; ne koristi se za trajne reference između load-ova.
Dimenzione identity vrednosti se nikada ne resetuju ili regenerišu. Datum ima deterministički ključ.

Amounts/price koriste DECIMAL(19,2), quantity BIGINT, a quality agregacije DECIMAL(38,2)/(38,0).
Izvorni Silver iznosi su INT: mart ne izmišlja decimale, valutu ili neto/bruto značenje iznosa.

## Dimenzije i istorija

Customer atributi prate odgovarajuće Silver join-ove kao postojeći Gold. Primary business key je cst_id,
a ERP join ključ cst_key. Dvosmisleni ERP/category join-ovi i nejedinstveni source ključevi zaustavljaju
učitavanje pre objave. SCD Type 1 prepisuje aktuelne customer atribute uz isti surrogate key.

Product verzija se identifikuje po (prd_key, prd_start_dt), ne po trenutnom Gold ROW_NUMBER ključu.
Interval je **[valid_from, valid_to]**, sa oba kraja uključena. Silver već postavlja kraj na dan pre
sledećeg početka; NULL valid_to znači otvoren kraj, bez veštačkog sentinel datuma u sačuvanoj tabeli.
Is_current važi za otvorenu verziju koja je prisutna u izvoru. Preklapanje ili isti business/start par
je kritična greška. Surrogate ključ verzije ostaje isti kada se pri sledećem učitavanju promeni njen
kraj/atribut. Izvorna istorija se uvozi: ovo još nije generički CDC/SCD Type 2 za proizvoljne promene.
Ako se promeni sam valid_from, to je druga verziona identifikacija i dobija drugi ključ.

Ako dimenzioni business key/verzija nestane iz Silver-a, fizički red i njegov ključ se zadržavaju uz
is_in_source=0. Nije dostupan za novo mapiranje prodaje. Time se ključevi ne recikliraju. Date dimenzija
zadržava prethodne datume i dodaje potreban raspon svih tri date role-a.

## Unknown politika

Svaka dimenzija ima jedan rezervisan član sa ključem **0**. Unknown date nema datum ni year/month/day
atribute (NULL), pa nema izmišljene vrednosti poput 1900-01-01. Fact čuva i originalne source datume i
business ključeve, radi verifikacije i dijagnostike.

- Nedostajući/nepronađen customer -> customer_key=0 i MISSING_CUSTOMER_KEY/NOT_IN_SOURCE.
- Order_date NULL -> order_date_key=0, product_key=0, MISSING_ORDER_DATE. Ne dodeljuje se aktuelna
  ili proizvoljna istorijska verzija proizvoda.
- Postoji key ali ne postoji vremenski važeća verzija -> product_key=0 sa BEFORE_HISTORY,
  AFTER_HISTORY ili INTERVAL_GAP. Nepoznat product key -> MISSING_PRODUCT_KEY.
- Nedostajući shipping/due datum -> odgovarajući date_key=0. Ostale poznate date role-e se nezavisno mapiraju.

Unknown nalazi su WARNING: prodajni red i iznos ostaju sačuvani. Izveštaj broji svaki razlog; ne koristi
samo jedan ukupan broj koji skriva uzrok. Poznata verzija se povezuje samo kada order datum pripada
inkluzivnom intervalu. Ako postoje dve verzije za taj datum, greška zaustavlja load; nema TOP 1 nagađanja.

## Deployment i komande

Iz korena projekta u PowerShell-u, sa postojećom .venv:

```powershell
$target = @('--server', 'DESKTOP-N1402MQ\SQLEXPRESS', '--expected-server', 'DESKTOP-N1402MQ\SQLEXPRESS', '--database', 'DataWarehouse', '--trust-server-certificate')

.\.venv\Scripts\python.exe -m mart_pipeline.deploy @target

.\.venv\Scripts\python.exe -m mart_pipeline --dry-run --report-path ('.\reports\mart-dry-' + [guid]::NewGuid() + '.json')

.\.venv\Scripts\python.exe -m mart_pipeline @target --execute --report-path ('.\reports\mart-execute-' + [guid]::NewGuid() + '.json')
$LASTEXITCODE
```

Deployment CLI je eksplicitna granica za `scripts/mart/schema.sql`, `load.sql`, `quality.sql`. Sve tri
komponente izvršava unutar jedne transakcije nakon provere očekivane instance/baze, sa application lock-om.
Nema DROP, TRUNCATE ili promene drugih šema. Ponovni deployment proverava contract version 1, stvarni
metadata potpis i hash sva tri source deployment fajla. Izmenjena šema/procedure/indeksi/constraints ili
izmenjen deployment source zahtevaju eksplicitnu migraciju; ništa se prećutno ne prepravlja ili ignoriše.
Skripte se ne pokreću nezavisno mimo ovog wrapper-a. Normalno učitavanje ne kreira SQL objekte.

Default dry-run ne otvara SQL konekciju: prikazuje plan. --execute i --dry-run su međusobno isključivi.
Za execute su potrebni server/database/expected-server (CLI ili postojeći DW_* environment defaults).
ODBC driver i per-connection certificate trust prate postojeći connection helper. Nema credential ili
globalnih postavki. JSON se rezerviše pre SQL rada, van originalnog datasets; ne prepisuje se bez
--overwrite-report. Ima UUID, UTC vremena, status, counts i aggregate check rezultate, bez customer
atributa i raw driver teksta. SQL greška ili quality ERROR daje exit 1; WARNING sam ne obara uspeh.
Invalid CLI daje 2. Report/disk greška može nastati posle commit-a; potvrđen committed=True tada ostaje
vidljiv i greška izveštaja ne može vratiti već završen SQL load.

## Transakciona objava

Python konekcija ostaje autocommit=True, ali šalje jednu eksplicitnu SQL BEGIN TRANSACTION. Isolation je
SERIALIZABLE; transaction-owned `mart.loader.v1` application lock serijalizuje mart load-ove. Procedura
prihvata tačno jednu caller-owned transakciju i koristi XACT_ABORT/TRY-CATCH/ROLLBACK/THROW. Ne otvara
sopstvenu nested transakciju. Iz Silver tabela se u transakciji prave #temp izvori uz HOLDLOCK.

Dims se ažuriraju/inseruju bez resetovanja ključeva. Fact se DELETE + INSERT potpuno osvežava, bez
resetovanja fact identity. Zatim Python izvršava canonical mart.check_quality i čita sve rezultate.
Svi ERROR nalazi moraju biti nula pre jedinog COMMIT-a. Late nextset SQL greška takođe sprečava COMMIT.
Ako load ili quality padne, prethodno objavljeni mart se vraća rollback-om. Identity brojači mogu imati
gap-ove posle rollback-a; to nije promena već dodeljenih dimenzionih ključeva.

Obični SQL read-committed čitaoci ne mogu videti necommitovane delove osvežavanja; mogu biti blokirani
do objave. NOLOCK čitaoci nemaju tu garanciju. Od faze 4B podržani Python warehouse i mart ulazi uzimaju
isti session project lock, dok postojeći mart transaction lock ostaje unutrašnja zaštita. Direktni SQL
pozivi bez project protokola nisu koordinisani. Višekoračni full-load nije jedan atomski snapshot.
Ne menja se database isolation konfiguracija.
Gubitak veze baš pri COMMIT potvrdi može ostaviti nepoznat ishod; izveštaj to navodi, bez automatskog retry-a.

## Jedinstveni quality registar

`scripts/mart/quality.sql` definiše jedinu canonical proceduru mart.check_quality. Python ne kopira
njene SQL uslove. Može se read-only izvršiti u SSMS-u, ali precommit gate radi kroz odvojeni loader.

- M01: PK i poslovna/version jedinstvenost.
- M02: fact FK integritet; M03/M04: intervali, preklapanja i current oznake.
- M05/M06: temporalna product veza i customer business key.
- M07/M08: date role mapiranje i unknown samo kada nema važećeg člana.
- M09–M11: source/fact redovi, količina i iznos.
- M12: kompletan multiskup svih devet poslovnih polja prodaje, GROUP BY + count + EXCEPT u oba smera.
  Proverava i multiplicitet; ukupni zbir/redovi sami ne dokazuju jednak sadržaj.
- M13/M14: unknown članovi i brojevi source dimenzionih redova.
- U01–U09: unknown customer/product razlozi i tri date role-a, kao WARNING counts.
- R01/R02: quantity/amount metrike bez praga; anomaly_count=NULL i metric_value kao tekst.

PK/FK/check/unique constraints dodatno sprovode model. Unknown redovi su isključeni iz poslovne
jedinstvenosti i intervala. Historijski retained absent product redovi su isključeni iz aktuelnih interval
provera i novih fact veza. Nema promene postojeće 28-check Silver/Gold registry konfiguracije.

## SQL pregled i analiza

```sql
USE DataWarehouse;
EXEC mart.check_quality;

SELECT product_number,product_key,valid_from,valid_to,is_current
FROM mart.dim_product WHERE product_number=N'BK-R50B-58' ORDER BY valid_from;

SELECT f.order_number,d.calendar_date AS order_date,p.product_number,p.valid_from,p.valid_to,
       f.quantity,f.sales_amount,f.product_match_reason
FROM mart.fact_sales f JOIN mart.dim_product p ON p.product_key=f.product_key
JOIN mart.dim_date d ON d.date_key=f.order_date_key
WHERE f.order_number=N'SO45080';

SELECT product_match_reason,COUNT_BIG(*) AS sales_rows,SUM(sales_amount) AS amount
FROM mart.fact_sales GROUP BY product_match_reason;

SELECT d.calendar_year,d.calendar_month,SUM(f.quantity) AS quantity,SUM(f.sales_amount) AS amount
FROM mart.fact_sales f JOIN mart.dim_date d ON d.date_key=f.order_date_key
WHERE f.order_date_key<>0 GROUP BY d.calendar_year,d.calendar_month ORDER BY d.calendar_year,d.calendar_month;
```

Poslednji upit eksplicitno isključuje unknown order datume; njihov iznos je dostupan u zasebnoj unknown
grupi i ne treba ga sakriti u konačnim zbirnim izveštajima.

## Testovi i granice

```powershell
.\.venv\Scripts\python.exe -m pytest -q
$env:DW_RUN_MART_INTEGRATION='1'
.\.venv\Scripts\python.exe -m pytest -q -s -p no:cacheprovider tests\integration\test_mart_sql.py
Remove-Item Env:DW_RUN_MART_INTEGRATION
```

SQL testovi rade samo nad mart-om; Source i CRM-demo objekti se čitaju i porede. Testovi dodatno rade
necommitovani mart load sa namernom quantity greškom; reconciliation mora sprečiti objavu. Nema
izmena izvornih podataka da bi provera prošla. Stvarni rezultati: [PHASE_4A_VERIFICATION.md](PHASE_4A_VERIFICATION.md).

Ograničenja: nema pouzdanog source line_id za inkrementalni fact, generičkog CDC istorijata, valute,
izmišljene product istorije ili customer istorije. Mart uvozi postojeće Silver intervale, čiji kvalitet
zavisi od prethodnih transformacija. Nema schedulera, Airflow-a, Docker-a, cloud-a ili Power BI-a.
