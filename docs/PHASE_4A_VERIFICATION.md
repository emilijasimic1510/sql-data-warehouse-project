# Faza 4A — završna verifikacija

Datum: 12.10.2026. Potvrđeni cilj: DESKTOP-N1402MQ\SQLEXPRESS, DataWarehouse.
Kreirani i menjani su samo novi mart objekti. Originalni Bronze/Silver/Gold, full-load pipeline i
crm_incremental demo ostali su netaknuti. Gold view-ovi sačuvani su kao baseline.
Nalazi dokumentovani pre izbora modela: [MART_SOURCE_FINDINGS.md](MART_SOURCE_FINDINGS.md).

## Model i grain

| Objekat | Grain | Konačno redova, uključujući unknown |
| --- | --- | ---: |
| mart.dim_customer | Jedan customer_id, SCD Type 1, trajni surrogate key | 18485 |
| mart.dim_product | Jedna izvorna (product_number, valid_from) verzija, trajni ključ | 398 |
| mart.dim_date | Jedan datum, stabilni YYYYMMDD date_key | 1140 |
| mart.fact_sales | Jedan izvorni prodajni zapis, multiplicitet očuvan | 60398 |

Realnih članova: 18484 kupca, 397 product verzija (295 otvorenih + 102 zatvorene), 1139 datuma.
Svaka dimenzija ima dodatni unknown red sa ključem 0. Unknown datum ima NULL calendar_date.
Date raspon: 2010-12-29–2014-02-09, uključujući shipping/due datume.

Order_number nije PK: izvor ima 27659 porudžbina za 60398 prodajnih zapisa. Posmatrana kombinacija
order/product/customer trenutno je jedinstvena, ali nema deklarisanog trajnog line_id. Zato fact
ostaje full-refresh, bez deduplikacije ili tvrdnje da tehnički fact_key označava trajnu izvornu stavku.
Iznosi/cena su decimal(19,2), količina bigint. Dimenzione IDENTITY vrednosti se ne resetuju.

## Testovi

Kompletan suite:

```text
python -m pytest -q
123 passed, 11 skipped in 6.66s
```

Prethodnih 111 unit slučajeva sačuvano je; dodato 12 mart slučajeva. Jedanaest skip-ova su opt-in SQL
slučajevi: prethodnih 7 CRM i nova 4 mart testa. Nisu ponavljani završeni CRM load testovi.

Prvi stvarni mart SQL suite:

```text
3 passed, 1 failed in 49.61s
```

Oba mart load-a, sve precommit provere, stabilnost ključeva i multiskupa već su prošli. Greška je bila
isključivo u naknadnom read-only Gold test upitu: CAST(cost AS int) nije imao alias u derived tabeli
(SQL 8155). Ispravljen je test query, bez promene modela ili source podataka. Ponovljen je samo taj test:

```text
python -m pytest ... tests/integration/test_mart_sql.py -k two_loads
1 passed, 3 deselected in 27.99s
```

Sva četiri nova SQL test slučaja su time uspešno proverena. Zbog ponavljanja neuspelog test slučaja
stvarno su izvršena **četiri commitovana mart load-a**, u dva para, i jedan dodatni namerno neuspešan
necommitovani quality pokušaj. Ovo nije prikazano kao samo dva izvršavanja. Prvobitni JSON izveštaji
sačuvani su, a potvrđujući par dobio je nova UUID imena izveštaja.
Dry-run CLI odvojeno je izvršen i dao PASS / exit 0 bez SQL konekcije.

## Reconciliation i stabilnost

Svaki commitovani load ima nula anomalija u svih 14 ERROR provera M01–M14. Provere uključuju PK/business
jedinstvenost, FK, product intervale, temporalni matching, date role-e, source broj redova, ukupnu
količinu/iznos i pun multiskup devet poslovnih source polja (sa count-om svake ponovljene kombinacije).
Precommit gate ne dozvoljava objavu kritične razlike.

| Metrika | Silver | Mart |
| --- | ---: | ---: |
| Prodajni redovi | 60398 | 60398 |
| Ukupna količina | 60423 | 60423 |
| Ukupni iznos | 29356250.00 | 29356250.00 |

Za dva load-a u oba para sačuvano je kompletno mapiranje business key -> surrogate key za customer,
product verzije i datume. Mape se potpuno podudaraju; njihovi SHA-256 potpisi takođe su isti.
Kompletan sadržaj svih dimenzija identičan je, ne samo broj redova. Fact poslovni redovi poređeni su
kao sortirani multiskup, bez tehničkog fact_key, sa svim dimenzionim/source poljima i multiplicitetom.
Sva četiri commitovana load-a imaju isti fact poslovni hash. Fact identity brojevi nisu očekivano isti.

Unit testovi proveravaju default dry-run, CLI greške, jednu transakciju, WARNING uspeh, quality ERROR
rollback, late SQL grešku, bezbedan failure JSON, zaštitu postojećeg report-a i odbijanje deployment drift-a.
Stvarni SQL testovi proveravaju source multiset, dimenzione mape/sadržaj, Gold atribute, stvarne granice
intervala, nedostajuće datume, precommit rollback, redeployment i očuvanje originalnih objekata.

## Istorija i razlike prema Gold-u

| Nalaz | Gold baseline | Mart |
| --- | --- | --- |
| Product verzije | 295 aktuelnih | 397 izvornih verzija + unknown |
| Product veza prodaje | Po broju proizvoda na aktuelnu verziju | Po broju i order datumu na važeću verziju |
| Prodajni redovi | 60398 | 60398 |
| Prodaja na zatvorenim verzijama | Nema istorijskog member-a | 8246 |
| Prodaje pre najranije poznate istorije proizvoda | Povezane sa current member-om | 18410 unknown, razlog BEFORE_HISTORY |
| Nedostajući order datum | Nema pouzdane temporalne verzije | 19 unknown product i unknown order_date |

Mart ima 41969 poznatih temporalnih product veza: 33723 current i 8246 zatvorene verzije.
Ukupno unknown product veza je 18429. Nema MISSING_PRODUCT_KEY, AFTER_HISTORY ili INTERVAL_GAP slučajeva.
Unknown customer/shipping/due broj je nula. Warning U02 i U07 opisuju istih 19 prodaja, pa se ne sabiraju
kao različite prodaje. Source istorija se ne proširuje veštački da bi unknown broj postao nula.

Customer atributi i atributi 295 current proizvoda upoređeni su sa Gold-om, nezavisno od surrogate
ključevа, bez razlika. Source i mart temporalni matching provereni su za svaki interval na start/end,
dan pre početka, dan nakon zatvorenog kraja i NULL datum. Nula razlika/dvosmislenih verzija.
155 stvarnih prodaja nalazi se tačno na valid_from, 25 tačno na valid_to, i mapiranje je ispravno.
Granice su inkluzivne; NULL valid_to označava otvoren kraj.

Primer: porudžbina SO45080, proizvod BK-R50B-58, order_date 2011-07-01, quantity 1, amount 699.
Mart je povezuje sa verzijom 2011-07-01–2012-06-30: datum prodaje je na uključenoj početnoj granici.
Kasnija/current verzija istog product broja nije automatski dodeljena ovoj prodaji. SQL za pregled
verzija i ovog fact reda nalazi se u [MART.md](MART.md).

## Transakciona objava i dokaz rollback-a

Caller otvara jednu SERIALIZABLE transakciju na autocommit=True konekciji i uzima application lock.
Load procedura pravi zaključane lokalne source kopije, ažurira dims uz iste ključeve i DELETE/INSERT
osvežava fact. Mart.check_quality radi pre COMMIT-a. Normalni read-committed čitaoci vide prethodno ili
novo commitovano stanje, uz moguće čekanje; NOLOCK nema te garancije.

Stvarni integration fault test izvršio je mart load u transakciji, a zatim namerno povećao quantity
jednog mart fact reda pre quality poziva. M10 (total quantity) i M12 (pun multiskup) prijavili su ERROR;
COMMIT nije izvršen. Zasebna konekcija potvrdila je identičan prethodni fact sadržaj, uključujući njegove
tehničke ključeve. Ovo je izvršena SQL mutacija i rollback, ne mock tvrdnja. Silver nije menjan.

Deployment ponovljen nakon popunjavanja: potpis je VERIFIED, nijedna mart tabela nije promenjena.
Objekti, constraints/indeksi/procedure i deployment source moraju odgovarati sačuvanoj verziji/potpisu;
nekоmpatibilnost zahteva eksplicitnu migraciju. Normalno učitavanje ne kreira/menja SQL definicije.

## Očuvanje i artefakti

Pre deployment-a i nakon oba SQL test izvršavanja čitani su svih 15 originalnih business objekata i svih
5 crm_incremental tabela. Njihovi kompletni sortirani multiskupovi, sa load timestamp-ovima i ključevima,
ostali su isti. Nije korišćen samo broj redova kao dokaz jednakosti. Pet CRM-demo kupaca ostaje sačuvano.
Originalni CSV, svi postojeći Python/SQL paketi i dependencies, kao i Git indeks, prošli su SHA-256
poređenje pre/posle. Nema commita, pusha, service/credential promena ili drugih baza/instanci.

Sažetak i dokaz: [PHASE_4A_RESULTS.json](PHASE_4A_RESULTS.json). Lokalni report-i pod reports/ su
ignorisani. Tu su dry-run, prvobitni i potvrđujući load report-i, kao i oba SQL evidence JSON-a.
Tačne deployment/dry-run/execute komande i nekoliko SSMS upita: [MART.md](MART.md).

## Ograničenja

Nema trajnog source line_id za inkrementalni fact. Customer je Type 1, a product istorija je uvoz
postojećih Silver intervala, ne generički CDC. Nepostojeća prošlost ostaje unknown. Nema currency
metapodataka, automatskog retry-a, schedulera ili Power BI-a. Koordinisati sa originalnim višekoračnim
full-load-om; mart application lock ne pretvara njegove autocommit korake u jedan source snapshot.
Identity može imati gap-ove posle rollback-a. Gubitak COMMIT potvrde/disk greška report-a zahteva
proveru mart-a; ti failure scenariji nisu posebno simulirani. Faza 4A ovde staje.
