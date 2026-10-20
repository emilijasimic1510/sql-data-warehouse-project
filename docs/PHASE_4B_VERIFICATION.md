# Faza 4B — završna verifikacija

Datum: 12.10.2026. Cilj potvrđen pre mutacija i ponovo pri izvršavanju/proveri:
DESKTOP-N1402MQ\SQLEXPRESS, DataWarehouse. Faza 4B završena; nema naredne faze, commita ili pusha.

## Šta je povezano

Novi e2e_pipeline direktno poziva postojeći warehouse structured runner i mart runner. Nema shell CLI
poziva, kopije CSV validatora, SQL quality pravila ili mart transformacija. Prvi korak ostaje CSV
validacija, zatim Bronze, Silver i warehouse quality; mart se poziva samo posle warehouse PASS.
WARNING dozvoljava nastavak, ERROR/SQL/audit failure preskače mart. Parent JSON čuva oba child rezultata.

ProjectSession upravlja jednom SQL konekcijom i Session Exclusive application lock-om
`datawarehouse.pipeline.v1`, database scoped, public principal, default 10000 ms bounded timeout.
Standalone warehouse i standalone mart takođe koriste taj resource. E2E child-ovi pozajmljuju istu
konekciju; ne pokušavaju da dobiju parent lock na drugoj konekciji. Release/disconnect su u finally.

Originalni autocommit full-load nema whole-load rollback. Mart ima svoju SERIALIZABLE transakciju i
quality gate pre COMMIT-a. E2E nije jedna transakcija. Full-load PASS + mart FAIL znači parent FAIL,
sa mogućim novim Silver/Gold i prethodno objavljenim mart-om. CRM-demo nije deo toka.

Eksplicitna additive audit migracija dodaje parent_run_id, component, summary_json i failure_stage,
uz self-FK/index/JSON check. Postojeći audit run/step/quality model ponovo je korišćen. Parent i linked
warehouse/mart audit zapisi postoje; detaljne warehouse provere ostaju u njegovom audit-u, a sve
mart provere u embedded child JSON-u. Aggregate sažetak je u parent summary_json.

## Testovi

Kompletan postojeći i novi unit suite, jednom po završetku implementacije:

```text
python -m pytest -q
141 passed, 13 skipped in 4.46s
```

123 prethodna unit slučaja i 18 novih. Starih 11 SQL slučajeva nisu ponavljani; dodata su 2 opt-in
project-lock SQL slučaja. Unit slučajevi potvrđuju redosled, preskakanje mart-a posle Bronze/Silver/quality
failure-a, WARNING nastavak, mart failure -> parent FAIL, dry-run bez konekcije, istu konekciju, release
pri grešci, standalone writer protokol, audit failure, zaštitu report-a i parent/child UUID-jeve.
Mock test sa unknown prihodima potvrđuje da se njihov iznos ne oduzima od ukupnog prihoda.

Novi stvarni SQL lock testovi nisu izvršavali load procedure niti menjali tabele:

- Dve različite SQL session veze: prva drži Exclusive lock. Druga ima timeout 150 ms i ne dobija lock.
  Nakon release-a prve, druga uspešno dobija i oslobađa lock. Dokaz je u lokalnom lock JSON-u.
- Kontrolisana host-side greška u prvom vlasniku aktivira finally close/release; druga konekcija zatim
  uspešno uzima resource. Prvobitni test cleanup pokušao je da zatvori već zatvoren cursor (test greška),
  pa je ispravljen i ponovljen samo taj slučaj: 1 passed, 1 deselected in 0.20s. Oba SQL scenarija su proverena.

Prvi pokušaj audit migracije imao je SQL 42S22: nove kolone vezivane su u istom batch-u pre dostupnosti
novog metadata. DDL references izvršene su runtime EXEC-om i migracija je uspešno završena pre load-a.
Nisu menjani poslovni podaci ili SQL pravila da bi test/migracija prošli.

## Jedino stvarno end-to-end izvršavanje

Izvršeno je **tačno jedno potpuno E2E učitavanje**, kroz novu CLI komandu. Nema retry-a warehouse-a ili
ponovnog mart load-a u ovoj fazi. Dry-run odvojeno je završio PASS / exit 0 bez SQL konekcije.

Parent run_id: **4803c33f-d430-45ea-b9e5-65b2c791e27b**.
Warehouse child run_id: **d47e3a56-6d5a-487c-a4c1-7ebf14392cf1**.

| Parent korak | Status | Posmatrano trajanje |
| --- | --- | ---: |
| warehouse | PASS | približno 2.72 s |
| mart | PASS | približno 7.89 s |
| summary | PASS | približno 0.09 s |

Konačno: **PASS / exit 0**, audit PASS, coordination RELEASED, mart committed=True.
Warehouse ima nula ERROR provera; S12 upozorava na 15 datuma pre 1924, kao ranije. Mart ima nula
kritičnih reconciliation anomalija. Poznati unknown nalazi ostaju WARNING. CSV newline upozorenje
za PX_CAT_G1V2.csv ostaje sa svih 37 zapisa. Ova vremena su jedno posmatranje, ne performance benchmark.

## Konačan sažetak

| Metrika | Rezultat |
| --- | ---: |
| Prodajni redovi | 60398 |
| Količina | 60423 |
| Prihod | 29356250.00 |
| Poznate temporalne product veze | 41969 |
| Current product veze | 33723 |
| Istorijske product veze | 8246 |
| Istorijske veze / svi prodajni redovi | 13.65% |
| Unknown product veze | 18429 |

| Unknown razlog | Redova | Količina | Prihod |
| --- | ---: | ---: | ---: |
| BEFORE_HISTORY | 18410 | 18426 | 8649691.00 |
| MISSING_ORDER_DATE | 19 | 19 | 4992.00 |

Unknown prihod **8654683.00 uključen je u ukupan 29356250.00**. Unknown proizvodi nemaju pouzdane
istorijske atribute/trošak; current cost nije proizvoljno korišćen kao zamena. Nema novih izmišljenih
product intervala ili datuma. U02/U07 mart quality nalaz predstavlja istih 19 zapisa u dve role-e,
pa se brojevi WARNING provera ne sabiraju kao broj različitih neispravnih prodaja.

## Reconciliation i potpun sadržaj

Pre izvršavanja potvrđeno je da originalni warehouse odgovara Phase 4A baseline-u, a kompletan mart
fact poslovni hash odgovara sačuvanom PHASE_4A_RESULTS.json. Zatim su snimljeni svi redovi/kolone 24
objekta: originalnih 15 business objekata, 5 CRM-demo tabela i 4 mart tabele.

Posle E2E-a svi sortirani multiskupovi, sa duplikatima, imaju iste hash-eve i brojeve redova. Isključeni
su samo Silver dwh_create_date i mart fact_key, jer ih full-load/full-refresh tehnički menjaju. Customer,
product i date dimenzioni ključevi ostali su deo poređenja. Gold generisani ključevi nisu isključeni.
Ovo je potpuna business-content provera, ne tvrdnja zasnovana samo na ukupnim brojevima redova.
CRM-demo svih pet tabela ostao je identičan bez izuzetaka.

Parent i oba child audit run-a upoređeni su sa embedded JSON rezultatima: UUID, parent ID, component,
status i UTC start/end se podudaraju. Parent step statusi/trajanja i parent summary_json odgovaraju JSON-u.
Svih 28 warehouse check audit redova odgovara child rezultatima. Mart quality ponovo je read-only
izvršen pri verifikaciji; sve kritične anomalije su nula. Zajednički lock je bio oslobođen i ponovo
dostupan read-only verifikacionoj sesiji.

Originalni CSV i SQL fajlovi, CRM-demo kod, dependencies i Git indeks ostali su nepromenjeni.
Namerno su dopunjeni warehouse runner/audit i mart runner za composition/coordination, uz novu helper
klasu, E2E paket, additive audit skriptu, testove i dokumentaciju. Nema drugih baza/šema/servisa ili
credential promena. Generisani report-i su pod ignorisanim reports/ direktorijumom.

Trajni dokaz: [PHASE_4B_RESULTS.json](PHASE_4B_RESULTS.json). Lokalni detaljni parent report:
`reports/phase4b-execute.json`; dry-run: `reports/phase4b-dry-run.json`. Parent report već sadrži oba
child izveštaja. Commands, SSMS lineage pregled i svakodnevni recovery: [E2E_PIPELINE.md](E2E_PIPELINE.md).

## Ograničenja i spremnost za Airflow

Direktan ručni SQL bez application-lock protokola nije koordinisan. E2E nema whole-run rollback ili
automatski retry. Mart failure posle warehouse PASS čuva prethodni mart, ali ne vraća Silver/Gold.
Audit/report failure posle commit-a mora se razlikovati od neuspele objave. COMMIT acknowledgement
loss, nasilni process kill i disk failure nisu posebno simulirani u ovoj fazi.

Za sledeću Airflow fazu postoje jedna ulazna funkcija/komanda, bounded lock, parent/child lineage,
quality gates, exit code i report artifacts. Prvi jednostavan dizajn treba da poziva ovaj tok u jednom
task-u, uz full-load retries=0. Podela na više worker task-ova traži novo projektovanje lock ownership-a
između njih; deljena konekcija se ne prenosi između procesa. Raspored, worker pristup, storage i
notification/recovery politika ostaju za sledeću fazu. Airflow nije uveden. Faza 4B ovde staje.
