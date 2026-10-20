# Faza 4A — nalazi izvora i odluke pre implementacije

Read-only profilisanje 12.10.2026 na potvrđenom DESKTOP-N1402MQ\SQLEXPRESS / DataWarehouse.
Dokument nastaje pre deployment-a ili učitavanja mart-a. Izvorni kod i stvarna baza su autoritativni.

- Prodaja: 60398 redova, 27659 različitih order_number. Order_number nije grain/PK.
- Trenutno nema ponovljenih grupa (order_number, product_number, customer_id) ili potpuno identičnih
  prodajnih redova. Ipak, ne postoji source line_id, unique constraint ili ugovor stabilnosti te kombinacije.
  Grain mart fact-a zato je jedan sačuvan izvorni Silver prodajni zapis, sa multiplicitetom. SQL fact_id je
  tehnički ključ osvežavanja, ne identitet izvorne stavke. Strategija je full-refresh bez deduplikacije.
- Customer cst_id je jedinstven i nije NULL. ERP cid join-ovi i kategorijski id ne dupliraju rezultate.
- Silver ima 397 product verzija, 295 product_number i 295 otvorenih/current redova. Kombinacija
  (prd_key, prd_start_dt) je jedinstvena, non-NULL, bez preklapanja i nevažećih intervala.
- Postojeći Silver end date je datum PRE sledećeg start-a. Intervale definišemo inkluzivno
  [valid_from, valid_to], NULL end = otvoren kraj. Time se ne dodaje izmišljena istorija.
- Prodaja ima 19 NULL order datuma, 0 NULL shipping/due datuma. Potrebna date dimenzija pokriva
  2010-12-29–2014-02-09, uključujući shipping i due datume.
- Direktne poslovne veze imaju 0 nedostajućih customer/product ključeva. Vremenska veza ima
  18410 dated prodaja bez važeće verzije i 0 dvosmislenih matching verzija. 8246 prodaja pripada
  istorijskim (zatvorenim) verzijama. 155 je tačno na valid_from, 25 tačno na valid_to granici.
- Izvorni sales/price/quantity su INT; agregati su quantity=60423, amount=29356250.00.
  Mart koristi DECIMAL(19,2) za iznose/cenu i BIGINT za količinu; agregate širi na decimal(38,2).

Odluke: customer key trajni IDENTITY uz UNIQUE cst_id; product key trajni IDENTITY uz UNIQUE
(product_number, valid_from); date_key YYYYMMDD sa rezervisanim 0. Ne resetuju se identity vrednosti.
Unknown dimenzioni redovi imaju ključ 0; unknown datum nema izmišljenu vrednost datuma.
Missing order date -> unknown proizvod i unknown order date, bez temporalnog nagađanja.
Ostale temporalne nepoklopljene veze dobijaju razlog BEFORE_HISTORY/AFTER_HISTORY/INTERVAL_GAP
ili MISSING_PRODUCT_KEY. Unknown je WARNING metrika, ne automatska greška: prodaja i iznosi ostaju
sačuvani. Multiplikacija join-a, preklapanje, neispravni ključ/FK ili reconciliation razlika su ERROR.
Dims koje izvor više ne sadrži se zadržavaju sa is_in_source=0; ključevi se ne recikliraju.
Fact se objavljuje uz očuvane dimenzione ključeve u jednoj transakciji, sa proverama pre COMMIT-a.

Mašinski nalazi: lokalni reports/phase4a-source-findings.json. Primer temporalne prodaje:
SO45080, BK-R50B-58, order_date 2011-07-01, verzija 2011-07-01–2012-06-30, quantity 1, amount 699.
Faza 3B demo ostaje izolovan; mart čita samo odgovarajuće Silver izvore.
