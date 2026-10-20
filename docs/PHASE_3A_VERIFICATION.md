# Faza 3A — završna verifikacija

Datum: 11.10.2026. Faza 3A završena je lokalno, bez SQL konekcije, učitavanja ili izmene baze.
Postojeći full-load pipeline i originalni CSV izvori nisu menjani. Nema commita, pusha ili promene indeksa.

## Napravljeno

Odvojeni paket `crm_demo` koristi samo standardnu Python biblioteku. Generiše sintetičke CRM snapshot/delta
pakete i njihove manifeste, kao i eksplicitna očekivanja budućeg inkrementalnog ponašanja. Postojeći
validator za šest originalnih izvora ostaje nepromenjen. `docs/CRM_DEMO.md` definiše zaseban ugovor,
scenarije, semantiku vremena i plan SQL staging/upsert/SCD Type 1 faze; taj SQL nije implementiran.
Nije pronađen AGENTS.md u projektu ili pregledanim nadređenim direktorijumima.

Read-only pregled CRM izvora našao je 18494 zapisa, ID opseg 11000–29483, 4 prazna ID-ja i 6 dodatnih
redova sa ponovljenim ID-jem. Nema preklapanja sa demo opsegom 1900000000–1900000999.
Nijedno originalno ime nije prepisano u simulator: on uopšte ne čita originalni izvor.

## Testovi

Kompletan postojeći i novi suite izvršen je jednom, posle implementacije:

```text
.\.venv\Scripts\python.exe -m pytest -q
94 passed in 3.94s
```

To je svih 51 prethodnih + 43 nova test slučaja. Pokriveni su isti bajtovi/manifesti/ID-jevi pri istim
parametrima, determinističnost preko zasebnog Python procesa i drugačijeg PYTHONHASHSEED-a, rad bez
site-packages, stvarni hash i broj zapisa, pozitivan/negativan ugovor, CSV struktura, oštećen manifest,
ponovljeni event_id, zaštita output-a, originalni fajlovi, CLI exit kodovi i doslednost očekivanja.
Nezavisan interpreter pravila postoji samo u testovima; baza nije uključena u ove testove.

## Generisani i provereni demo

Iz korena projekta izvršeno:

```powershell
.\.venv\Scripts\python.exe -m crm_demo generate --output-dir .\demo_output\phase3a-seed42 --seed 42 --start-date 2026-01-01
.\.venv\Scripts\python.exe -m crm_demo verify --output-dir .\demo_output\phase3a-seed42
.\.venv\Scripts\python.exe -m crm_demo validate --package-dir .\demo_output\phase3a-seed42\06_negative
```

Generisanje: exit 0. Provera skupa: PASS / exit 0. Zasebna validacija negativnog paketa: FAIL / exit 1,
očekivano. CSV oblik i manifest negativnog paketa su ispravni; jedina ugovorna greška je prazan cst_id.
Za ponovno generisanje koristiti novi output folder: postojeći se nikada ne prepisuje.

C1–C5 označavaju ID-jeve 1900000001–1900000005. U tabeli su različiti kupci, ne broj UPDATE događaja:

| Paket | Redova | Validacija | Ubaciti | Ažurirati | Poslovno nepromenjeni |
| --- | ---: | --- | --- | --- | --- |
| 00_snapshot | 3 | PASS | C1,C2,C3 | — | — |
| 01_changes | 3 | PASS | C4 | C1 | C2,C3 |
| 02_versions | 2 | PASS | — | C1 | C2,C3,C4 |
| 03_late_arrival | 3 | PASS | C5 | C2 | C1,C3,C4 |
| 04_stale | 2 | PASS | — | — | C1–C5 |
| 05_replay | 3 | PASS | — | — | C1–C5 |
| 06_negative | 1 | FAIL, očekivano | — | — | C1–C5 |

C1: snapshot -> novo prezime _v2 -> dve verzije _v3/_v4 sa konačnim _v4 -> ponovljeni _v2 događaj
se preskače -> zaseban zastareo događaj ne vraća staro stanje -> replay i negativni paket ne menjaju kupca.
Njegov cst_create_date ostaje 2026-01-01 kroz celu priču; stvarni redosled promena određuje source_updated_at.

Manifesti su provereni prema stvarnim CSV bajtovima. Paket 05 ima identičan CSV, manifest i batch_id
kao paket 01. Ukupno postoji 12 različitih validnih događaja; 17 isporučenih redova uključuje njihove
ponovne isporuke i jedan zaseban neispravan događaj.
`git check-ignore` potvrdio je da runtime CSV i expectations.json nisu kandidati za dodavanje u Git.

SHA-256 poređenje 27 prethodno sačuvanih stavki potvrdilo je očuvanje šest CSV izvora, SQL skripti,
postojećih Python paketa, dependencies fajlova i stanja Git indeksa. Novi fajlovi su samo simulator,
testovi, dokumentacija i ignorisani demo/verification izlazi; README i .gitignore dopunjeni su za novu fazu.

Trajni sažetak: [PHASE_3A_RESULTS.json](PHASE_3A_RESULTS.json).
Runtime: `demo_output/phase3a-seed42/`; lokalni verification izlazi su u `reports/phase3a-verification.json`
i `reports/phase3a-negative-validation.json`. Detaljan ugovor i plan: [CRM_DEMO.md](CRM_DEMO.md).

## Granica faze i sledeći korak

Sledeći loader treba da validira staging, prepozna obrađene batch/event ID-jeve, odbije konfliktan
payload istog ID-ja, i unutar jedne transakcije upsert-uje poslednje stanje po cst_id, uz trajni ledger.
Novija verzija može biti update ili no_change; i no_change unapređuje prihvaćeno source vreme.
Starije verzije su stale bez izmene stanja. Ponovljeni commitovan paket ne pravi nove promene.
Negativan paket se odbija atomarno. Nema brisanja kupaca ili istorije SCD Type 2.

Globalni timestamp filter propustio bi C5 i validnu promenu C2 iz paketa 03. Zato treba garantovati
preuzimanje svih isporuka i odluku donositi po poslovnom ključu uz trajnu deduplikaciju događaja.
Gold ROW_NUMBER ključevi se izračunavaju pri čitanju i nisu trajno dodeljeni surrogate ključevi.

Specifikacija očekivanih rezultata i testovi nad memorijom nisu integracioni test SQL baze. Pre SQL
implementacije ostaje projektovanje izolovanog demo cilja, transakcija, konkurentnosti i oporavka.
Faza 3A ovde staje.
