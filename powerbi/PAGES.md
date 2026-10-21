# Četiri stranice izveštaja

Ovo je specifikacija za ručno sastavljanje, ne screenshot napravljenog Power BI izveštaja.
Canvas 16:9 (1280×720), svetla pozadina, 24 px margine, kartice u gornjem redu, najviše 5–6
glavnih vizuala po stranici. Font Segoe UI; naslovi 18–22, ose/legende najmanje 11. Tema:
[sales-reliability.theme.json](sales-reliability.theme.json). Unknown serije ručno oboji amber,
poznate teal/blue; nemoj zavisiti samo od boje — naziv i status uvek ispiši.

Svaka stranica: naslov, jedna rečenica o pitanju, vidljiv filter kontekst i kratka fusnota.
Nema valute/simbola $, € ili RSD, nema 3D/pie mnoštva kategorija. Svi tooltip-i koriste mere,
ne slučajni SUM tehničkih ključeva. Uključi naslov i alt text koji opisuje pitanje vizuala.

## 1. Sales Overview

Pitanje: **Koliki je obim prodaje i kako se datirani iznos menja kroz vreme?**

| Vizual / pozicija | Polja i mere | Filter / interakcija |
|---|---|---|
| Gornje 4 kartice | Sales Amount, Orders, Quantity, Average Order Value | Calendar i current country sliceri; početno All |
| Linijski chart, sredina levo | X Calendar.Year Month; Y Sales Amount; tooltip Sales Rows, Orders, Sales MoM Rate | Sort Year Month ascending; trend ne uključuje NULL order datum |
| Godišnja matrica, sredina desno | Rows Calendar.Year; Values Sales Amount, Sales YoY Rate | Full-year context; partial/boundary YoY blank, fusnota „Not comparable” |
| Donje dve dijagnostičke kartice | Sales Without Order Date; Sales Amount Without Order Date | Naslov „Undated — all dates”; mere ignorišu Calendar |
| Sliceri | Calendar.Year / Year Month, dim_customer.current_customer_country | Bez podrazumevanog date is-not-blank filtera; Reset filters bookmark |

Fusnota: „Amount currency/net/gross unspecified. Trend uses order dates. Undated amount remains in
unfiltered total. Boundary period changes are not comparable.” Ne koristi relativni „last year”
filter prema današnjem datumu: izvorni istorijski raspon je predmet analize.

## 2. Products & Markets

Pitanje: **Koje istorijske kategorije i aktuelne zemlje kupaca doprinose iznosu, i koliki deo nema
pouzdanu istorijsku klasifikaciju?**

| Vizual | Polja i mere | Filter / interakcija |
|---|---|---|
| Kartice | Sales Amount, Unknown Product Sales Amount, Unknown Product Sales Rate | Isti business context; unknown denominator uključuje unknown |
| Horizontalni bar | dim_product.category_label → Sales Amount; tooltip Quantity, Orders | Prikaži SVE kategorije uključujući Unknown historical category, bez Top N filtera |
| Horizontalni bar | dim_customer.current_customer_country → Sales Amount | Naslov „Sales by CURRENT customer country”; Unknown current country ostaje |
| Matrix detalj | category_label → subcategory_label → product_label; Sales Amount, Quantity | Drilldown, ne filtrirati is_current; proizvodi kroz verzije mogu imati iste nazive |
| Unknown reason tabela | fact_sales.product_match_reason; Sales Rows, Sales Amount | Visual filter product_key=0; breakdown bez pokušaja dodele aktuelne kategorije |
| Sliceri | Calendar.Year/Year Month, category_label, current_customer_country | Date slicer jasno označen; bez skrivenih cross-page filtera |

Unknown nije kategorija proizvoda već nedostajuća istorijska veza. Trenutna customer country je
SCD1 atribut; ova analiza nije dokaz geografije stare kupovine. Ne koristi mapu sa naslovom
„Purchase location” i ne izračunavaj maržu iz current product cost.

## 3. Customers

Pitanje: **Koliko poznatih kupaca kupuje i koliko njih ima najmanje dve porudžbine u istoj selekciji?**

| Vizual | Polja i mere | Filter / interakcija |
|---|---|---|
| Kartice | Purchasing Customers, Repeat Customers, Repeat Customer Rate | Preračunavanje u izabranom periodu, ne lifetime flag |
| Clustered columns | Calendar.Year; Purchasing Customers, Repeat Customers | U tooltip-u definicija „>=2 orders within this year and current filters” |
| Bar | current_customer_country; Repeat Customer Rate | Tooltip Purchasing Customers i Repeat Customers; ne porediti rate bez denominatora |
| Matrix | current_customer_country; Orders, Purchasing Customers, Repeat Customers, Repeat Customer Rate, Average Order Value | Total se iznova računa; ne sumirati distinct brojeve |
| Sliceri | Calendar.Year/Year Month, current_customer_country, category_label | Selekcija kategorije menja i značenje repeat: ponovljene porudžbine sa vidljivim stavkama |

Fusnota: „Repeat is within the selected context, not cohort retention or proof of loyalty.
Unknown customer key is excluded from customer counts.” Ne prikazuj imena/datume rođenja;
nisu potrebni za poslovno pitanje. Demografske uzročne tvrdnje nisu podržane.

## 4. Data Reliability

Pitanje: **Koji je poslednji potvrđeni tok/objava i koja poznata ograničenja utiču na analizu?**

| Vizual | Polja i mere | Filter / interakcija |
|---|---|---|
| Operativne kartice | Latest E2E Status, Last Successful E2E UTC, Last Successful E2E Seconds, Last Confirmed Mart Completion UTC | Disconnected audit_snapshot, svi datumi UTC; poslednja mart kartica označena „confirmed completion proxy” |
| Osvežavanje | BI Refresh Observed UTC | Malo tekstualno polje, odvojeno od source event datuma |
| Parent/child tabela | audit_runs.component/run_id/status/started_at_utc/ended_at_utc/elapsed_seconds/failure_stage | Single-select audit_families.family_id; root_component=e2e za ovaj blok |
| Koraci i quality tabela (dva vizuala) | audit_steps.name/status/duration_seconds; audit_quality.check_id/severity/status/anomaly_count/metric_value | Ista audit family; ne SUM anomaly_count različitih check-ova |
| Unknown reason bar | product_match_reason; Sales Amount; tooltip Sales Rows | product_key=0 samo na vizualu, bez date filtera |
| Donje kartice | Sales Without Order Date, Sales Amount Without Order Date | All-time data diagnostics |

Ne sinhronizuj poslovne slicere sa ovom stranicom. Audit filter ne sme menjati business chart.
Audit detalji quality tabele pokrivaju warehouse registry; mart quality proverava se zasebnim
read-only SQL-om i child JSON izveštajem. Nema lažnog mart zelenog statusa za check koji nije
importovan. `RUNNING` = nepotvrđen završetak, ne nužno aktivan proces; FAIL ne znači globalni rollback.

Tekstualni blok: „Historical event range and pipeline execution time are different concepts.
Unknown product and missing dates are preserved. 13 orders contain both dated and undated lines;
distinct order counts across groups are not additive.”

## Tri početna nalaza — osnova za narativ

Izmereni read-only 21.10.2026; tačni agregati: [PHASE_6A_RESULTS.json](../docs/PHASE_6A_RESULTS.json).

1. **29,48% iznosa (8.654.683,00) nema pouzdanu istorijsku product vezu.** BEFORE_HISTORY nosi
   8.649.691,00 u 18.410 redova, missing order date još 4.992,00 u 19 redova. To ograničava
   category analizu; nije dokaz da su sami proizvodi nepoznati ili da je prodaja pogrešna.
2. **6.865 od 18.484 poznata kupca ima >=2 porudžbine u celom dostupnom datasetu: 37,14%.**
   To opisuje ponovljenu kupovinu u ovom istorijskom uzorku. Bez cohort/observation window ugovora
   ne možemo to nazvati retention-om, proceniti churn niti utvrditi uzrok ponašanja.
3. **Datirani iznos 2013. je 16.344.878,00 naspram 5.842.231,00 u 2012, +179,77%.**
   Obe godine su unutrašnje godine posmatranog raspona prema ugovoru. To je promena zabeleženog
   obima, ne dokaz efekta kampanje ili potpune pokrivenosti izvora. Januar 2014. se ne poredi
   sa celom 2013. godinom; 19 nedatiranih stavki ne dodeljujemo proizvoljnoj godini.
