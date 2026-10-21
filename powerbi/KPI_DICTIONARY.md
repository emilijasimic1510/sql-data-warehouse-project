# KPI ugovor

Mere: [measures.dax](measures.dax), izvorni grain/relacije: [MODEL.md](MODEL.md).
SQL reference su nezavisni read-only kontrolni obračuni, ne tvrdnja da je DAX izvršen.
Default je ceo dataset bez filtera, uključujući unknown i undated. Poslovne mere poštuju filtere
Calendar/customer/product, osim eksplicitno označenih dijagnostičkih kartica. Koristi iste filtere
u SQL-u pri poređenju; all-time SQL rezultat nije referenca za filtrirani vizual.

| Mera | Definicija / filter kontekst | Format | SQL referenca |
|---|---|---|---|
| Sales Amount | SUM sales_amount svih vidljivih stavki | #,##0.00; bez valute | 01 prvi SELECT |
| Quantity | SUM quantity | #,##0 | 01 prvi SELECT |
| Sales Rows | COUNTROWS fact_sales, broj stavki | #,##0 | 01 prvi SELECT |
| Orders | DISTINCTCOUNT order_number; ne broj stavki | #,##0 | 01 prvi SELECT; mesečni SELECT |
| Average Order Value | Sales Amount / Orders u istom kontekstu; u product filteru samo vidljiva vrednost stavki po porudžbini | #,##0.00 | 01 prvi SELECT |
| Purchasing Customers | Distinct customer_key>0 koji imaju vidljivu prodaju; unknown nije osoba | #,##0 | 01 prvi/drugi SELECT |
| Repeat Customers | Kupci sa >=2 distinct porudžbine **u izabranom periodu i istim product/market filterima**; all-time samo kada nema filtera | #,##0 | 01 drugi SELECT, @start/@end_exclusive |
| Repeat Customer Rate | Repeat Customers / Purchasing Customers, isti kontekst i customer>0 | 0.00% | 01 drugi SELECT (SQL vraća procenat 0–100) |
| Sales MoM Rate | Jedan ceo mesec prema prethodnom celom mesecu; obe granice strogo unutar globalnog observed order-date raspona | 0.00%; BLANK nije 0% | 04 prvi SELECT (stopa 0–1) |
| Sales YoY Rate | Jedna cela kalendarska godina prema prethodnoj celoj godini; isti konzervativni coverage uslov | 0.00% | 04 drugi SELECT |
| Unknown Product Sales Amount | Sales Amount gde product_key=0, uz presek ostalih filtera | #,##0.00 | 01 prvi/treći SELECT |
| Unknown Product Sales Rate | Unknown amount / ceo vidljivi Sales Amount, denominator uključuje unknown | 0.00% | 01 prvi SELECT (procenat 0–100) |
| Sales Without Order Date | Broj stavki order_date_key=0, ignoriše Calendar, zadržava customer/product | #,##0 | 01 prvi SELECT |
| Sales Amount Without Order Date | Iznos istih stavki; isti izuzetak Calendar filtera | #,##0.00 | 01 prvi SELECT |
| Sales by Shipping/Due Date | Sales Amount preko odgovarajuće neaktivne relacije, umesto order relacije | #,##0.00 | Isti SUM iz 01, grupisati po source_shipping_date/source_due_date |
| Last Confirmed Mart Completion UTC | Poslednji mart execute PASS ended_at_utc, proxy objave | yyyy-MM-dd HH:mm:ss UTC | 02 peti rezultat; 05 audit_snapshot |
| Last Successful E2E UTC | Poslednji e2e execute PASS ended_at_utc | yyyy-MM-dd HH:mm:ss UTC | 02 četvrti rezultat; 05 |
| Last Successful E2E Seconds | Razlika audit UTC end-start istog poslednjeg uspešnog E2E run-a | 0.000 s | 02/05; nije zbir child/step trajanja |
| Latest E2E Status / Started UTC | Najnoviji pokušaj, i kada nije PASS; ne skrivati neuspeh starijim uspehom | Text / UTC | 02 prvi rezultat; 05 |
| BI Refresh Observed UTC | SYSUTCDATETIME pri importu snapshot upita | UTC | 05; nije ni source-event ni load vreme |

Sales Amount ne znači profit, neto ili bruto; currency metadata ne postoji. Purchasing nije broj
svih dimenzionih kupaca. Repeat Rate nije retention, cohort ili dokaz lojalnosti. Orders/Customers/
Repeat/AOV/rate su neaditivni: total mora ponovo računati meru, ne sabirati prikazane grupe.
Ako nema denominatora, DIVIDE daje BLANK. Unknown numerator koristi 0 kada nema takvih stavki.

## Nepotpuni periodi i coverage

Min/max **order** datum dolazi iz fact-a nezavisno od business slicera. Da se prvi/poslednji mesec
ili godina ne predstave kao kompletni, zahtevamo current period i prethodni period strogo unutar
tih granica. To namerno odbija oba boundary perioda čak i kada bi poslednja prodaja pala na kraj
meseca; izvor nema completeness watermark. Unutrašnji periodi su samo **rasponom podržani**, ne
garantovano kompletni izvorni podaci. MoM zahteva sve datume jednog meseca, YoY sve datume jedne
godine; delimičan date slicer i višegodišnji total vraćaju BLANK. Nema YTD/MTD poređenja u ovoj fazi.
Referentni SQL daje rasponom podržane 2012/2011 -17.4253% i 2013/2012 +179.7711%; 2010/2011/2014
YoY ostaje NULL prema ugovoru. SQL rezultat 2011/2010 nije prihvatljivo „godišnje poređenje”.

## Povezivanje sa tačnim SQL kontekstom

Za datum filter koristi `source_order_date >= @start AND source_order_date < @end_exclusive`.
Za country/category dodaj LEFT JOIN na dimenziju i isti label/filter iz 06_business_import.sql
PRE GROUP BY customer_key ili SUM. Time Repeat meri kupca sa dve porudžbine u istoj vidljivoj
selekciji; nije precomputed lifetime flag. DAX stopa je 0–1, dok dve all-time SQL procentualne
kolone sadrže 0–100; poredi posle formatiranja. Decimalne SQL reference čuvaju više decimala
od kartice; round na dve decimale radi se samo za prikaz.

## Zvanična dokumentacija korišćena za pripremu

- [CALCULATE i filter context](https://learn.microsoft.com/en-us/dax/calculate-function-dax)
- [DISTINCTCOUNT i neaditivni totals](https://learn.microsoft.com/en-us/dax/distinctcount-function-dax)
- [DIVIDE i prazan denominator](https://learn.microsoft.com/en-us/dax/divide-function-dax)
- [USERELATIONSHIP](https://learn.microsoft.com/en-us/dax/userelationship-function-dax)
- [Zahtevi date tabele](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-date-tables)

Pročitano 21.10.2026; formula source je statički pregledan, Desktop validacija ostaje ručna.
