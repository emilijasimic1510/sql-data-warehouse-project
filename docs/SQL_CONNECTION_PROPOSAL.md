# Predlog sledeće faze: Linux worker → lokalni SQL Server

Ovo je predlog, ništa od navedenog nije izvršeno u fazi 5B.

1. Zasebno odobriti TCP/IP samo za DESKTOP-N1402MQ\SQLEXPRESS, izabrati fiksni slobodan port
   i planirani restart te instance. Koristiti host.docker.internal + port u worker Connection;
   ne zavisiti od SQL Browser/UDP discovery-a. Testirati dostupnost iz projektnog scheduler-a.
   Firewall pravilo dodati samo ako je potrebno i ograničiti izvor na odgovarajuću Docker/WSL mrežu;
   ne izlagati port javnim mrežama. Koristiti sertifikat kome Linux driver veruje i Encrypt=yes.
2. Za ovu lokalnu mašinu praktičan izbor je zasebno odobren mixed mode i namenski SQL login,
   npr. dw_airflow_loader, mapiran samo u DataWarehouse. Alternativa je pravi AD/Kerberos principal,
   SPN i runtime ticket/keytab; desktop NTLM token se ne prenosi u Linux kontejner.
3. Namenski nalog ne treba sysadmin, db_owner, kreiranje baza ili pristup drugim bazama. Potrebni su:
   CONNECT u DataWarehouse; EXECUTE na bronze.load_bronze, silver.load_silver, mart.load_model,
   mart.check_quality; SELECT nad konkretnim Bronze/Silver/Gold/mart objektima koje postojeći quality,
   count i reconciliation upiti koriste; INSERT/UPDATE na audit.pipeline_runs i INSERT na
   audit.pipeline_steps/audit.quality_results. Metadata vidljivost tih procedura potrebna je za
   postojeći OBJECT_ID target check. Application lock koristi postojeći public principal u toj bazi.
4. Sam EXECUTE nije dovoljan dokaz da sadašnji loader može sve: Bronze koristi dinamički BULK INSERT,
   TRUNCATE zahteva ALTER, a mart ima IDENTITY_INSERT grane. Preporuka za zasebnu nedestruktivnu
   security migraciju je potpisan Bronze modul sa sertifikatskim pravom ADMINISTER BULK OPERATIONS
   i preciznim table INSERT/ALTER pravima, te kontrolisan izvršni kontekst za statičke Silver/mart
   module. Tako se potrebna povišena prava daju modulima, ne direktno worker login-u. Ne uključivati
   TRUSTWORTHY ili davati sysadmin/db_owner da bi test prošao. Ako se zadrže potpuno neizmenjeni,
   nepotpisani moduli, DBA mora posebno odobriti i testirati neophodna direktna BULK/INSERT/ALTER
   prava; to je širi pristup od preporučenog i nije samo read-only/EXECUTE nalog.
5. SQL Server servisni nalog mora imati read pristup samo dataset folderu na Windows hostu.
   To je zaseban NTFS pristup od SQL login-a i Linux read-only mount-a. sql_dataset_root ostaje
   Windows putanja; DW_DATASET_ROOT ostaje /opt/project/datasets.
6. Lozinku čuvati u zaštićenom projektnom runtime/worker.env kao Connection.password (auth_mode=sql),
   ili u Airflow metadata Connection-u preko lokalnog UI-a uz postojeći Fernet ključ. Ako se pređe
   na metadata Connection, ukloniti istoimeni AIRFLOW_CONN_* env zapis koji bi ga zasenio.
   Ne stavljati lozinku u Extra, DAG, CLI argument, Git, image ili log. Sačuvati postojeće runtime
   ACL-ove samo za vlasnika/izvršni nalog; Docker administrator i dalje može čitati environment.
   Za produkciju koristiti odgovarajući secrets backend umesto lokalnog dotenv fajla.
7. Tek po odobrenju i pripremi: container-side read-only preflight potvrđuje instancu/bazu/procedure;
   zatim poseban odobreni SQL integration test prava i jedno stvarno učitavanje, uz audit,
   shared application lock i sve postojeće reconciliation provere. Do tada execute=false.

Bezbednosnu migraciju i provere najmanjih potrebnih prava treba pripremiti kao zaseban pregledan
zadatak; nijedan SQL security ili mrežni DDL nije deo sadašnje faze 5B.

Relevantni Microsoft izvori: [BULK INSERT dozvole](https://learn.microsoft.com/en-us/sql/t-sql/statements/bulk-insert-transact-sql?view=sql-server-ver17), [TRUNCATE i EXECUTE AS](https://learn.microsoft.com/en-us/sql/t-sql/statements/truncate-table-transact-sql?view=sql-server-ver17).

