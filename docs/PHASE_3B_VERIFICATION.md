# Faza 3B — završna verifikacija

SQL verifikacija izvršena je 11.10.2026; završna dokumentacija zaključena 12.10.2026.
Cilj potvrđen pre mutacije: `DESKTOP-N1402MQ\SQLEXPRESS`, baza `DataWarehouse`.
Izmene baze ograničene su na novu `crm_incremental` šemu. Full-load tok i Bronze/Silver/Gold nisu menjani.
Demo nije povezan sa Gold analitikom. Faza 3B ovde staje.

## Implementacija

Napravljeno je pet tabela: customers, staging, batches, events i attempts, sa odgovarajućim ključevima,
CHECK/FK ograničenjima i indeksima, kao i procedura apply_batch. Customers čuva samo poslednje stanje
po cst_id, bez istorijskih verzija (SCD Type 1). Staging ostaje izolovan po attempt_id i ordinalu i čuva
ishode pojedinačnih isporuka. Events beleži jedinstvene događaje; attempts odvojeno evidentira replay.

Eksplicitni `scripts/crm_incremental/deploy.sql` ne briše podatke. Za postojeći deployment proverava
verziju i SHA-256 metapodataka objekata/procedure; nekompatibilna ili izmenjena struktura traži migraciju.
Python CLI ponovo koristi postojeći demo validator na zamrznutim ulaznim bajtovima. Serveru nije potreban
pristup CSV putanji. Hash događaja koristi imenovana, tipizirana polja i UTC kanonizaciju, nezavisno od
redosleda mapiranja ili ekvivalentnog formatiranja vremena; strogi ulazni CSV ugovor ostaje nepromenjen.

Jedna transakcija paketa obuhvata attempts, staging, customers i uspešne ledger zapise. Pyodbc radi sa
autocommit=True; Python eksplicitno šalje BEGIN i, tek posle svih SQL rezultata, COMMIT. Procedura nema
svoj nested BEGIN/COMMIT; ima XACT_ABORT, TRY/CATCH, ROLLBACK i THROW. Application lock serijalizuje
obradu, uključujući isti batch i upsert-e. Greške se beleže u lokalnom JSON-u bez ličnih podataka.

## Testovi — jasno odvojeno

Kompletan lokalni suite:

```text
.\.venv\Scripts\python.exe -m pytest -q
111 passed, 7 skipped in 3.51s
```

To uključuje prethodna 94 testa i 17 novih unit test slučajeva. SQL testovi su opt-in i zato se
podrazumevano preskaču. Pokriveni su validacija/manifesta, zamrznuti ulaz, kanonizacija, default dry-run,
CLI argumenti, transakciona komanda, rana/kasna SQL greška, zaštita JSON-a i redosled suite-a.

Zatim, eksplicitno na dozvoljenoj stvarnoj instanci:

```text
DW_RUN_SQL_INTEGRATION=1
python -m pytest -q -s tests/integration/test_crm_incremental_sql.py
7 passed, 1 warning in 5.63s
```

Upozorenje je bilo PytestCacheWarning pri kreiranju postojećeg cache direktorijuma; nije SQL/test greška.
Nije bilo neuspešnih testova. Prvi sandbox read-only pokušaj konekcije dobio je 08001 zbog Windows
bezbednosnog konteksta; dozvoljena verifikacija van sandbox-a prošla je bez promene globalnih postavki.

## Stvarni rezultati po paketu

Svaki paket obrađen je kroz isti runner koji koristi CLI; neposredno posle svakog paketa izvršen je
SELECT celog demo customers stanja i poređenje sa eksplicitnim expectations.json faze 3A. Poređene su
sve normalizovane CRM vrednosti, source vreme, last_event_id i business hash. Svih sedam poređenja prošlo je.

I/U su različiti kupci ubačeni/ažurirani nakon celog paketa. Ostale kolone broje događaje.

| Paket | Status | Ulaz | I | U | Update događaji | No-change | Stale | Duplicate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 00_snapshot | APPLIED | 3 | 3 | 0 | 0 | 0 | 0 | 0 |
| 01_changes | APPLIED | 3 | 1 | 1 | 1 | 1 | 0 | 0 |
| 02_versions | APPLIED | 2 | 0 | 1 | 2 | 0 | 0 | 0 |
| 03_late_arrival | APPLIED | 3 | 1 | 1 | 1 | 0 | 0 | 1 |
| 04_stale | APPLIED | 2 | 0 | 0 | 0 | 1 | 1 | 0 |
| 05_replay | REPLAY | 3 | 0 | 0 | 0 | 0 | 0 | 3 |
| 06_negative | REJECTED | 1 | 0 | 0 | 0 | 0 | 0 | 0 |

Negativni paket je odbijen pre otvaranja SQL konekcije. Customers ostaje isto; nema delimičnog staging-a
ili uspešnog ledger zapisa. Dry-run jednog validnog paketa zasebno je pokrenut kroz CLI i vratio exit 0.

Svih šest validnih paketa zatim je ponovljeno. Svaki je vratio REPLAY, nula ubačenih/ažuriranih kupaca,
a broj duplicate događaja jednak je broju ulaznih redova. Kompletno customers stanje i jedinstveni event
ledger ostali su identični, uključujući source vremena i last_event_id. Ponavljanje je dodalo samo
attempts/staging evidenciju isporuke, ne nove poslovne promene ili jedinstvene događaje.

## Dokaz rollback-a i konflikata

Dva stvarna SQL failure testa sprovedena su u posebnom test ID prostoru 1900000900–1900000999:

1. U proceduru su namerno prosleđena dva tipizirana test događaja sa istim cst_key za različite kupce,
   zaobilazeći preflight samo radi fault injection-a na SQL granici. Drugi INSERT izazvao je UNIQUE
   constraint grešku; svi zapisi paketa u svih pet tabela vraćeni su na prethodno stanje.
2. Posle uspešne apply_batch procedure, a pre COMMIT-a, test hook je u istoj stvarnoj SQL transakciji
   pročitao novog kupca 1900000922 i potvrdio da je prisutan, uz @@TRANCOUNT=1. Zatim je poslao stvarni
   `THROW 51199`. Nakon rollback-a zasebna konekcija potvrdila je odsustvo kupca i iste brojeve redova
   svih pet tabela kao pre pokušaja. Ovo nije samo Python mock dokaz: upsert i SQL greška stvarno su izvršeni.

Stvarni testovi dodatno su potvrdili odbijanje istog batch_id sa drugim sadržajem, istog event_id sa
drugim payload-om, konflikata unutar paketa i različitih vrednosti istog source vremena. Jednako vreme
sa istim vrednostima prolazi kao no_change. Dve konkurentne obrade istog paketa dale su tačno jedan
APPLIED i jedan REPLAY, uz jednog kupca. Snapshot dodaje kupca bez brisanja ostalih.

Deployment je još dva puta potvrđen nakon popunjavanja, sa istim potpisom i bez promene podataka.
Kontrolisani testovi nisu menjali ili brisali demo rezultate. Cleanup je u svojoj transakciji obrisao
samo registrovane test batch/event/customer identitete; test ID prostor je posle toga prazan.

## Očuvanje i konačno stanje

Pre deployment-a i nakon svih integration testova/cleanup-a pročitani su svi redovi/kolone originalnih
15 poslovnih tabela/view-ova. Kanonski sortirani multiskupovi (sa duplikatima) imaju identične SHA-256
hash-eve i brojeve redova. Uključeni su i load timestamp-ovi i Gold ključevi; definicije view-ova takođe
se podudaraju. To je stvarna potpuna provera sadržaja, ne samo poređenje ukupnog broja redova.

Lokalno SHA-256 poređenje 32 prethodno snimljene stavke potvrđuje nepromenjene originalne CSV fajlove,
postojeće SQL skripte, oba prethodna Python toka, crm_demo kod, dependencies i stanje Git indeksa.
Nema commita/pusha. README i dokumentacija dopunjeni su za novu fazu.

Posle cleanup-a ostalo je:

| Tabela u crm_incremental | Redova |
| --- | ---: |
| customers | 5 |
| events | 12 |
| batches | 5 |
| attempts | 12 |
| staging | 32 |

Pet jedinstvenih prihvaćenih batch-eva je očekivano: paket 05 je ponavljanje 01, a negativni nije prihvaćen.
Dvanaest attempts predstavlja šest validnih isporuka u prvom prolazu i šest u drugom. Staging čuva oba
prolaza (16 + 16 redova); events samo 12 jedinstvenih događaja.

## Primer kupca i korišćenje

C1 (1900000001) se ubacuje sa početnim prezimenom, u 01 prelazi na _v2, u 02 se njegove verzije obrađuju
po vremenu i završava na _v4 uprkos obrnutom CSV redosledu. Ponovljeni _v2 događaj u 03 je duplicate;
starija drugačija promena u 04 je stale. Replay i odbijeni negativni paket ne menjaju _v4. Create_date
ostaje isti, a source_updated_at odražava poslednju prihvaćenu izmenu.

Tačne deployment/dry-run/execute komande i SSMS SELECT upiti nalaze se u
[CRM_INCREMENTAL.md](CRM_INCREMENTAL.md). Suite CLI namerno završava exit 1 zbog negativnog paketa;
raniji uspešni paketi ostaju commitovani. Samostalni validni paket ili replay vraća exit 0.

Trajni mašinski dokaz: [PHASE_3B_RESULTS.json](PHASE_3B_RESULTS.json).
Pojedinačni lokalni JSON izveštaji su `reports/phase3b-00_snapshot.json` do
`reports/phase3b-06_negative.json`, a dry-run je `reports/phase3b-dry-run.json`.
Detaljan SQL test dokaz je sačuvan u `reports/phase3b-sql-evidence-d11b9bf1-876f-4ff0-9632-c6505cb5d725.json`.

## Preostala ograničenja

Serijalizovani demo nije visokopropusni CDC sistem. Nema retry/retention automatizacije, brisanja kupaca,
SCD Type 2 ili automatskih migracija. SQL granica veruje tipiziranim/kanonizovanim vrednostima ovog
klijenta; direktan konkurentni DML drugih aplikacija nije podržan. Nisu testirani pad servera ili gubitak
mreže u trenutku COMMIT-a. Takav ishod mora se proveriti u ledger-u pre retry-a.

Failure zapisi su lokalni JSON, jer se neuspešna SQL transakcija u celini vraća. Nagli prekid procesa ili
disk greška mogu ostaviti nezavršen JSON. Postojeći Gold ključevi i dalje su ROW_NUMBER vrednosti,
ne trajni surrogate ključevi; izolovani demo ih ne koristi niti utiče na Gold rezultate.
