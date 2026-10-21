# Power BI priprema — Sales Performance & Data Reliability

Počni ovde. Otvori **Power BI Desktop → Blank report**, ne JSON/DAX kao PBIX.
Nema gotovog PBIX/PBIP u fazi 6A: UI kontrola nije uspela, pa model/refresh/DAX nisu verifikovani
u Desktop-u. SQL reference su stvarno izvršene. Nijedan raniji izveštaj nije prepisan.

## Ručno povezivanje i Import

1. U SSMS-u prvo izvrši target SELECT i read-only KPI/reconciliation iz
   [Windows vodiča](../docs/QUICKSTART_WINDOWS.md). E2E execute **nije potreban** za BI Import.
2. Power BI Desktop → Home → Get data → SQL Server.
   Server: `DESKTOP-N1402MQ\SQLEXPRESS`; Database: `DataWarehouse`; režim **Import**.
   Windows → Use my current credentials. Ne koristi SQL login, ne uključuj cloud/Publish.
3. Za jednostavan kontrolisan početak: Advanced options → SQL statement → kopiraj **samo prvi
   SELECT blok** iz [06_business_import.sql](sql/06_business_import.sql), bez komentara GO separatora.
   Transform Data → naziv query-ja `fact_sales`. Za preostala tri bloka ponovi New Source → SQL
   Server, sa istim serverom/bazom. Nazivi: `dim_customer`, `dim_product`, `dim_date`.
   Ako koristiš Navigator umesto SQL-a, izaberi iste mart tabele pa Choose Columns prema SQL
   fajlu; custom label kolone ipak treba napraviti kao u SELECT-u. SQL put je najdirektniji.
4. Dodaj odvojene query-je iz [05_audit_import.sql](sql/05_audit_import.sql): `audit_families`,
   `audit_runs`, `audit_steps`, `audit_quality`, `audit_snapshot`. Ne paste ceo fajl: svaki query
   dobija samo svoj SELECT i nema `GO`/`USE`. Nema novih SQL view-ova.
5. U Power Query-ju setuj date kolone na **Date** (source_order/shipping/due, calendar_date,
   product valid_from/valid_to), audit vremena na Date/Time, UUID na Text, keys na Whole number,
   iznose na Fixed decimal number. Izaberi dim_date → desni klik → Disable Enable load.
6. New Source → Blank Query → Advanced Editor → zameni sadržaj sa [Calendar.m](Calendar.m),
   nazovi query **Calendar**. Dim_date ostaje dependency, ne model tabela. Close & Apply.
7. Model view → napravi relacije tačno iz [MODEL.md](MODEL.md); proveri jedinstvenost, Single smer
   i aktivnu order relaciju. Calendar → Mark as date table → Date. Sort Month by Month Number.
8. Modeling → New measure → jednu po jednu nalepi definicije iz [measures.dax](measures.dax),
   redom. To je skup definicija, **nije** jedan executable DAX query. Možeš ih čuvati na fact_sales
   tabeli, a audit mere na audit_snapshot. Format: iznosi 2 decimale bez valute, counts 0 decimala,
   rate Percentage 2 decimale, duration 3 decimale. Definicije: [KPI rečnik](KPI_DICTIONARY.md).
9. View → Themes → Browse for themes (u novijem ribbon-u Design → Import theme) →
   [sales-reliability.theme.json](sales-reliability.theme.json). Import teme u Desktop-u nije
   izvršen u ovoj fazi; JSON sintaksa jeste proverena.
10. Dodaj/renamuj četiri report stranice prema [PAGES.md](PAGES.md). Napravi vizuale/filtre,
    uključi unknown kategoriju i undated kartice. Proveri Edit interactions i Reset filters.
11. Home → Refresh, pa poredi kartice sa SQL-om **sa istim filterima**; uradi acceptance korake u
    MODEL.md. Sačuvaj lokalno kao `powerbi/Sales Performance & Data Reliability.pbix`.
    To je budući stvarni fajl, nije isporučen placeholder. Ne Publish na Service.

Ako SQL konektor odbije sertifikat, ne menjaj registry, globalne privacy opcije ili SQL server.
Zabeleži tačnu poruku; lokalni pyodbc test koristi encryption + per-connection certificate trust,
ali to **ne konfiguriše Power BI konektor**. Njegove dostupne opcije zavise od verzije. Koristi
samo eksplicitnu per-source certificate trust opciju ako je dostupna i namerno odabrana za ovu
razvojnu instancu; ne biraj nešifrovanu konekciju samo da bi upozorenje nestalo. Ako opcije nema,
stani na konekciji i zabeleži blokadu. Ne unositi kredencijale u M ili Git.

## PBIP / TMDL bez lažnog projekta

Kada Desktop uspešno otvori i osveži stvarni model, možeš Save As → Power BI Project (.pbip),
ako je opcija dostupna u toj verziji. U PBIP se čuvaju odvojeni report i semantic model metadata;
TMDL definition direktorijum i TMSL model.bim su alternativni formati modela. Nemoj preimenovati
tekstualni fajl u `.pbix`, mešati oba formata ili kopirati verziono neusklađene PBIR sheme.
Desktop treba da generiše početnu validnu strukturu; zatim ponovo otvori `.pbip`, Refresh i Save.
Lokalni `.pbi` cache/podešavanja i credential fajlovi nisu za Git; proveri generated .gitignore
pre eventualnog budućeg commita. Ova faza ne menja Git indeks.

Zvanični Microsoft izvori (pregledani 21.10.2026):

- [SQL Server Import i Windows konekcija](https://learn.microsoft.com/en-us/power-query/connectors/sql-server)
- [PBIP projekti](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview)
- [Semantic model / TMDL i TMSL struktura](https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset)
- [TMDL view](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-tmdl-view)
- [Custom report themes](https://learn.microsoft.com/en-us/power-bi/create-reports/report-themes-create-custom)
- [Date table validacija](https://learn.microsoft.com/en-us/power-bi/transform-model/desktop-date-tables)

Detalji stvarnog izvršavanja i ograničenja: [PHASE_6A_VERIFICATION.md](../docs/PHASE_6A_VERIFICATION.md).
